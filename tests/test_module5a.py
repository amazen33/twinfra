"""GPU-free real LangChain API/LCEL and fail-closed RAG security regressions."""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch
import yaml
from langchain_core.documents import Document
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_postgres import PGVectorStore
from sqlalchemy.pool import NullPool

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'module-5a/rag'))
import pipeline as p
import module5a as validator
import render_module5a as render


class RagTests(unittest.TestCase):
    def setUp(self):
        self.cfg=p.config(ROOT/'module-5a/config/rag.yaml')
        self.cfg['enabled']=True;self.cfg['embeddings']['manifestSHA256']='0'*64
        self.store=Mock();self.store.get_by_ids.return_value=[]
        self.store.add_documents.side_effect=lambda docs,ids:ids
        self.doc=Document(page_content='vCloud uses Kubernetes.',metadata={'source':'architecture-v1',
            'chunk':0,'embedding_revision':self.cfg['embeddings']['revision']})

    def test_defaults_do_not_enable_runtime(self):
        self.assertFalse(p.config(ROOT/'module-5a/config/rag.yaml')['enabled'])
        with patch.object(sys,'argv',['pipeline.py','--config',str(ROOT/'module-5a/config/rag.yaml'),'query','--question','test']),patch.object(p,'encoder') as encoder,patch('sys.stderr',new=io.StringIO()):
            self.assertEqual(p.main(),1);encoder.assert_not_called()

    def altered_config(self,field,key,value):
        cfg=copy.deepcopy(self.cfg);cfg[field][key]=value
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'config.yaml';path.write_text(yaml.safe_dump(cfg),encoding='utf-8')
            return p.config(path)

    def test_tls_cannot_be_disabled(self):
        with self.assertRaises(ValueError):self.altered_config('database','sslmode','disable')

    def test_endpoint_cannot_be_redirected(self):
        with self.assertRaises(ValueError):self.altered_config('inference','endpoint','https://other.example/v1/chat/completions')

    def test_vector_dimensions_cannot_drift(self):
        with self.assertRaises(ValueError):self.altered_config('embeddings','dimensions',768)

    def test_gate_requires_accepted_model_manifest(self):
        with self.assertRaises(ValueError):self.altered_config('embeddings','manifestSHA256',None)

    def test_chunk_overlap_must_advance(self):
        with self.assertRaises(ValueError):self.altered_config('retrieval','chunkOverlapCharacters',1600)

    def test_native_url_preserves_special_password_without_logging_it(self):
        url=p.database_url(self.cfg,('vcloud_dyn_'+'A'*20,'p@ss:/%?#'))
        self.assertEqual(url.password,'p@ss:/%?#');self.assertNotIn(url.password,str(url))
        self.assertEqual(url.query['sslmode'],'verify-full');self.assertIn('sslrootcert',url.query)

    def test_csi_pair_requires_whole_response(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'lease.json'
            path.write_text(json.dumps({'data':{'username':'vcloud_dyn_'+'A'*20,'password':'test-only'}}))
            self.assertEqual(p.credentials(path),('vcloud_dyn_'+'A'*20,'test-only'))
            path.write_text(json.dumps({'username':'vcloud_dyn_'+'A'*20,'password':'test-only'}))
            with self.assertRaisesRegex(ValueError,'CSI'):p.credentials(path)

    def test_revoked_credentials_are_not_cached_between_operations(self):
        values=[('vcloud_dyn_'+'A'*20,'first'),('vcloud_dyn_'+'B'*20,'second')]
        with patch.object(p,'credentials',side_effect=values) as reader,patch.object(PGVectorStore,'create_sync',return_value=self.store) as create:
            for _ in range(2):
                with p.vector_store(self.cfg,DeterministicFakeEmbedding(size=384)):pass
            self.assertEqual(reader.call_count,2)
            engines=[call.kwargs['engine'] for call in create.call_args_list]
            self.assertEqual([e._pool.url.username for e in engines],[x[0] for x in values])
            self.assertTrue(all(isinstance(e._pool.pool,NullPool) for e in engines))
            self.assertEqual(create.call_args.kwargs['table_name'],'vcloud_rag_documents')
            self.assertEqual(create.call_args.kwargs['distance_strategy'].value.operator,'<=>')

    def test_actual_langchain_chain_retrieves_before_generation(self):
        self.store.similarity_search.return_value=[self.doc];chat=Mock(return_value='Kubernetes.')
        result=p.build_chain(self.store,self.cfg,chat).invoke('What orchestrates vCloud?')
        self.assertEqual(result['answer'],'Kubernetes.');self.store.similarity_search.assert_called_once_with('What orchestrates vCloud?',k=4)
        self.assertEqual(result['sources'],[{'source':'architecture-v1','chunk':0}])
        self.assertIn(self.doc.page_content,chat.call_args.args[0][1]['content'])

    def test_empty_retrieval_does_not_invent_or_call_inference(self):
        self.store.similarity_search.return_value=[];chat=Mock()
        result=p.build_chain(self.store,self.cfg,chat).invoke('unknown')
        self.assertEqual(result['sources'],[]);chat.assert_not_called()

    def test_context_is_bounded(self):
        self.doc.page_content='x'*20000;self.store.similarity_search.return_value=[self.doc]
        state=p.retrieve('query',self.store,self.cfg);self.assertEqual(len(state['context']),8000)

    def test_large_question_fails_before_query(self):
        with self.assertRaises(ValueError):p.retrieve('x'*2001,self.store,self.cfg)
        self.store.similarity_search.assert_not_called()

    def test_wrong_indexed_encoder_is_rejected(self):
        self.doc.metadata['embedding_revision']='other';self.store.similarity_search.return_value=[self.doc]
        with self.assertRaises(ValueError):p.retrieve('query',self.store,self.cfg)

    def test_ingestion_ids_are_idempotent_and_do_not_create_ddl(self):
        data=[{'source':'doc-v1','text':'x'*2000}]
        first=p.ingest(self.store,data,self.cfg);second=p.ingest(self.store,data,self.cfg)
        self.assertEqual(first,second);self.assertEqual(len(first),2)
        self.assertNotIn('init_vectorstore_table',self.store.method_calls)
        self.assertEqual(self.store.add_documents.call_args.args[0][0].metadata['embedding_revision'],self.cfg['embeddings']['revision'])

    def test_source_update_cannot_leave_silent_stale_chunks(self):
        self.doc.metadata['source_sha256']='old';self.store.get_by_ids.return_value=[self.doc]
        with self.assertRaises(ValueError):p.ingest(self.store,[{'source':'doc-v1','text':'changed'}],self.cfg)
        self.store.add_documents.assert_not_called()

    def test_duplicate_source_in_batch_cannot_mix_two_versions(self):
        with self.assertRaises(ValueError):p.ingest(self.store,[
            {'source':'doc-v1','text':'long '*400},{'source':'doc-v1','text':'short'}],self.cfg)
        self.store.add_documents.assert_not_called()

    def test_model_content_and_manifest_cannot_be_changed(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'config.json').write_bytes(b'{}')
            receipt={'repository':'model','revision':'a'*40,'filesSHA256':{'config.json':hashlib.sha256(b'{}').hexdigest()}}
            raw=json.dumps(receipt).encode();(root/'vcloud-model.json').write_bytes(raw);digest=hashlib.sha256(raw).hexdigest()
            p.verify_model(root,'model','a'*40,digest)
            (root/'config.json').write_bytes(b'changed')
            with self.assertRaises(ValueError):p.verify_model(root,'model','a'*40,digest)
            receipt['filesSHA256']['config.json']=hashlib.sha256(b'changed').hexdigest()
            (root/'vcloud-model.json').write_text(json.dumps(receipt))
            with self.assertRaises(ValueError):p.verify_model(root,'model','a'*40,digest)

    def test_no_redirect_to_other_host(self):
        with self.assertRaises(ValueError):p.NoRedirect().redirect_request(None,None,None,None,None,None)

    def test_inference_request_is_private_bounded_and_ca_verified(self):
        response=Mock();response.read.return_value=json.dumps({'choices':[{'message':{'content':'answer'}}]}).encode()
        manager=Mock();manager.__enter__=Mock(return_value=response);manager.__exit__=Mock(return_value=False)
        opener=Mock();opener.open.return_value=manager
        with patch.object(p.ssl,'create_default_context',return_value=Mock()) as context,patch.object(p,'build_opener',return_value=opener):
            self.assertEqual(p.completion([{'role':'user','content':'question'}],self.cfg),'answer')
            context.assert_called_once_with(cafile=self.cfg['inference']['caFile'])
            request=opener.open.call_args.args[0];body=json.loads(request.data)
            self.assertEqual(request.full_url,self.cfg['inference']['endpoint']);self.assertEqual(body['max_tokens'],512)
            self.assertFalse(body['stream']);self.assertNotIn('Authorization',request.headers)

    def test_driver_error_does_not_leak_password_or_traceback(self):
        with patch.object(sys,'argv',['pipeline.py','--config','ignored','query','--question','q']),patch.object(p,'config',return_value=self.cfg),patch.object(p,'encoder',side_effect=RuntimeError('SECRET-URL')),patch('sys.stderr',new=io.StringIO()) as stderr:
            self.assertEqual(p.main(),1);self.assertNotIn('SECRET-URL',stderr.getvalue());self.assertNotIn('Traceback',stderr.getvalue())


class ManifestTests(unittest.TestCase):
    def test_rendered_pods_and_credentials_keep_frozen_policy(self):
        items=[o for path,text in render.files().items() if path.endswith('.yaml') for o in yaml.safe_load_all(text)]
        validator.audit(items)

    def test_privileged_gpu_service_rejected(self):
        obj=render.vllm()[1];obj['spec']['template']['spec']['containers'][0]['securityContext']['privileged']=True
        with self.assertRaises(ValueError):validator.audit([obj])

    def test_gpu_quantity_must_be_equal_and_one(self):
        obj=render.vllm()[1];obj['spec']['template']['spec']['containers'][0]['resources']['limits']['nvidia.com/gpu']=2
        with self.assertRaises(ValueError):validator.audit([obj])

    def test_hostpath_model_storage_rejected(self):
        obj=render.vllm()[1];obj['spec']['template']['spec']['volumes'][0]={'name':'models','hostPath':{'path':'/models'}}
        with self.assertRaises(ValueError):validator.audit([obj])

    def test_jobs_must_remain_suspended(self):
        obj=render.jobs()[0];obj['spec']['suspend']=False
        with self.assertRaises(ValueError):validator.audit([obj])

    def test_query_and_writer_identities_and_secrets_are_separate(self):
        items=render.integration();classes=[o for o in items if o['kind']=='SecretProviderClass']
        self.assertEqual(len(classes),2)
        for obj in classes:
            params=obj['spec']['parameters'];self.assertNotIn('secretObjects',obj['spec'])
            self.assertEqual(len(yaml.safe_load(params['objects'])),1)
        self.assertNotEqual(classes[0]['spec']['parameters']['roleName'],classes[1]['spec']['parameters']['roleName'])

    def test_no_world_or_any_external_workload_allowance(self):
        for policy in render.network():
            for rule in policy['spec'].get('ingress',[])+policy['spec'].get('egress',[]):
                self.assertNotIn('world',rule.get('fromEntities',[])+rule.get('toEntities',[]))
                self.assertNotIn('toFQDNs',rule);self.assertNotIn('toCIDR',rule)

    def test_scale_from_zero_has_both_controller_egress_paths(self):
        policies={o['metadata']['name']:o for o in render.network()}
        for app,expected in [('activator',{'8112'}),('autoscaler',{'9090','8022'})]:
            policy=policies['vcloud-rag-'+app]
            self.assertEqual(policy['spec']['endpointSelector']['matchLabels'],{'app':app})
            rule=policy['spec']['egress'][0]
            self.assertEqual(rule['toEndpoints'][0]['matchLabels']['k8s:serving.knative.dev/service'],'vcloud-vllm')
            self.assertEqual({p['port'] for p in rule['toPorts'][0]['ports']},expected)

    def test_renderer_has_no_drift(self):render.main(True)


if __name__=='__main__':unittest.main()
