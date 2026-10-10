"""Environment-neutral manifest primitives. SPDX-License-Identifier: MIT."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def resource(kind, name, spec=None, namespace=None, api='v1', labels=None):
    obj = {'apiVersion': api, 'kind': kind, 'metadata': {'name': name}}
    if namespace:
        obj['metadata']['namespace'] = namespace
    if labels:
        obj['metadata']['labels'] = labels
    if spec is not None:
        obj['spec'] = spec
    return obj


def security():
    return {'runAsNonRoot': True, 'runAsUser': 65532, 'runAsGroup': 65532,
            'allowPrivilegeEscalation': False, 'readOnlyRootFilesystem': True,
            'capabilities': {'drop': ['ALL']}, 'seccompProfile': {'type': 'RuntimeDefault'}}
