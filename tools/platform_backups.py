#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""WO-09 static backup manifests; no network, keys, buckets or host mutation."""
import copy
import gzip
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse
import yaml

ROOT = Path(__file__).resolve().parents[1]
COMMON = ROOT/'deploy/common'


def config():
    value=json.loads((COMMON/'backup-config.json').read_text())
    endpoint=urlparse(value['endpointURL'])
    if endpoint.scheme!='https' or not endpoint.hostname or endpoint.username or endpoint.port:
        raise ValueError('Backups require an HTTPS endpoint without credentials or a custom port')
    if value['environment']!='twinfra-dev-cairo-1' or value['region']!='auto':
        raise ValueError('Only the owner-approved dev R2 profile is admitted')
    if value['archiveTimeoutSeconds']>300 or value['retentionDays']!=7:
        raise ValueError('WO-09 archive timeout/retention differs')
    if not isinstance(value.get('enabled'),bool):raise ValueError('Explicit backup activation gate required')
    return value


def upstream():
    lock=json.loads((COMMON/'backup-artifacts.lock.json').read_text())['plugin']
    raw=gzip.decompress((COMMON/'vendor/barman-cloud.yaml.gz').read_bytes())
    if hashlib.sha256(raw).hexdigest()!=lock['sha256']:
        raise ValueError('Barman release manifest checksum differs')
    return [o for o in yaml.safe_load_all(raw) if o]


def plugin_objects():
    from platform_dev import labels, security, image
    site=config();ns=site['namespace'];result=[]
    for original in upstream():
        o=copy.deepcopy(original);meta=o['metadata']
        if 'namespace' in meta:meta['namespace']=ns
        meta.setdefault('labels',{}).update(labels('backups'))
        for subject in o.get('subjects',[]):
            if 'namespace' in subject:subject['namespace']=ns
        if o['kind']=='Secret':
            # This upstream Secret contains only an image name. A literal env
            # pin is transparent to the all-image-references and licence gates.
            continue
        if o['kind']=='Deployment':
            o['spec']['strategy']={'type':'RollingUpdate','rollingUpdate':{'maxUnavailable':0,'maxSurge':1}}
            pod=o['spec']['template']['spec'];pod['securityContext']['fsGroup']=10001
            o['spec']['template']['metadata']['labels'].update(labels('backups'))
            container=pod['containers'][0]
            container['image']=image('barman-plugin');container['imagePullPolicy']='IfNotPresent'
            container['securityContext']=security()|{'runAsUser':10001,'runAsGroup':10001}
            container['env']=[{'name':'SIDECAR_IMAGE','value':image('barman-sidecar')}]
            container['resources']={'requests':{'cpu':'50m','memory':'64Mi'},'limits':{'cpu':'500m','memory':'256Mi'}}
        result.append(o)
    return result


def objectstore(namespace=None):
    from platform_dev import obj
    c=config();secret=c['credentialSecret']
    spec={'configuration':{'destinationPath':'s3://'+c['bucket']+'/'+c['postgresPrefix'],
         'endpointURL':c['endpointURL'],
         's3Credentials':{'accessKeyId':{'name':secret,'key':'ACCESS_KEY_ID'},
                          'secretAccessKey':{'name':secret,'key':'ACCESS_SECRET_KEY'}},
         'data':{'compression':'gzip'},'wal':{'compression':'gzip'}},
         'retentionPolicy':'7d','instanceSidecarConfiguration':{
             'resources':{'requests':{'cpu':'100m','memory':'128Mi'},'limits':{'cpu':'1','memory':'512Mi'}},
             'env':[{'name':'AWS_DEFAULT_REGION','value':c['region']},
                    {'name':'AWS_REQUEST_CHECKSUM_CALCULATION','value':'when_required'},
                    {'name':'AWS_RESPONSE_CHECKSUM_VALIDATION','value':'when_required'}]}}
    return obj('ObjectStore','twinfra-postgres-backups',spec,'barmancloud.cnpg.io/v1',ns=namespace or c['namespace'])


