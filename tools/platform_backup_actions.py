#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Explicit owner backup diagnostics, restore rendering and scoped LV transport."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import subprocess
import yaml

from platform_resources import ROOT
from platform_backups import config, objectstore


def kubectl(context, *args):
    result=subprocess.run(['kubectl','--context',context,*args],capture_output=True,text=True)
    if result.returncode:raise ValueError('kubectl backup observation failed; verify WO-08/WO-09 prerequisites')
    return result.stdout


def timestamp(value):
    if isinstance(value,(int,float)):
        if not math.isfinite(value) or value<=0:raise ValueError('Missing/nonfinite backup timestamp')
        return datetime.fromtimestamp(value,timezone.utc)
    parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None:raise ValueError('Backup time must include its timezone')
    return parsed.astimezone(timezone.utc)


def freshness(value, now, warn, fail):
    try:
        point=timestamp(value);age=(now-point).total_seconds()
        if age<0:raise ValueError('Future backup timestamp')
        return {'status':'FAIL' if age>=fail else 'WARN' if age>=warn else 'PASS',
                'timestamp':point.isoformat(),'ageSeconds':int(age),'warnSeconds':warn,'failSeconds':fail}
    except (ValueError,TypeError,AttributeError,OverflowError):
        return {'status':'FAIL','timestamp':None,'ageSeconds':None,'reason':'missing, invalid or future timestamp',
                'warnSeconds':warn,'failSeconds':fail}


def assess(base, wal, etcd, now=None):
    now=now or datetime.now(timezone.utc);site=config()
    values={'base':freshness(base,now,86400,86400+site['postgresRpoSeconds']),
            'wal':freshness(wal,now,600,site['postgresRpoSeconds']),
            'etcd':freshness(etcd,now,18000,site['etcdRpoSeconds'])}
    return {'status':'failed' if any(v['status']=='FAIL' for v in values.values()) else 'warning' if any(v['status']=='WARN' for v in values.values()) else 'passed',
            'checkedAt':now.isoformat(),'backups':values,'postgresRtoTargetSeconds':site['postgresRtoSeconds'],
            'restoreRpoRtoMeasured':False}


def observe(context):
    site=config();ns=site['namespace']
    store=json.loads(kubectl(context,'get','objectstore','twinfra-postgres-backups','-n',ns,'-o','json'))
    base=store.get('status',{}).get('serverRecoveryWindow',{}).get(site['cluster'],{}).get('lastSuccessfulBackupTime')
    cluster=json.loads(kubectl(context,'get','cluster',site['cluster'],'-n',ns,'-o','json'))
    pod=cluster.get('status',{}).get('currentPrimary','')
    if not re.fullmatch(r'twinfra-postgres-[1-9][0-9]*',pod):raise ValueError('No verified PostgreSQL primary identity')
    metrics=kubectl(context,'get','--raw','/api/v1/namespaces/'+ns+'/pods/'+pod+':9187/proxy/metrics')
    match=re.search(r'^cnpg_pg_stat_archiver_last_archived_time(?:\{[^\n]*\})?\s+([0-9.eE+-]+)\s*$',metrics,re.M)
    wal=float(match[1]) if match else None
    status=json.loads(kubectl(context,'get','configmap','twinfra-backup-status','-n',ns,'-o','json'))
    result=assess(base,wal,status.get('data',{}).get('etcdSnapshotTime'))
    last_failure=store.get('status',{}).get('serverRecoveryWindow',{}).get(site['cluster'],{}).get('lastFailedBackupTime')
    if last_failure and (not base or timestamp(last_failure)>timestamp(base)):
        result['status']='failed';result['backupFailureAfterLastSuccess']=True
    return result


def prometheus(report):
    lines=[]
    for name,value in report['backups'].items():
        point=timestamp(value['timestamp']).timestamp() if value['timestamp'] else 0
        lines.append('twinfra_backup_last_success_timestamp_seconds{kind="'+name+'"} '+str(point))
        lines.append('twinfra_backup_freshness_failed{kind="'+name+'"} '+str(int(value['status']=='FAIL')))
    lines.append('twinfra_backup_check_failed '+str(int(report['status']=='failed')))
    return '\n'.join(lines)+'\n'


