#!/usr/bin/env python3
"""Owned-lab negative access test; refuses pre-existing Pods and cleans up its UID."""
import json
from pathlib import Path
import subprocess
import sys
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'tools'))
from wsl_platform import PYTHON
from wsl_endpoints import check

K = ['/usr/local/bin/k3s', 'kubectl', '--kubeconfig=/etc/vcloud-wsl/kubeconfig.yaml',
     '--context=vcloud-wsl-local', '--request-timeout=15s']
NAME = 'vcloud-console-denied'


def run(args, **kwargs):
    return subprocess.run(K + args, capture_output=True, check=True, **kwargs)


def main():
    if not Path('/var/lib/vcloud-wsl/owner.json').is_file():
        raise ValueError('Owned WSL lab required')
    if run(['-n', 'hpc-compute', 'get', 'pod', NAME, '--ignore-not-found', '-o', 'name']).stdout.strip():
        raise ValueError('Refusing to replace a pre-existing test Pod')
    for service in ('ministack', 'storage-ui', 'dynamodb-admin', 'vcloud-console-shell'):
        slices = json.loads(run(['-n', 'platform-services', 'get', 'endpointslices', '-l', 'kubernetes.io/service-name=' + service, '-o', 'json']).stdout)
        if not any(e.get('conditions', {}).get('ready') is True for s in slices['items'] for e in s.get('endpoints', [])):
            raise ValueError('Target not Ready: ' + service)
    code = """import socket,urllib.request
targets=[('ministack',4566),('storage-ui',9001),('dynamodb-admin',8081),('vcloud-console-shell',3000)]
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
for name,port in targets:
    host=name+'.platform-services.svc.cluster.local'
    socket.gethostbyname(host) # DNS must work; failure isn't deny-all acceptance.
    try:
        opener.open('http://'+host+':'+str(port)+'/healthz',timeout=2)
    except (TimeoutError,urllib.error.URLError) as err:
        if isinstance(err,urllib.error.URLError) and not isinstance(err.reason,TimeoutError): raise
        print('PASS: unauthorized cross-namespace access blocked: '+name,flush=True)
    else: raise RuntimeError('Unauthorized service reachable: '+name)
"""
    sc = {'runAsNonRoot': True, 'runAsUser': 65532, 'runAsGroup': 65532, 'allowPrivilegeEscalation': False,
          'capabilities': {'drop': ['ALL']}, 'seccompProfile': {'type': 'RuntimeDefault'}, 'readOnlyRootFilesystem': True}
    run_id = uuid.uuid4().hex
    pod = {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {'name': NAME, 'namespace': 'hpc-compute',
        'labels': {'vcloud.io/test-run': run_id}}, 'spec': {'automountServiceAccountToken': False, 'restartPolicy': 'Never',
        'activeDeadlineSeconds': 40, 'securityContext': {'runAsNonRoot': True, 'runAsUser': 65532, 'seccompProfile': {'type': 'RuntimeDefault'}},
        'containers': [{'name': 'probe', 'image': PYTHON, 'imagePullPolicy': 'IfNotPresent', 'command': ['python', '-c', code],
            'securityContext': sc, 'resources': {'requests': {'cpu': '25m', 'memory': '32Mi'}, 'limits': {'cpu': '100m', 'memory': '64Mi'}}}]}}
    check([pod])
    created = json.loads(run(['create', '-f', '-', '-o', 'json'], input=json.dumps(pod).encode()).stdout)
    try:
        run(['-n', 'hpc-compute', 'wait', '--for=jsonpath={.status.phase}=Succeeded', '--timeout=55s', 'pod/' + NAME])
        print(run(['-n', 'hpc-compute', 'logs', NAME]).stdout.decode().strip())
    finally:
        found = json.loads(run(['-n', 'hpc-compute', 'get', 'pod', NAME, '-o', 'json']).stdout)
        if found['metadata']['uid'] == created['metadata']['uid'] and found['metadata']['labels']['vcloud.io/test-run'] == run_id:
            run(['-n', 'hpc-compute', 'delete', 'pod', NAME, '--wait=false'])


if __name__ == '__main__':
    main()