def cluster_patch(cluster):
    """Preserve PostgreSQL identity, storage, image and application roles."""
    result=copy.deepcopy(cluster)
    result['spec']['postgresql']['parameters']['archive_timeout']=str(config()['archiveTimeoutSeconds'])+'s'
    result['spec']['plugins']=[{'name':'barman-cloud.cloudnative-pg.io','isWALArchiver':True,
                             'parameters':{'barmanObjectName':'twinfra-postgres-backups'}}]
    return result


def backup_objects():
    from platform_dev import obj
    schedule=obj('ScheduledBackup','twinfra-postgres-daily',{
        'schedule':'0 0 2 * * *','immediate':True,'backupOwnerReference':'self',
        'cluster':{'name':config()['cluster']},'method':'plugin',
        'pluginConfiguration':{'name':'barman-cloud.cloudnative-pg.io'}},'postgresql.cnpg.io/v1')
    status=obj('ConfigMap','twinfra-backup-status');status['data']={}
    reader=obj('Role','twinfra-backup-secret-reader',api='rbac.authorization.k8s.io/v1')
    reader['rules']=[{'apiGroups':[''],'resources':['secrets'],'resourceNames':[config()['credentialSecret']],'verbs':['get']},
                     {'apiGroups':[''],'resources':['configmaps'],'resourceNames':['twinfra-backup-status'],'verbs':['get','patch']}]
    binding=obj('RoleBinding','twinfra-backup-secret-reader',api='rbac.authorization.k8s.io/v1')
    binding.update(roleRef={'apiGroup':'rbac.authorization.k8s.io','kind':'Role','name':reader['metadata']['name']},
                   subjects=[{'kind':'ServiceAccount','name':'twinfra-etcd-backup','namespace':'kube-system'}])
    return plugin_objects()+[objectstore(),schedule,status,reader,binding]+network()