def restore_manifest(target_time):
    from platform_dev import database, obj
    site=config();ns=site['restoreNamespace'];point=timestamp(target_time)
    if point>=datetime.now(timezone.utc):raise ValueError('Restore target must be in the past')
    cluster=next(v for v in database() if v['kind']=='Cluster')
    cluster['metadata']['name']='twinfra-postgres-restore';cluster['metadata']['namespace']=ns
    spec=cluster['spec'];spec.pop('managed',None);spec.pop('plugins',None)
    spec['bootstrap']={'recovery':{'source':'source','recoveryTarget':{'targetTime':point.isoformat()}}}
    spec['externalClusters']=[{'name':'source','plugin':{'name':'barman-cloud.cloudnative-pg.io',
        'parameters':{'barmanObjectName':'twinfra-postgres-restore-source','serverName':site['cluster']}}}]
    pv=next(v for v in database() if v['kind']=='PersistentVolume')
    pv['metadata']['name']='twinfra-restore-drill'
    pv['spec']['local']['path']='/var/lib/twinfra/local-pv/restore-drill'
    pv['spec']['claimRef']={'namespace':ns,'name':'twinfra-postgres-restore-1'}
    pv['metadata']['annotations']['twinfra.io/vetting-document']='docs/runbooks/backup-and-restore.md'
    namespace=obj('Namespace',ns,ns=None)
    namespace['metadata']['labels'].update({'pod-security.kubernetes.io/enforce':'restricted','pod-security.kubernetes.io/enforce-version':'v1.30'})
    store=objectstore(ns);store['metadata']['name']='twinfra-postgres-restore-source';store['spec'].pop('retentionPolicy',None)
    deny=obj('NetworkPolicy','twinfra-restore-default-deny',{'podSelector':{},'policyTypes':['Ingress','Egress'],'ingress':[],'egress':[]},'networking.k8s.io/v1',ns=ns)
    policy=obj('CiliumNetworkPolicy','twinfra-restore-network',{'endpointSelector':{},
        'ingress':[{'fromEntities':['host','remote-node','health'],'toPorts':[{'ports':[{'port':'8000','protocol':'TCP'}]}]},
                   {'fromEndpoints':[{'matchLabels':{'k8s:io.kubernetes.pod.namespace':site['namespace'],'k8s:app.kubernetes.io/name':'cloudnative-pg'}}],
                    'toPorts':[{'ports':[{'port':'5432','protocol':'TCP'},{'port':'8000','protocol':'TCP'}]}]}],
        'egress':[{'toEntities':['kube-apiserver'],'toPorts':[{'ports':[{'port':'443','protocol':'TCP'},{'port':'6443','protocol':'TCP'}]}]},
                  {'toEndpoints':[{'matchLabels':{'k8s:io.kubernetes.pod.namespace':'kube-system','k8s:k8s-app':'kube-dns'}}],
                   'toPorts':[{'ports':[{'port':'53','protocol':'ANY'}],'rules':{'dns':[{'matchPattern':'*'}]}}]},
                  {'toFQDNs':[{'matchName':site['endpointURL'].removeprefix('https://')}],
                   'toPorts':[{'ports':[{'port':'443','protocol':'TCP'}]}]}]},'cilium.io/v2',ns=ns)
    return [namespace,pv,store,deny,policy,cluster]


def restore_storage(args):
    from platform_host import request
    from platform_image_staging import SSH
    ssh=SSH(args.ssh,args.context)
    result=request(ssh,'check')
    if result.get('status')!='passed' or result.get('mode')!='post-bootstrap':
        raise ValueError('Restore LV requires an identity-verified post-bootstrap host')
    if args.remove and not args.apply:raise ValueError('Restore removal requires --apply --remove')
    mode='remove' if args.remove else 'apply' if args.apply else 'plan'
    payload=(ROOT/'deploy/common/backup/restore-storage.py').read_bytes()
    raw=ssh.run(['sudo','-n','python3','-',json.dumps({'context':args.context,'mode':mode})],payload=payload)
    return json.loads(raw)


def execute(args):
    if args.context!='twinfra-dev-cairo-1':raise ValueError('Use explicit --context twinfra-dev-cairo-1')
    if args.action=='restore-manifest':
        if not args.target_time:raise ValueError('restore-manifest needs --target-time with a timezone')
        print(yaml.safe_dump_all(restore_manifest(args.target_time),sort_keys=False));return 0
    report=restore_storage(args) if args.restore_drill else observe(args.context)
    print(prometheus(report) if args.prometheus else json.dumps(report,indent=2))
    return int(report['status']=='failed')


def action(args):
    try:return execute(args)
    except (ValueError,OSError,KeyError,TypeError):
        print(json.dumps({'status':'failed','reason':'Backup observation or restore precondition failed; inspect the owner runbook'}))
        return 1
