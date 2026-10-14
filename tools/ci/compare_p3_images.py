#!/usr/bin/env python3
"""WO-34 complete patch comparison and all-Go data inspection for P3."""
import argparse
import json
from pathlib import Path
from compare_console_images import scan_projection,counts
from registry_export import export_public
import supply_chain as sc
from triage_go_image import triage

ROWS=[
 ('ministack-before','docker.io/ministackorg/ministack@sha256:11d7308bfc75029d55625b9525e84a2401431ed1ff2148c6311800ff5009ae9c'),
 ('ministack-after','docker.io/ministackorg/ministack@sha256:451a0cc80a4f464e1c2d2f77fbb40ac37d01902d58ca3630ac5eaea9c92f12da'),
 ('pause-before','registry.k8s.io/pause@sha256:278fb9dbcca9518083ad1e11276933a2e96f23de604a3a08cc3c80002767d24c'),
 ('pause-after','registry.k8s.io/pause@sha256:f548e0e8e3dc1896ca956272154dde3314e8cc4fde0a57577ee9fa1c63f5baf4')]


def compare(tools,scanner,out):
 out.mkdir(parents=True,exist_ok=True);images=[];bindings={}
 for name,ref in ROWS:
  archive=out/(name+'.oci.tar');export_public(ref,archive)
  projection=out/(name+'.scan.oci.tar');bindings[name]=scan_projection(archive,projection,ref.split('@')[1])
  triage(ref,scanner,out/name)
  images.append(dict(target=ref,source='oci-archive:'+str(projection.resolve()),digest=ref.split('@')[1],
                     platform='linux/amd64',origins=[name],introduced=False))
 plan=dict(version=1,full=True,base=None,lockfiles=[],coverage=[],images=images)
 result=sc.scan(plan,sc.verify_tools(tools),out/'cache',out/'scan')
 report=dict(date=sc.today().isoformat(),database=result['database'],imageCodeExecuted=False,images=[])
 for name,ref in ROWS:
  found=[v for v in result['findings'] if v['target']==ref]
  report['images'].append(dict(name=name,reference=ref,verifiedAmd64Digest=bindings[name],
                             coverage='complete-oci-archive-linux-amd64',counts=counts(found),findings=found))
 sc.write(out/'comparison.json',report)
 # A stopped component is still fully scanned as data. Only the actual rendered
 # pin can be promoted; no exception is transferred to an inactive candidate.
 root=Path(__file__).resolve().parents[2]
 app=sc.read(root/'deploy/common/images.lock.json')['images']['ministack']['digest']
 pause=sc.read(root/'deploy/common/bootstrap-images.lock.json')['images']['pause']['digest']
 pins={'ministack':app,'pause':pause};report['promotions']={};failed=False
 for component,pin in pins.items():
  before=next(v for v in report['images'] if v['name']==component+'-before')
  after=next(v for v in report['images'] if v['name']==component+'-after')
  if pin not in (before['reference'].split('@')[1],after['reference'].split('@')[1]):
   raise ValueError('Unexpected P3 rendered pin')
  selected=after['reference'].endswith('@'+pin)
  blocked=bool(after['counts']['CriticalWithFix'] or after['counts']['HighWithFix'])
  report['promotions'][component]=dict(promoted=selected,blockedCandidate=blocked)
  failed|=selected and blocked
 sc.write(out/'comparison.json',report)
 return int(failed)


if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--tools',type=Path,required=True)
 p.add_argument('--scanner',type=Path,required=True);p.add_argument('--out',type=Path,default=Path('.build/wo34-p3'))
 a=p.parse_args();raise SystemExit(compare(a.tools,a.scanner,a.out))