def node_objects():
    from platform_dev import obj, labels, security, image
    site=config();name='twinfra-etcd-backup';l=labels('backups')|{'app.kubernetes.io/name':name}
    account=obj('ServiceAccount',name,ns='kube-system')
    cm=obj('ConfigMap','twinfra-backup-config',ns='kube-system')
    cm['data']={'backup-config.json':json.dumps(site,sort_keys=True)}
    certificates=('ca.crt','healthcheck-client.crt','healthcheck-client.key')
    host_volumes=[{'name':'etcd-'+str(i),'hostPath':{'path':'/etc/kubernetes/pki/etcd/'+file,'type':'File'}} for i,file in enumerate(certificates)]
    mounts=[{'name':'etcd-'+str(i),'mountPath':'/etcd-tls/'+file,'readOnly':True} for i,file in enumerate(certificates)]
    work={'name':'snapshot','mountPath':'/backup'}
    resources={'requests':{'cpu':'100m','memory':'128Mi'},'limits':{'cpu':'1','memory':'512Mi'}}
    def container(n,im,command,root=False):
        sc=security()
        if root:sc.update(runAsNonRoot=False,runAsUser=0,runAsGroup=65532)
        return {'name':n,'image':im,'imagePullPolicy':'IfNotPresent','command':command,
                'securityContext':sc,'resources':copy.deepcopy(resources),'volumeMounts':[dict(work)]}
    etcd=image('etcd-backup');python=image('python');backup=image('backup')
    save=container('snapshot',etcd,['/usr/local/bin/etcdctl','--endpoints=https://192.168.1.3:2379',
        '--cacert=/etcd-tls/ca.crt','--cert=/etcd-tls/healthcheck-client.crt','--key=/etcd-tls/healthcheck-client.key',
        'snapshot','save','/backup/snapshot.db'],root=True)
    save['volumeMounts']+=mounts
    # The root-owned 0600 output must become group-readable for the non-root
    # verifier/uploader. No certificate volume is mounted into this container.
    chmod=container('snapshot-permissions',python,['python','-c',
        "import os; p='/backup/snapshot.db'; s=os.stat(p); assert s.st_uid==0 and s.st_gid==65532; os.chmod(p,0o640)"],root=True)
    check=container('verify',etcd,['/usr/local/bin/etcdutl','snapshot','status','/backup/snapshot.db','--write-out=json'])
    upload=container('encrypt-upload',backup,['python','/app/upload.py'])
    upload['resources']['limits']['memory']='1Gi'
    upload['volumeMounts'].append({'name':'config','mountPath':'/config','readOnly':True})
    upload['volumeMounts'].append({'name':'api-token','mountPath':'/var/run/secrets/kubernetes.io/serviceaccount','readOnly':True})
    job=obj('CronJob',name,{'schedule':'0 */6 * * *','timeZone':'Etc/UTC','suspend':not site['enabled'],
        'concurrencyPolicy':'Forbid','startingDeadlineSeconds':300,'successfulJobsHistoryLimit':1,'failedJobsHistoryLimit':2,
        'jobTemplate':{'spec':{'backoffLimit':1,'activeDeadlineSeconds':1800,'ttlSecondsAfterFinished':600,
            'template':{'metadata':{'labels':l},'spec':{'restartPolicy':'Never','serviceAccountName':name,
                'automountServiceAccountToken':False,'nodeSelector':{'kubernetes.io/hostname':'twinfra-dev-cairo-1'},
                'tolerations':[{'key':'node-role.kubernetes.io/control-plane','operator':'Exists','effect':'NoSchedule'}],
                'securityContext':{'runAsNonRoot':True,'runAsUser':65532,'runAsGroup':65532,'fsGroup':65532,'seccompProfile':{'type':'RuntimeDefault'}},
                'volumes':host_volumes+[{'name':'snapshot','emptyDir':{'medium':'Memory','sizeLimit':'512Mi'}},
                                      {'name':'config','configMap':{'name':cm['metadata']['name']}},
                                      {'name':'api-token','projected':{'defaultMode':0o440,'sources':[
                                          {'serviceAccountToken':{'path':'token','expirationSeconds':3600}},
                                          {'configMap':{'name':'kube-root-ca.crt','items':[{'key':'ca.crt','path':'ca.crt'}]}}]}}],
                'initContainers':[save,chmod,check],'containers':[upload]}}}}},'batch/v1',ns='kube-system')
    # This policy selects only our Job Pods; it does not isolate other system Pods.
    policy=obj('CiliumNetworkPolicy','twinfra-etcd-backup-network',{
        'endpointSelector':{'matchLabels':{'app.kubernetes.io/name':name}},'ingress':[],
        'egress':[{'toEntities':['host'],'toPorts':[{'ports':[{'port':'2379','protocol':'TCP'}]}]},
                  {'toEntities':['kube-apiserver'],'toPorts':[{'ports':[{'port':'443','protocol':'TCP'},{'port':'6443','protocol':'TCP'}]}]},
                  {'toEndpoints':[{'matchLabels':{'k8s:io.kubernetes.pod.namespace':'kube-system','k8s:k8s-app':'kube-dns'}}],
                   'toPorts':[{'ports':[{'port':'53','protocol':'ANY'}],'rules':{'dns':[{'matchPattern':'*'}]}}]},
                  {'toFQDNs':[{'matchName':urlparse(site['endpointURL']).hostname}],
                   'toPorts':[{'ports':[{'port':'443','protocol':'TCP'}]}]}]},'cilium.io/v2',ns='kube-system')
    return [account,cm,job,policy]


def node_exception():
    from manifest_contract import pod_projection, podspec
    job=next(o for o in node_objects() if o['kind']=='CronJob')
    return {'status':'approved','registry':'registry.twinfra.example.com',
            'approval':{'by':'amazen33','date':'2026-10-16','decision':'WO-09 Amendment 3; three read-only etcd client files only'},
            'agents':{'CronJob/kube-system/twinfra-etcd-backup':pod_projection(job)},
            'backupNodeException':{'kind':job['kind'],'namespace':'kube-system','name':job['metadata']['name'],'podSpec':podspec(job)}}


