#!/usr/bin/env python3
"""Trusted final promotion gate, baked into the image. JSON is a valid YAML document."""
import json
import copy
from pathlib import Path
import re
import sys


def validate(obj, template=None):
    if (obj.get('apiVersion'), obj.get('kind'), obj.get('metadata', {}).get('name'),
        obj.get('metadata', {}).get('namespace')) != ('serving.knative.dev/v1', 'Service', 'vcloud-api', 'workload-apps'):
        raise ValueError('Only the dedicated vcloud-api Knative workload may be promoted')
    spec = obj['spec']['template']['spec']
    if spec.get('serviceAccountName') != 'vcloud-api' or spec.get('automountServiceAccountToken') is not False:
        raise ValueError('Workload identity/token drift')
    if any(spec.get(k) for k in ('hostNetwork','hostPID','hostIPC','volumes','initContainers')):
        raise ValueError('Workload host access, volume or init-container drift')
    if len(spec['containers']) != 1: raise ValueError('Unexpected container')
    c = spec['containers'][0]
    if c['name'] != 'api' or not re.fullmatch(r'registry\.vcloud\.example\.com/vcloud/api:git-[0-9a-f]{40}@sha256:[0-9a-f]{64}', c['image']):
        raise ValueError('Wrong registry, source tag or digest')
    context = c['securityContext']
    if not (context.get('runAsNonRoot') is True and context.get('runAsUser') == 65532 and
            context.get('runAsGroup') == 65532 and context.get('allowPrivilegeEscalation') is False and
            context.get('readOnlyRootFilesystem') is True and context.get('privileged',False) is False and
            context.get('capabilities') == {'drop':['ALL']} and context.get('seccompProfile') == {'type':'RuntimeDefault'}):
        raise ValueError('Workload privilege/security drift')
    if c.get('imagePullPolicy') != 'IfNotPresent' or c.get('command') or c.get('args'):
        raise ValueError('Workload execution override')
    if c['resources'] != {'requests':{'cpu':'100m','memory':'128Mi'},'limits':{'cpu':'1','memory':'256Mi'}}:
        raise ValueError('Workload resource drift')
    annotations = obj['metadata']['annotations']
    revision = annotations.get('vcloud.io/source-revision','')
    if not re.fullmatch(r'[0-9a-f]{40}',revision) or ':git-'+revision+'@' not in c['image']:
        raise ValueError('Source attribution drift')
    if template is None:
        template_path=Path(__file__).with_name('workload-template.yaml')
        if not template_path.exists(): template_path=Path(__file__).resolve().parents[1]/'gitops/workload.yaml'
        template=json.loads(template_path.read_text())
    actual, expected=copy.deepcopy(obj),copy.deepcopy(template)
    for item in (actual,expected):
        item['metadata']['annotations'].pop('vcloud.io/source-revision',None)
        item['spec']['template']['spec']['containers'][0].pop('image',None)
    if actual!=expected: raise ValueError('Only image and source-revision fields may change during promotion')
    return True


if __name__ == '__main__':
    validate(json.loads(Path(sys.argv[1]).read_text()))
    print('Final promotion workload contract passed')
