"""Project only Amendment 15's exact seed additions from older delivery checks."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def seed_before_graphics(data):
    spec=importlib.util.spec_from_file_location('graphics_receipt',ROOT/'deploy/common/host-graphics.py')
    graphics=importlib.util.module_from_spec(spec);spec.loader.exec_module(graphics)
    result=copy.deepcopy(data)
    expected=[{'path':graphics.FILE,'permissions':'0644','content':graphics.BODY},
        {'path':graphics.STATE+'/ownership.json','permissions':'0600','content':json.dumps({
            'owner':graphics.OWNER,'sha256':hashlib.sha256(graphics.BODY.encode()).hexdigest(),'backup':None})+'\n'},
        {'path':'/usr/local/lib/twinfra/host-graphics.py','permissions':'0644',
         'content':(ROOT/'deploy/common/host-graphics.py').read_text(encoding='utf-8')}]
    for file in expected:
        if result['write_files'].count(file)!=1:raise AssertionError('Unexpected graphics seed file or content')
        result['write_files'].remove(file)
    command=['bash','-c','python3 /usr/local/lib/twinfra/host-graphics.py --bootstrap; rc=$?; if [ "$rc" -eq 20 ]; then exit 0; fi; exit "$rc"']
    if result['runcmd'].count(command)!=1:raise AssertionError('Unexpected graphics bootstrap command')
    result['runcmd'].remove(command)
    env=next(f for f in result['write_files'] if f['path']=='/etc/twinfra-host.env')
    if env['content'].count('DISABLE_NOUVEAU=true\n')!=1:raise AssertionError('Unexpected graphics flag')
    env['content']=env['content'].replace('DISABLE_NOUVEAU=true\n','')
    return result
