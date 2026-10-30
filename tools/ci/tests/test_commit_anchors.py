"""WO-40 10g/10h: executable evidence must survive a squash merge."""
import ast
from pathlib import Path
import re
import shlex
import subprocess
import unittest

import yaml

ROOT=Path(__file__).resolve().parents[3]
RETIRED={
    'tools/ci/activate_r12.py': (
        'retired one-shot R12 activation tool; refuses to run', 'WO-40 Amendment 10h'),
}
SHA=re.compile(r'^([a-f0-9]{40})(?=$|[:^~])')


def tracked():
    return subprocess.check_output(['git','-C',str(ROOT),'ls-files','--','tests','tools','.github/workflows'],
                                   text=True,encoding='utf-8').splitlines()


class Sources:
    """Read literals and aliases as data; never import or execute scanned code."""
    def __init__(self, sources):
        self.sources=sources
        self.trees={p:ast.parse(text,filename=p) for p,text in sources.items() if p.endswith('.py')}
        self.modules={Path(p).stem:p for p in self.trees}
        self.bindings={p:{} for p in self.trees}
        for path,tree in self.trees.items():
            for node in ast.walk(tree):
                if isinstance(node,ast.Assign):
                    for target in node.targets:
                        if isinstance(target,ast.Name):self.bindings[path][target.id]=(path,node.value)
                elif isinstance(node,ast.Import):
                    for item in node.names:
                        if item.name in self.modules:
                            self.bindings[path][item.asname or item.name]=(self.modules[item.name],None)
                elif isinstance(node,ast.ImportFrom) and node.module in self.modules:
                    other=self.modules[node.module]
                    for item in node.names:
                        self.bindings[path][item.asname or item.name]=(other,ast.Name(id=item.name))

    def value(self, path, node, seen=frozenset()):
        if isinstance(node,ast.Constant):return node.value if isinstance(node.value,str) else None
        if isinstance(node,(ast.List,ast.Tuple)):
            return [self.value(path,item,seen) for item in node.elts]
        if isinstance(node,ast.Name):
            key=(path,node.id)
            if key in seen:return None
            other,value=self.bindings[path].get(node.id,(path,None))
            return self.value(other,value,seen|{key}) if value is not None else None
        if isinstance(node,ast.Attribute) and isinstance(node.value,ast.Name):
            other,value=self.bindings[path].get(node.value.id,(None,None))
            if other and value is None:return self.value(other,ast.Name(id=node.attr),seen)
        if isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Add,ast.Div)):
            left,right=self.value(path,node.left,seen),self.value(path,node.right,seen)
            if isinstance(node.op,ast.Div):return right
            if isinstance(left,str):return left+(right if isinstance(right,str) else '')
            return right
        if isinstance(node,ast.JoinedStr):
            parts=[self.value(path,item.value if isinstance(item,ast.FormattedValue) else item,seen)
                   for item in node.values]
            return ''.join(item for item in parts if isinstance(item,str))
        return None

    def references(self):
        refs={}
        for path,tree in self.trees.items():
            if path in RETIRED:continue
            for node in ast.walk(tree):
                args=None
                if isinstance(node,(ast.List,ast.Tuple)):
                    values=self.value(path,node)
                    if values and values[0]=='git':args=values[1:]
                elif isinstance(node,ast.Call) and (
                        isinstance(node.func,ast.Name) and node.func.id=='git' or
                        isinstance(node.func,ast.Attribute) and node.func.attr=='git'):
                    args=[self.value(path,item) for item in node.args]
                elif isinstance(node,ast.Call) and node.args and getattr(node.func,'attr','') in (
                        'run','check_output','check_call','Popen','call','system'):
                    command=self.value(path,node.args[0])
                    if isinstance(command,str):
                        values=shlex.split(command)
                        if values and values[0]=='git':args=values[1:]
                if args is None:continue
                for index,item in enumerate(args):
                    if item in ('show','cat-file'):
                        for value in args[index+1:]:
                            match=SHA.match(value) if isinstance(value,str) else None
                            if match:refs.setdefault(match[1],set()).add((path,node.lineno))
        for path,text in self.sources.items():
            if path.endswith('.py') or path in RETIRED:continue
            for number,line in enumerate(text.splitlines(),1):
                if line.lstrip().startswith(('#','//')):continue
                for match in re.finditer(r'''\bgit\b[^\n]*?\b(?:show|cat-file)\s+(?:-\S+\s+)*["']?([a-f0-9]{40})(?=$|[\s:"'^~])''',line):
                    refs.setdefault(match[1],set()).add((path,number))
        return refs

    def activation_calls(self):
        failures=[]
        commands={'run','check_call','check_output','Popen','call','system','execv','execve'}
        for path,tree in self.trees.items():
            for node in ast.walk(tree):
                if not isinstance(node,ast.Call):continue
                name=node.func.id if isinstance(node.func,ast.Name) else getattr(node.func,'attr','')
                values=[self.value(path,arg) for arg in node.args]
                strings=[]
                for value in values:
                    strings.extend(value if isinstance(value,list) else [value])
                if name in commands and any(isinstance(v,str) and (
                        'activate_r12.py' in v or 'tools.ci.activate_r12' in v) for v in strings):
                    failures.append((path,node.lineno))
                if name=='activate' and isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name):
                    module=self.bindings[path].get(node.func.value.id,(None,None))[0]
                    if module=='tools/ci/activate_r12.py':failures.append((path,node.lineno))
                if isinstance(node.func,ast.Name):
                    module,value=self.bindings[path].get(node.func.id,(None,None))
                    if module=='tools/ci/activate_r12.py' and isinstance(value,ast.Name) and value.id=='activate':
                        failures.append((path,node.lineno))
        return failures


