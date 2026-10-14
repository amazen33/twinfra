#!/usr/bin/env python3
"""WO-34 complete OCI before/after comparison; never execute image contents."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import types

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import build_console_image as builder
from registry_export import export_public
from platform_image_staging import validate_archive


def git(*args):
    return subprocess.check_output(['git','-C',str(ROOT),*args],text=True,encoding='utf-8').strip()


def build_pair(base, out):
    if not re.fullmatch(r'[a-f0-9]{40}', base):
        raise ValueError('Immutable comparison base required')
    old = json.loads(git('show', base + ':console/image.lock.json'))
    for path, expected in old['filesSHA256'].items():
        if path not in ('console/Dockerfile', 'tools/build_console_image.py', 'tools/platform_oci.py'):
            if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != expected:
                raise ValueError('Before-image application source differs: ' + path)
    out.mkdir(parents=True, exist_ok=True)
    # The historical builder is trusted repository source, not code from an image.
    historical = types.ModuleType('historical_console_builder')
    historical.__file__ = str(ROOT / 'tools/build_console_image.py')
    exec(compile(git('show', base + ':tools/build_console_image.py'),
                 historical.__file__, 'exec'), historical.__dict__)
    historical.ROOT = ROOT
    builder.stage_frontend()
    builder.download_inputs()
    before_base = out / 'before-base.oci.tar'
    export_public(old['base'].removeprefix('registry.twinfra.example.com/'), before_base)
    before = historical.build(before_base, out / 'before-console.oci.tar')
    if before['digest'] != old['digest']:
        raise ValueError('Historical console digest did not reproduce: '+before['digest'])
    after = builder.verify_receipt(builder.build(builder.DEFAULT_BASE, ROOT / '.build/dev-images/console.oci.tar'))
    for path, receipt in ((out / 'before-console.oci.tar', before),
                          (ROOT / '.build/dev-images/console.oci.tar', after)):
        validate_archive(path, receipt['digest'])
    return old, after, before_base


def counts(findings):
    return {level + ('WithFix' if fixed else 'WithoutFix'):
            sum(f['severity'] == level and f['fixAvailable'] == fixed for f in findings)
            for level in ('Critical', 'High') for fixed in (True, False)}


def compare(base, tools, out, prepared=False):
    import supply_chain as sc
    old = json.loads(git('show',base+':console/image.lock.json'))
    after = json.loads((ROOT/'console/image.lock.json').read_text())
    before_base = out/'before-base.oci.tar'
    if prepared:
        for path,pin in ((out/'before-console.oci.tar',old['digest']),
                         (ROOT/'.build/dev-images/console.oci.tar',after['digest']),
                         (before_base,old['base'].split('@')[1]),
                         (builder.DEFAULT_BASE,after['base'].split('@')[1])):
            validate_archive(path,pin)
    else:
        old, after, before_base = build_pair(base, out)
    rows = [('console-before', old['canonical'], out / 'before-console.oci.tar'),
            ('console-after', after['canonical'], ROOT / '.build/dev-images/console.oci.tar'),
            ('python-before', old['base'], before_base),
            ('python-after', after['base'], builder.DEFAULT_BASE)]
    plan = dict(version=1, full=True, base=None, lockfiles=[], coverage=[], images=[
        dict(target=ref, source='oci-archive:' + str(path.resolve()), digest=ref.split('@')[1],
             platform='linux/amd64', origins=[name], introduced=False) for name, ref, path in rows])
    result = sc.scan(plan, sc.verify_tools(tools), out / 'cache', out / 'scan')
    report = dict(baseCommit=base, date=sc.today().isoformat(), imageCodeExecuted=False,
                  releaseEvidence=after['releaseEvidence'], database=result['database'], images=[])
    for name, ref, path in rows:
        found = [f for f in result['findings'] if f['target'] == ref]
        report['images'].append(dict(name=name, reference=ref, counts=counts(found), findings=found,
                                     coverage='complete-oci-archive-linux-amd64'))
    sc.write(out / 'comparison.json', report)
    return int(next(row for row in report['images'] if row['name'] == 'console-after')['counts']['CriticalWithFix'] != 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True)
    parser.add_argument('--tools', type=Path)
    parser.add_argument('--build-only',action='store_true')
    parser.add_argument('--prepared',action='store_true')
    parser.add_argument('--out', type=Path, default=ROOT / '.build/wo34-console')
    args = parser.parse_args()
    if args.build_only:
        build_pair(args.base,args.out)
        return 0
    if not args.tools:parser.error('--tools is required for scanning')
    return compare(args.base, args.tools, args.out,args.prepared)


if __name__ == '__main__':
    raise SystemExit(main())
