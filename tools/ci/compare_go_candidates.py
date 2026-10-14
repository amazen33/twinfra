#!/usr/bin/env python3
"""Data-only P2 image comparisons; this command never promotes a candidate."""
import argparse
import json
from pathlib import Path
from compare_console_images import scan_projection, counts
from registry_export import export_public
import supply_chain as sc

ROWS = [
    ('argocd', 'before', 'quay.io/argoproj/argocd@sha256:dd3f47d5a5e4da563a7a398506e892481b358a7cec50abdf320c71aa55904bfa'),
    ('argocd', 'after', 'quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518'),
    ('coredns', 'before', 'registry.k8s.io/coredns/coredns@sha256:e7e6440cfd1e919280958f5b5a6ab2b184d385bba774c12ad2a9e1e4183f90d9'),
    ('coredns', 'after', 'registry.k8s.io/coredns/coredns@sha256:7efd3c635b03efd68c4e8398fc45f0d993d0e9ab016f72c1cefb0fd6d01aa286'),
    ('etcd', 'before', 'registry.k8s.io/etcd@sha256:397189418d1a00e500c0605ad18d1baf3b541a1004d768448c367e48071622e5'),
    ('etcd', 'after', 'registry.k8s.io/etcd@sha256:5ed4e32061aa061f970d6500629213e8579ef17571dcf9789074966acb9afad1'),
]


def severe(values):
    return {(v['package'], v['vulnerability'], v['severity'])
            for v in values if v['severity'] in ('Critical', 'High')}


def improvement(before, after):
    a, b = severe(before), severe(after)
    return dict(noNewCriticalHigh=not (b - a), netImprovement=not (b - a) and bool(a - b),
                removed=[list(v) for v in sorted(a - b)], introduced=[list(v) for v in sorted(b - a)])


def compare(tools, out):
    out.mkdir(parents=True, exist_ok=True)
    images, bindings = [], {}
    for component, side, ref in ROWS:
        name = component + '-' + side
        archive = out / (name + '.oci.tar')
        export_public(ref, archive)
        projection = out / (name + '.scan.oci.tar')
        bindings[name] = scan_projection(archive, projection, ref.split('@')[1])
        images.append(dict(target=ref, source='oci-archive:' + str(projection.resolve()),
                           digest=ref.split('@')[1], platform='linux/amd64', origins=[name], introduced=False))
    plan = dict(version=1, full=True, base=None, lockfiles=[], coverage=[], images=images)
    result = sc.scan(plan, sc.verify_tools(tools), out / 'cache', out / 'scan')
    report = dict(date=sc.today().isoformat(), database=result['database'],
                  applicationCodeExecuted=False, promotionPerformed=False, images=[], components={})
    findings = {}
    for component, side, ref in ROWS:
        name = component + '-' + side
        found = [v for v in result['findings'] if v['target'] == ref]
        findings[name] = found
        report['images'].append(dict(name=name, reference=ref, verifiedAmd64Digest=bindings[name],
                                    coverage='complete-oci-archive-linux-amd64', counts=counts(found), findings=found))
    for component in ('argocd', 'coredns', 'etcd'):
        report['components'][component] = improvement(findings[component + '-before'], findings[component + '-after'])
    sc.write(out / 'comparison.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tools', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    compare(args.tools, args.out.resolve())
