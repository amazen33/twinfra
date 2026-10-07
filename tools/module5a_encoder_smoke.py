#!/usr/bin/env python3
"""Offline acceptance of staged CPU weights; no database, GPU or cluster calls."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'module-5a/rag'))
from pipeline import config,encoder


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    value=config(ROOT/'module-5a/config/rag.yaml')
    # This host-only test accepts the explicitly supplied staging receipt. It
    # never changes the public config, feature gate or application PVC owner.
    value['embeddings']['path']=str(args.model.resolve())
    receipt=args.model/'vcloud-model.json'
    digest=hashlib.sha256(receipt.read_bytes()).hexdigest()
    value['embeddings']['manifestSHA256']=digest
    import torch
    torch.set_num_threads(2)
    model=encoder(value)
    texts=['Kubernetes orchestrates container workloads.',
           'Kubernetes manages containers and workloads.',
           'Bananas are yellow fruit.']
    vectors=model.embed_documents(texts)
    if len(vectors)!=3 or any(len(v)!=384 for v in vectors):raise ValueError('Vector shape mismatch')
    norms=[math.sqrt(sum(x*x for x in v)) for v in vectors]
    if any(abs(norm-1)>1e-5 for norm in norms):raise ValueError('Unnormalized encoder output')
    similar=sum(x*y for x,y in zip(vectors[0],vectors[1]))
    unrelated=sum(x*y for x,y in zip(vectors[0],vectors[2]))
    if similar<=unrelated:raise ValueError('Semantic ordering failed')
    query=model.embed_query(texts[0])
    if max(abs(x-y) for x,y in zip(query,vectors[0]))>1e-5:raise ValueError('Query/document encoder mismatch')
    report={'status':'passed','scope':'real offline CPU encoder only; no database/GPU/end-to-end RAG',
            'repository':value['embeddings']['repository'],'revision':value['embeddings']['revision'],
            'manifestSHA256':digest,'dimensions':384,'vectors':len(vectors),
            'normalized':True,'semanticOrdering':True,'queryDocumentAgreement':True,
            'relatedCosine':round(similar,6),'unrelatedCosine':round(unrelated,6),
            'torchVersion':torch.__version__}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(report))


if __name__=='__main__':main()