def outputs():
    directory=ROOT/'deploy/environments/dev/cairo-1/backups'
    return {directory/'node/workloads.yaml':yaml.safe_dump_all(node_objects(),sort_keys=False),
            directory/'node/kustomization.yaml':yaml.safe_dump({'apiVersion':'kustomize.config.k8s.io/v1beta1','kind':'Kustomization','resources':['workloads.yaml']},sort_keys=False),
            directory/'reference.yaml':yaml.safe_dump_all(backup_objects(),sort_keys=False),
            COMMON/'backup-node-exception.json':json.dumps(node_exception(),indent=2)+'\n',
            COMMON/'backup/alerts.rules.yaml':yaml.safe_dump({'groups':alert_groups()},sort_keys=False),
            directory/'observability/prometheus-rule.yaml':yaml.safe_dump(alert_manifest(),sort_keys=False)}


def alert_groups():
    rules=[]
    for kind,seconds in [('base',87300),('wal',config()['postgresRpoSeconds']),('etcd',config()['etcdRpoSeconds'])]:
        metric='twinfra_backup_last_success_timestamp_seconds{kind="'+kind+'"}'
        rules.append({'alert':'TwinfraBackupStale'+kind.title(),
            'expr':'(time() - '+metric+' >= '+str(seconds)+') or absent('+metric+')',
            'for':'1m','labels':{'severity':'critical','kind':kind},
            'annotations':{'summary':'Twinfra '+kind+' backup is stale or missing'}})
    rules.append({'alert':'TwinfraBackupCheckFailed','expr':'twinfra_backup_check_failed == 1',
                  'for':'1m','labels':{'severity':'critical'},
                  'annotations':{'summary':'Twinfra backup check reported failure'}})
    return [{'name':'twinfra.backups','rules':rules}]


def alert_manifest():
    from platform_dev import obj
    return obj('PrometheusRule','twinfra-backups',{'groups':alert_groups()},'monitoring.coreos.com/v1')


def network():
    from platform_dev import obj
    ns=config()['namespace'];host=urlparse(config()['endpointURL']).hostname
    def select(values):return {'matchLabels':{'k8s:io.kubernetes.pod.namespace':ns,**values}}
    cnpg=select({'k8s:app.kubernetes.io/name':'cloudnative-pg'})
    plugin=select({'k8s:app':'barman-cloud'})
    dns={'toEndpoints':[{'matchLabels':{'k8s:io.kubernetes.pod.namespace':'kube-system','k8s:k8s-app':'kube-dns'}}],
         'toPorts':[{'ports':[{'port':'53','protocol':'ANY'}],'rules':{'dns':[{'matchPattern':'*'}]}}]}
    tcp=lambda port:[{'ports':[{'port':str(port),'protocol':'TCP'}]}]
    return [
        obj('CiliumNetworkPolicy','twinfra-barman-plugin-network',{
            'endpointSelector':plugin,'ingress':[{'fromEndpoints':[cnpg],'toPorts':tcp(9090)},
                {'fromEntities':['host','remote-node','health'],'toPorts':tcp(9090)}],
            'egress':[dns,{'toEntities':['kube-apiserver'],'toPorts':tcp(443)+tcp(6443)}]},'cilium.io/v2'),
        obj('CiliumNetworkPolicy','twinfra-cnpg-plugin-egress',{'endpointSelector':cnpg,
            'egress':[{'toEndpoints':[plugin],'toPorts':tcp(9090)},
                      {'toEndpoints':[{'matchLabels':{'k8s:io.kubernetes.pod.namespace':config()['restoreNamespace'],
                                                       'k8s:cnpg.io/cluster':'twinfra-postgres-restore'}}],
                       'toPorts':tcp(5432)+tcp(8000)}]},'cilium.io/v2'),
        obj('CiliumNetworkPolicy','twinfra-postgres-backup-egress',{
            'endpointSelector':select({'k8s:cnpg.io/cluster':config()['cluster']}),
            'egress':[dns,{'toFQDNs':[{'matchName':host}],'toPorts':tcp(443)}]},'cilium.io/v2')]
