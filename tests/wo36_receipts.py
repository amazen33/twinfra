"""Exact pre-WO-36 delivery projections, plus bounded current-source checks.

Older delivery receipts retain their original scope. Only the explicit WO-36
site metadata and network hooks are projected out; every other byte/AST node
must still match the merged baseline. New behavior runs in test_host_network.
"""
import ast
import copy
from pathlib import Path
import re
import subprocess
import yaml

ROOT=Path(__file__).resolve().parents[1]
BASE='7e5d017'
SITE={'subnet':'192.168.1.0/24','gateway':'192.168.1.1','dns':['192.168.1.1','1.1.1.1'],
      'fixedRange':['192.168.1.2','192.168.1.99'],'dhcpRange':['192.168.1.100','192.168.1.254'],
      'host':{'name':'twinfra-dev-cairo-1','interface':'eno1','address':'192.168.1.3/24','mac':'64:00:6a:86:5c:4f'},
      'futureControlPlaneVIP':'192.168.1.10','futureNodeAddresses':['192.168.1.11','192.168.1.12','192.168.1.13']}


def receipt(name):
    old=subprocess.check_output(['git','-C',str(ROOT),'show',BASE+':'+name])
    current=(ROOT/name).read_text(encoding='utf-8')
    if name=='deploy/environments/dev/cairo-1/services/workloads.yaml':
        objects=list(yaml.safe_load_all(current));changed=[]
        for obj in objects:
            if obj['kind']=='Deployment' and obj['metadata']['name'] in ('twinfra-console','twinfra-gateway','twinfra-ministack'):
                if obj['spec']['strategy']!={'type':'RollingUpdate','rollingUpdate':{'maxUnavailable':0,'maxSurge':1}}:
                    raise AssertionError('Unexpected WO-36 stateless strategy')
                changed.append(obj['metadata']['name']);obj['spec']['strategy']={'type':'Recreate'}
        if len(changed)!=3 or yaml.safe_dump_all(objects,sort_keys=False).encode()!=old:
            raise AssertionError('Dev services changed beyond the three approved strategies')
        return old
    if name=='vcloud-ssot.yaml':
        data=yaml.safe_load(current)
        if data.pop('siteNetwork')!=SITE:raise AssertionError('WO-36 address plan differs')
        stripped,count=re.subn(r'(?ms)^siteNetwork:\n.*?(?=^addressPlan:)', '',current)
        if count!=1 or stripped.encode()!=old:raise AssertionError('SSoT changed beyond exact WO-36 site metadata')
        return old
    before=ast.parse(old);after=ast.parse(current)
    previous={n.name:n for n in before.body if isinstance(n,ast.FunctionDef)}
    if name=='deploy/common/host-admin.py':
        after.body=[n for n in after.body if getattr(n,'name',None) not in ('network_agent','network_warnings')]
        for node in after.body:
            if getattr(node,'name',None)=='evaluate':
                node.body=[n for n in node.body if not (isinstance(n,ast.If) and ast.unparse(n.test)=="'networkIntegrity' in state")]
            if getattr(node,'name',None)=='dispatch':
                node.body=[n for n in node.body if not (isinstance(n,ast.If) and ast.unparse(n.test)=="action.startswith('network-')")]
                for i,n in enumerate(node.body):
                    if isinstance(n,ast.If) and ast.unparse(n.test)=="action == 'check'":
                        node.body[i]=copy.deepcopy(next(n for n in previous['dispatch'].body if isinstance(n,ast.If) and ast.unparse(n.test)=="action == 'check'"))
    elif name=='tools/platform_host.py':
        after.body=[n for n in after.body if getattr(n,'name',None)!='network']
        for node in after.body:
            if getattr(node,'name',None)=='request':
                node.body=[n for n in node.body if not (isinstance(n,ast.If) and ast.unparse(n.test)=="action == 'check' or action.startswith('network-')")]
            if getattr(node,'name',None) in ('execute','action'):
                if node.args.args[-1].arg!='rollback':raise AssertionError('Unknown host action signature')
                node.args.args.pop();node.args.defaults.pop()
                if node.name=='execute':node.body=[n for n in node.body if not (isinstance(n,ast.If) and ast.unparse(n.test)=="action == 'host-network'")]
                else:
                    for call in ast.walk(node):
                        if isinstance(call,ast.Call) and isinstance(call.func,ast.Name) and call.func.id=='execute':
                            if ast.unparse(call.args.pop())!='rollback':raise AssertionError('Unknown host dispatch argument')
    else:raise AssertionError('Not a WO-36 receipt path')
    if ast.dump(before)!=ast.dump(after):raise AssertionError('Host source changed outside WO-36 hooks: '+name)
    return old
