"""Offline, synthetic GPU readiness exercise; no dataset download or training claim."""
import json
import torch

if torch.cuda.device_count() != 8:
    raise SystemExit('Eight whole GPUs required for the accepted reference node')
for index in range(8):
    device = torch.device('cuda', index)
    value = torch.ones((64, 64), device=device)
    if float((value @ value).mean().item()) != 64.0:
        raise SystemExit('Synthetic GPU operation failed')
print(json.dumps({'status': 'passed', 'gpu_count': 8, 'scope': 'synthetic per-node GPU exercise'}))
