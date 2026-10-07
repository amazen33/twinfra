#!/usr/bin/env python3
"""Explicit connected model staging; inference Pods never download weights."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

MODELS={
    'embeddings':('sentence-transformers/all-MiniLM-L6-v2','1110a243fdf4706b3f48f1d95db1a4f5529b4d41'),
    'inference':('deepseek-ai/DeepSeek-R1-Distill-Qwen-32B','711ad2ea6aa40cfca18895e8aca02ab92df1a746')}


def stage(model,destination,cache):
    from huggingface_hub import snapshot_download
    repository,revision=MODELS[model]
    # Refuse adoption or modification of an existing corpus/model directory.
    if destination.exists():raise ValueError('Use a new model staging directory')
    snapshot=Path(snapshot_download(repo_id=repository,revision=revision,cache_dir=str(cache),token=False,
        allow_patterns=['*.json','*.safetensors','*.txt','*.model','*.tiktoken'],
        ignore_patterns=['onnx/*','openvino/*']))
    if snapshot.name!=revision:raise ValueError('Unexpected model snapshot identity')
    destination.mkdir(parents=True)
    for path in snapshot.rglob('*'):
        if path.is_file():
            target=destination/path.relative_to(snapshot);target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(path,target) # Materialize hub-cache links; no symlinks in PVC artifacts.
    files={p.relative_to(destination).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
        for p in destination.rglob('*') if p.is_file()}
    if not any(name.endswith('.safetensors') for name in files):raise ValueError('No safe model weights staged')
    receipt={'repository':repository,'revision':revision,'filesSHA256':files}
    raw=(json.dumps(receipt,indent=2,sort_keys=True)+'\n').encode();(destination/'vcloud-model.json').write_bytes(raw)
    print(json.dumps({'model':model,'repository':repository,'revision':revision,
        'manifestSHA256':hashlib.sha256(raw).hexdigest(),'files':len(files)}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('model',choices=MODELS)
    parser.add_argument('--destination',type=Path,required=True);parser.add_argument('--cache',type=Path,required=True)
    args=parser.parse_args();stage(args.model,args.destination,args.cache)
