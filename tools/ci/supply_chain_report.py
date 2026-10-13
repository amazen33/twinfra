#!/usr/bin/env python3
"""Trusted main-only issue writer; stdlib only, no scanner or dependency execution."""
import argparse
import base64
import gzip
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request

REPOSITORY='amazen33/twinfra'
TITLE='Supply-chain scan: open findings'
WATCH_TITLE='Upstream updates available'


def request(url,token,payload=None,method=None):
    headers={'Authorization':'Bearer '+token,'User-Agent':'Twinfra-supply-chain-report','Accept':'application/vnd.github+json'}
    value=urllib.request.Request(url,headers=headers,method=method,
                                 data=json.dumps(payload).encode() if payload is not None else None)
    with urllib.request.urlopen(value,timeout=60) as response:return json.load(response)


def publish(report,title,url,token):
    if title not in (TITLE,WATCH_TITLE):raise ValueError('Unexpected issue title')
    if not re.fullmatch(r'https://github.com/amazen33/twinfra/actions/runs/[0-9]+',url):raise ValueError('Invalid run URL')
    body=report['markdown']
    if title==TITLE:
        state=report['firstSeen']
        if not isinstance(state,dict) or any(not re.fullmatch(r'[a-f0-9]{64}',key) for key in state):
            raise ValueError('Invalid first-seen state')
        tail='\n<!-- twinfra-supply-chain-state:'+base64.b64encode(gzip.compress(
            json.dumps(state,sort_keys=True,separators=(',',':')).encode(),mtime=0)).decode()+' -->\n'
    else:tail=''
    budget=64000-len(tail)-len(url)-100
    if budget<1000:raise ValueError('Tracking state exceeds issue limit')
    if len(body)>budget:body=body[:budget]+'\nFull findings are in the run artifact.\n'
    body=body+'\nRun: '+url+'\n'+tail
    # Labels are issue metadata. Creation is deferred to this main-only issues:write job.
    label_url=f'https://api.github.com/repos/{REPOSITORY}/labels'
    try:request(label_url+'/security',token)
    except urllib.error.HTTPError as error:
        if error.code!=404:raise
        request(label_url,token,dict(name='security',color='b60205',description='Supply-chain vulnerability findings'),'POST')
    matches=[];endpoint=f'https://api.github.com/repos/{REPOSITORY}/issues'
    for page in range(1,11):
        values=request(endpoint+f'?state=all&per_page=100&page={page}',token)
        matches.extend(v for v in values if v.get('title')==title and 'pull_request' not in v)
        if len(values)<100:break
    if len(matches)>1:raise ValueError('Duplicate tracking issues; owner must resolve')
    payload=dict(title=title,body=body,labels=['security'],state='open')
    value=request(endpoint+'/'+str(matches[0]['number']) if matches else endpoint,token,payload,
                  'PATCH' if matches else 'POST')
    return value['html_url']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True);parser.add_argument('--title',required=True)
    parser.add_argument('--run-url',required=True);args=parser.parse_args()
    if os.environ.get('GITHUB_REF')!='refs/heads/main' or os.environ.get('GITHUB_REPOSITORY')!=REPOSITORY:
        raise ValueError('Issue reporting is restricted to trusted main in Twinfra')
    print(publish(json.loads(args.report.read_text(encoding='utf-8')),args.title,args.run_url,os.environ['GH_TOKEN']))


if __name__=='__main__':main()
