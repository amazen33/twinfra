#!/usr/bin/env python3
"""Bounded growth of one CNPG Cluster from consecutive real metrics samples.

CNPG owns Pod changes. This service account can patch only the named Cluster.
Requests equal limits, growth stops at 1 CPU/1 GiB, and shrinking is disabled.
"""
from datetime import datetime,timezone
from decimal import Decimal,ROUND_CEILING
import json
import os
from pathlib import Path
import re
import ssl
import time
from urllib.request import Request,build_opener,HTTPSHandler,HTTPRedirectHandler


def quantity(value):
    match=re.fullmatch(r'(\d+(?:\.\d+)?)(n|u|m|Ki|Mi|Gi|K|M|G)?',str(value))
    if not match:raise ValueError('Invalid resource quantity')
    units={'':1,'n':Decimal('0.000000001'),'u':Decimal('0.000001'),'m':Decimal('0.001'),
           'Ki':2**10,'Mi':2**20,'Gi':2**30,'K':10**3,'M':10**6,'G':10**9}
    return Decimal(match[1])*units[match[2] or '']


def plan(cluster,samples,now):
    spec,status=cluster['spec'],cluster.get('status',{})
    if (spec.get('instances')!=1 or status.get('readyInstances')!=1 or
        status.get('phase')!='Cluster in healthy state' or not status.get('currentPrimary') or
        status.get('currentPrimary')!=status.get('targetPrimary') or cluster['metadata'].get('deletionTimestamp')):
        return None,'Cluster not healthy/stable'
    last=cluster['metadata'].get('annotations',{}).get('vcloud.io/resources-last-scaled')
    if last and now-datetime.fromisoformat(last.replace('Z','+00:00')).timestamp()<1800:
        return None,'cooldown'
    current=spec['resources']
    if current.get('requests')!=current.get('limits') or set(current['requests'])!={'cpu','memory'}:
        return None,'Unexpected resource policy'
    if len(samples)!=3:return None,'Three consecutive samples required'
    stamps=[datetime.fromisoformat(sample['timestamp'].replace('Z','+00:00')).timestamp() for sample in samples]
    if any(b<=a for a,b in zip(stamps,stamps[1:])):return None,'Metrics did not advance'
    wanted=dict(current['requests']);changed=False
    for resource,low,high in [('cpu',Decimal('.5'),Decimal('1')),('memory',Decimal(512*2**20),Decimal(1024*2**20))]:
        previous=quantity(current['requests'][resource])
        if not low<=previous<=high:return None,'Resource outside local bounds'
        values=[]
        for sample in samples:
            if sample['metadata']['name']!=status['currentPrimary']:return None,'Metrics target changed'
            stamp=datetime.fromisoformat(sample['timestamp'].replace('Z','+00:00')).timestamp()
            if not 0<=now-stamp<=120:return None,'Stale metrics'
            pg=[c for c in sample['containers'] if c['name']=='postgres']
            if len(pg)!=1:return None,'Postgres metrics absent'
            values.append(quantity(pg[0]['usage'][resource]))
        if all(value/previous>Decimal('.85') for value in values):
            target=min(high,previous*Decimal('1.25'))
            if target>previous:
                changed=True
                unit=1000 if resource=='cpu' else Decimal(1)/2**20
                wanted[resource]=str((target*unit).to_integral_value(rounding=ROUND_CEILING))+('m' if resource=='cpu' else 'Mi')
    if not changed:return None,'No sustained pressure or at maximum'
    annotations=cluster['metadata'].get('annotations',{})|{'vcloud.io/resources-last-scaled':datetime.fromtimestamp(now,timezone.utc).isoformat()}
    return [{'op':'test','path':'/metadata/resourceVersion','value':cluster['metadata']['resourceVersion']},
            {'op':'test','path':'/spec/resources','value':current},
            {'op':'add','path':'/spec/resources','value':{'requests':wanted,'limits':wanted}},
            {'op':'add','path':'/metadata/annotations','value':annotations}],'bounded resource growth'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('API redirect forbidden')


def main():
    token=Path('/var/run/secrets/kubernetes.io/serviceaccount/token').read_text().strip()
    ctx=ssl.create_default_context(cafile='/var/run/secrets/kubernetes.io/serviceaccount/ca.crt')
    opener=build_opener(HTTPSHandler(context=ctx),NoRedirect())
    base='https://'+os.environ['KUBERNETES_SERVICE_HOST']+':'+os.environ['KUBERNETES_SERVICE_PORT_HTTPS']
    name='vcloud-wsl-postgres';namespace='platform-services'
    path=f'/apis/postgresql.cnpg.io/v1/namespaces/{namespace}/clusters/{name}'
    def request(uri,patch=None):
        headers={'Authorization':'Bearer '+token}
        if patch is not None:headers['Content-Type']='application/json-patch+json'
        req=Request(base+uri,data=None if patch is None else json.dumps(patch).encode(),headers=headers,method='GET' if patch is None else 'PATCH')
        with opener.open(req,timeout=10) as response:return json.load(response)
    cluster=request(path);primary=cluster.get('status',{}).get('currentPrimary')
    if not primary:print('No primary; no change');return
    samples=[]
    for index in range(3):
        if index:time.sleep(16)
        samples.append(request(f'/apis/metrics.k8s.io/v1beta1/namespaces/{namespace}/pods/{primary}'))
    fresh=request(path)
    patch,reason=plan(fresh,samples,time.time());print(reason)
    if patch:
        result=request(path,patch)
        print(json.dumps({'cluster':name,'resources':result['spec']['resources']}))


if __name__=='__main__':main()
