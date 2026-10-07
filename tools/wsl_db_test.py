#!/usr/bin/env python3
"""Non-root TLS SQL/pgvector and retained-volume restart acceptance for WSL."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import time
import yaml
from wsl_platform import ROOT,NS,DB,PG_IMAGE,audit,resource
from wsl_lab import security

CLIENT='vcloud-wsl-db-client'
HOST=DB+'-rw.'+NS+'.svc.cluster.local'
CONNECTION=f'host={HOST} port=5432 dbname=vcloud user=vcloud_app sslmode=verify-full sslrootcert=/ca/ca.crt passfile=/work/.pgpass connect_timeout=5'
PASSFILE="umask 077; printf '%s:5432:vcloud:%s:%s\\n' '"+HOST+"' \"$(cat /auth/username)\" \"$(cat /auth/password)\" > /work/.pgpass; "


def manifest():
    return resource('Pod',CLIENT,{'automountServiceAccountToken':False,'securityContext':{'fsGroup':26},
        'containers':[{'name':'client','image':PG_IMAGE,'imagePullPolicy':'IfNotPresent','command':['sh','-c','sleep 36000'],
            'securityContext':security()|{'runAsUser':26,'runAsGroup':26},
            'resources':{'requests':{'cpu':'25m','memory':'64Mi'},'limits':{'cpu':'200m','memory':'128Mi'}},
            'volumeMounts':[{'name':'auth','mountPath':'/auth','readOnly':True},{'name':'ca','mountPath':'/ca','readOnly':True},{'name':'work','mountPath':'/work'}]}],
        'volumes':[{'name':'auth','secret':{'secretName':DB+'-app','defaultMode':0o440,'items':[{'key':'username','path':'username'},{'key':'password','path':'password'}]}},
                   {'name':'ca','secret':{'secretName':DB+'-ca','defaultMode':0o440,'items':[{'key':'ca.crt','path':'ca.crt'}]}},
                   {'name':'work','emptyDir':{'medium':'Memory','sizeLimit':'16Mi'}}]},NS,labels={'vcloud.io/component':'database-test'})


def kubectl(*args,capture=False):
    command=['/usr/local/bin/k3s','kubectl','--kubeconfig','/etc/vcloud-wsl/kubeconfig.yaml','--context','vcloud-wsl-local',*args]
    if capture:return subprocess.check_output(command,text=True).strip()
    subprocess.run(command,check=True)


def sql(query):
    # Password is read only inside the non-root Pod and written to memory-backed
    # mode-0600 pgpass; no password appears in Git, argv, logs or PGPASSWORD.
    return kubectl('exec','-n',NS,CLIENT,'--','sh','-ec',PASSFILE+'exec psql "$1" -v ON_ERROR_STOP=1 -qAtc "$2"','sh',CONNECTION,query,capture=True)


def main(restart=False):
    build=ROOT/'.build/wsl-platform';build.mkdir(exist_ok=True)
    obj=manifest();audit([obj]);path=build/'db-client.yaml';path.write_text(yaml.safe_dump(obj,sort_keys=False))
    subprocess.run([str(ROOT/'.tools/wsl-lab/kubeconform'),'-strict','-summary','-schema-location',str(ROOT/'module-4a/schemas/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json'),str(path)],check=True)
    kubectl('apply','--server-side','--dry-run=server','-f',str(path));kubectl('apply','--server-side','-f',str(path))
    kubectl('wait','-n',NS,'--for=condition=Ready','pod/'+CLIENT,'--timeout=120s')
    version=sql('SHOW server_version;');vector=sql("SELECT extversion FROM pg_extension WHERE extname='vector';")
    if not version.startswith('18.6') or vector!='0.8.2':raise ValueError('Unexpected database/extension version')
    if sql('SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid();')!='t':raise ValueError('SQL connection is not TLS')
    if sql("SELECT '[1,0,0]'::vector <=> '[1,0,0]'::vector;")!='0':raise ValueError('Vector distance differs')
    sql("CREATE TABLE IF NOT EXISTS local_acceptance (marker text PRIMARY KEY, embedding vector(3)); INSERT INTO local_acceptance VALUES ('local-storage-survives','[1,0,0]') ON CONFLICT (marker) DO UPDATE SET embedding=EXCLUDED.embedding;")
    if restart:
        # Only the owned instance Pod is recreated; its PVC/PV/filesystem remain.
        kubectl('delete','pod',DB+'-1','-n',NS)
        for _ in range(60):
            try:
                if sql("SELECT count(*) FROM local_acceptance WHERE marker='local-storage-survives';")=='1':break
            except subprocess.CalledProcessError:pass
            time.sleep(2)
        else:raise ValueError('Persistent marker did not recover after restart')
        kubectl('wait','-n',NS,'--for=condition=Ready','cluster/'+DB,'--timeout=180s')
    report={'status':'passed','timestampUTC':datetime.now(timezone.utc).isoformat(),'cluster':DB,'postgresql':version,
            'pgvector':vector,'tls':'sslmode=verify-full','vectorDistance':'passed',
            'persistentDataAfterInstanceRestart':'passed' if restart else 'not executed',
            'storage':'vetted finite 4 GiB ext4 Local PV; Retain','namespace':NS}
    (build/'database-acceptance.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--restart',action='store_true')
    main(parser.parse_args().restart)