def unreachable(refs, reachable):
    return {sha:locations for sha,locations in refs.items()
            if not all(reachable(sha,ref) for ref in ('HEAD','origin/main'))}


class CommitAnchors(unittest.TestCase):
    def test_only_explicit_retired_activation_exemption(self):
        self.assertEqual(RETIRED,{'tools/ci/activate_r12.py':(
            'retired one-shot R12 activation tool; refuses to run','WO-40 Amendment 10h')})

    def test_all_executable_commit_anchors_are_main_ancestors(self):
        sources={p:(ROOT/p).read_text(encoding='utf-8') for p in tracked()
                 if p.endswith(('.py','.ps1','.sh','.js','.mjs'))}
        refs=Sources(sources).references()
        self.assertTrue(refs,'Commit-anchor scan must inspect existing historical receipts')
        def reachable(sha,ref):
            return subprocess.run(['git','-C',str(ROOT),'merge-base','--is-ancestor',sha,ref],
                                  stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
        self.assertEqual(unreachable(refs,reachable),{},'Git evidence requires a commit reachable from HEAD and main')

    def test_literals_constants_imports_and_cat_file_are_detected(self):
        sha='f'*40
        fixtures={
            'tools/source.py':f'BASE={sha!r}\n',
            'tests/example.py':f'''import subprocess
import source as evidence
from source import BASE as ORIGINAL
subprocess.check_output(['git','show','{sha}:file'])
subprocess.run(['git','show',evidence.BASE+':file'])
subprocess.run(['git','cat-file','-e',ORIGINAL+'^{{commit}}'])
git('show',ORIGINAL+':file')
subprocess.run('git cat-file -e {sha}^{{commit}}',shell=True)
'''}
        fixtures['tools/example.ps1']=f'git show {sha}:file\n'
        refs=Sources(fixtures).references()
        self.assertEqual(len(refs[sha]),6)
        self.assertEqual(unreachable(refs,lambda commit,ref:ref=='HEAD'),refs)
        self.assertEqual(unreachable(refs,lambda commit,ref:True),{})

    def test_documentation_sha_is_not_an_executable_dependency(self):
        sha='f'*40
        self.assertEqual(Sources({'tests/context.py':f"assert '{sha}' in note\n"}).references(),{})

    def test_retired_entry_point_only_raises_nonzero(self):
        tree=ast.parse((ROOT/'tools/ci/activate_r12.py').read_text())
        entry=next(n for n in tree.body if isinstance(n,ast.If) and
                   ast.unparse(n.test)=="__name__ == '__main__'")
        self.assertEqual(len(entry.body),1)
        statement=entry.body[0]
        self.assertIsInstance(statement,ast.Raise)
        self.assertIsInstance(statement.exc,ast.Call)
        self.assertEqual(ast.unparse(statement.exc.func),'SystemExit')
        self.assertIsInstance(statement.exc.args[0],ast.Constant)
        with self.assertRaises(SystemExit) as caught:
            exec(compile(ast.Module(body=entry.body,type_ignores=[]),'<retired-entrypoint>','exec'),{})
        self.assertTrue(caught.exception.code)
        for text in ('Retired after the R12 activation','security/security-wave-2026-10-approval.json','WO-40 Amendment 10h'):
            self.assertIn(text,str(caught.exception.code))

    def test_no_workflow_or_test_invokes_retired_activation(self):
        paths=tracked()
        sources={p:(ROOT/p).read_text(encoding='utf-8') for p in paths if p.endswith('.py')}
        calls=Sources(sources).activation_calls()
        self.assertEqual([call for call in calls if call[0].startswith(('tests/','tools/ci/tests/'))],[])
        for path in paths:
            if not path.startswith('.github/workflows/') or not path.endswith(('.yml','.yaml')):continue
            workflow=yaml.safe_load((ROOT/path).read_text())
            for job in workflow.get('jobs',{}).values():
                for step in job.get('steps',[]):
                    command='\n'.join(line for line in step.get('run','').splitlines()
                                      if not line.lstrip().startswith('#'))
                    self.assertNotRegex(command,r'activate_r12(?:\.py|\b)',path)

    def test_retired_invocation_detection_keeps_pure_helper_imports(self):
        base='import activate_r12 as activation\n'
        harmless=base+"activation.approved_batch(current,approved)\n"
        self.assertEqual(Sources({'tests/example.py':harmless}).activation_calls(),[])
        for call in ("subprocess.run(['python','tools/ci/activate_r12.py'])",
                     "subprocess.run(['python','-m','tools.ci.activate_r12'])",
                     'activation.activate(report)',
                     'from activate_r12 import activate as rerun\nrerun(report)',
                     "command=['python','tools/ci/activate_r12.py']\nsubprocess.run(command)"):
            with self.subTest(call=call):
                sources={'tests/example.py':base+call,'tools/ci/activate_r12.py':'pass\n'}
                self.assertTrue(Sources(sources).activation_calls())


if __name__=='__main__':unittest.main()
