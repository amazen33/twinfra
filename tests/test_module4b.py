"""IAM configuration/security regressions; no real login or JWT verification is claimed."""
import copy,json,sys,unittest
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import module4b
from render_module4b import realm,plugin,rbac,oidc_args,route_patch,base_route,compose_route,identity_gateway

class IAMContracts(unittest.TestCase):
    def test_complete_realm_contract(self):module4b.realm_contract(realm())
    def test_pinned_source_and_schema_reproduce(self):self.assertEqual(module4b.bundle()['versions']['keycloak'],'26.8.0')
    def test_complete_gateway_contract(self):module4b.plugin_contract(plugin())
    def test_complete_rbac_contract(self):module4b.rbac_contract(rbac())
    def reject_realm(self,mutation):
        r=realm();mutation(r)
        with self.assertRaises(ValueError):module4b.realm_contract(r)
    def reject_plugin(self,mutation):
        p=plugin();mutation(p['spec']['plugins'][0]['config'])
        with self.assertRaises(ValueError):module4b.plugin_contract(p)
    def test_password_grant_rejected(self):self.reject_realm(lambda r:r['clients'][1].update(directAccessGrantsEnabled=True))
    def test_implicit_flow_rejected(self):self.reject_realm(lambda r:r['clients'][1].update(implicitFlowEnabled=True))
    def test_wildcard_redirect_rejected(self):self.reject_realm(lambda r:r['clients'][1]['redirectUris'].append('https://*'))
    def test_missing_pkce_rejected(self):self.reject_realm(lambda r:r['clients'][1]['attributes'].update({'pkce.code.challenge.method':'plain'}))
    def test_api_and_kubernetes_scope_mix_rejected(self):self.reject_realm(lambda r:r['clients'][2]['defaultClientScopes'].append('function.read'))
    def test_local_group_path_collisions_rejected(self):self.reject_realm(lambda r:r['clientScopes'][1]['protocolMappers'][0]['config'].update({'full.path':'false'}))
    def test_api_audience_in_id_token_rejected(self):self.reject_realm(lambda r:r['clientScopes'][0]['protocolMappers'][0]['config'].update({'id.token.claim':'true'}))
    def test_public_api_scope_rejected(self):self.reject_realm(lambda r:r.update(scopeMappings=[]))
    def test_default_user_provisioning_rejected(self):self.reject_realm(lambda r:r['users'].append({'username':'example'}))
    def test_mfa_enrollment_removal_rejected(self):self.reject_realm(lambda r:r['requiredActions'][0].update(defaultAction=False))
    def test_jwt_none_algorithm_rejected(self):self.reject_plugin(lambda c:c.update(accept_none_alg=True))
    def test_gateway_tls_skip_rejected(self):self.reject_plugin(lambda c:c.update(ssl_verify=False))
    def test_gateway_wrong_issuer_rejected(self):self.reject_plugin(lambda c:c.update(discovery='https://other.example.com/discovery'))
    def test_gateway_audience_bypass_rejected(self):self.reject_plugin(lambda c:c['claim_validator']['audience'].update(required=False))
    def test_gateway_scope_bypass_rejected(self):self.reject_plugin(lambda c:c.update(required_scopes=[]))
    def test_gateway_secret_in_git_rejected(self):self.reject_plugin(lambda c:c.update(client_secret='FixtureNeverRealCredential'))
    def test_gateway_unsigned_identity_header_rejected(self):self.reject_plugin(lambda c:c.update(set_userinfo_header=True))
    def test_cluster_admin_escalation_rejected(self):
        r=rbac();r[1]['roleRef']['name']='cluster-admin'
        with self.assertRaises(ValueError):module4b.rbac_contract(r)
    def test_secret_read_rejected(self):
        r=rbac();r[2]['rules'][0]['resources'].append('secrets')
        with self.assertRaises(ValueError):module4b.rbac_contract(r)
    def test_mutation_or_impersonation_rejected(self):
        for verb in ['create','update','delete','impersonate','bind','escalate']:
            r=rbac();r[0]['rules'][0]['verbs'].append(verb)
            with self.assertRaises(ValueError):module4b.rbac_contract(r)
    def test_missing_prefix_rejected(self):
        r=rbac();r[1]['subjects'][0]['name']='/vcloud/cluster-observers'
        with self.assertRaises(ValueError):module4b.rbac_contract(r)
    def test_namespace_scope_expansion_rejected(self):
        r=rbac();r[3]['metadata']['namespace']='platform-services'
        with self.assertRaises(ValueError):module4b.rbac_contract(r)
    def test_cluster_role_cannot_read_all_workloads(self):
        r=rbac();r[0]['rules'][0]['resources'].append('pods')
        with self.assertRaises(ValueError):module4b.rbac_contract(r)
    def test_patch_composes_and_preserves_gateway_tls_backend(self):
        self.assertEqual(module4b.apply_patch(base_route(),route_patch()),compose_route())
        before=base_route()['spec']['http'][0];after=compose_route()['spec']['http'][0]
        self.assertEqual(before['match'],after['match']);self.assertEqual(before['backends'],after['backends'])
        self.assertEqual([p['name'] for p in after['plugins']],['proxy-rewrite'])
    def test_patch_rejects_unexpected_route_target(self):
        base=base_route();base['metadata']['name']='other-route'
        with self.assertRaises(ValueError):module4b.apply_patch(base,route_patch())
    def test_api_server_group_prefix_matches_bindings(self):
        args={a['name']:a['value'] for a in oidc_args()}
        self.assertEqual(args['oidc-groups-prefix']+'/'+'vcloud/cluster-observers',rbac()[1]['subjects'][0]['name'])
        self.assertEqual(args['oidc-client-id'],'vcloud-kubernetes');self.assertEqual(args['oidc-username-claim'],'sub')
        self.assertEqual(args['oidc-ca-file'],'/etc/kubernetes/pki/keycloak-ca.crt')
    def test_identity_gateway_excludes_administration_and_bearer_login_loop(self):
        objects=identity_gateway();route=objects[2]['spec']['http'][0]
        self.assertEqual(route['match']['paths'],['/realms/vcloud/*','/resources/*'])
        self.assertFalse(any(p['name']=='openid-connect' for p in route['plugins']))
        self.assertEqual(objects[1]['spec']['scheme'],'https')
        self.assertEqual(objects[1]['spec']['upstreamHost'],'auth.vcloud.example.com')
        module4b.identity_contract(objects)
    def test_admin_path_or_forwarded_header_spoofing_rejected(self):
        for mutation in [lambda r:r['match']['paths'].append('/admin/*'),
                         lambda r:r['plugins'][0]['config']['headers']['set'].pop('X-Forwarded-For')]:
            objects=identity_gateway();mutation(objects[2]['spec']['http'][0])
            with self.assertRaises(ValueError):module4b.identity_contract(objects)
if __name__=='__main__':unittest.main()
