"""WO-40 Amendment 10: complete, data-only candidate admission comparisons."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
import supply_chain as sc
from compare_console_images import scan_projection, counts
from registry_export import export_public
from platform_pg_image import Export
from triage_go_image import triage

CASES={
    'argocd355':('argocd','3.5.5','quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518'),
    'argocd356':('argocd','3.5.6','quay.io/argoproj/argocd@sha256:8e5cc5bb008df8a09dba439462e58c94c55b7735888d3ebde0c25fc05e4e5335'),
    'ministack1533':('ministack','1.5.33','docker.io/ministackorg/ministack@sha256:b58186186515a372798ccf0ca9975c295db219b5a811975337d6967b968e07b4'),
    'keycloak2681':('keycloak','26.8.1','quay.io/keycloak/keycloak@sha256:a78d6b79572168cb25886b80a8b5b8d4ed4390743e3eecb810538683e209dd6b'),
}


def identity(value):
    return value['package'],value['vulnerability']


def compare_identities(before,after):
    def severe(values):
        return {identity(v) for v in values if v['severity'] in ('Critical','High') and v['fixAvailable']}
    old,new=severe(before),severe(after)
    return {'subset':new<=old,'strictImprovement':new<old,
            'closed':sorted(old-new),'introduced':sorted(new-old),'carried':sorted(old&new)}


def compare(case,tools,scanner,out):
    component,release,candidate=CASES[case]
    before=sc.immutable(sc.read(ROOT/'deploy/common/images.lock.json')['images'][component])
    out.mkdir(parents=True,exist_ok=True)
    images=[];bindings={};contracts={}
    for side,ref in [('before',before),('after',candidate)]:
        archive=out/(side+'.oci.tar');export_public(ref,archive)
        source=Export(archive)
        try:
            config=json.loads(source.blob(source.manifest['config']))['config']
            contracts[side]={key:config.get(key) for key in ('User','Entrypoint','Cmd','WorkingDir')}
        finally:source.archive.close()
        projection=out/(side+'.scan.oci.tar')
        bindings[side]=scan_projection(archive,projection,ref.split('@')[1])
        images.append({'target':ref,'source':'oci-archive:'+projection.resolve().as_posix(),
                       'digest':ref.split('@')[1],'platform':'linux/amd64','origins':[component+':'+side],'introduced':False})
    plan={'images':images,'lockfiles':[],'coverage':[],'base':None}
    result=sc.scan(plan,sc.verify_tools(tools),out/'cache',out/'scan')
    kev=json.loads(sc.fetch('https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json'))
    kev_ids={v['cveID'] for v in kev['vulnerabilities']}
    rows=[]
    for side,ref in [('before',before),('after',candidate)]:
        found=[v|{'kev':bool(set(v['aliases'])&kev_ids)} for v in result['findings'] if v['target']==ref]
        rows.append({'side':side,'reference':ref,'coverage':'complete-oci-archive-linux-amd64',
                     'verifiedAmd64Digest':bindings[side],'counts':counts(found),'findings':found})
    comparison=compare_identities(rows[0]['findings'],rows[1]['findings'])
    report={'date':sc.today().isoformat(),'component':component,'release':release,'database':result['database'],
            'kevCatalogVersion':kev['catalogVersion'],'imageCodeExecuted':False,'promotionPerformed':False,
            'images':rows,'comparison':comparison,'executionContract':contracts,
            'executionContractUnchanged':contracts['before']==contracts['after']}
    sc.write(out/'comparison.json',report)
    # Required binary-mode inspection of every Go ELF; image files are inputs only.
    for side,ref in [('before',before),('after',candidate)]:
        triage(ref,scanner,out/('go-'+side))
    print(case+': subset='+str(comparison['subset'])+', removed='+str(len(comparison['closed']))+
          ', introduced='+str(len(comparison['introduced'])))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',choices=CASES,required=True)
    parser.add_argument('--tools',type=Path,required=True)
    parser.add_argument('--scanner',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    compare(args.case,args.tools.resolve(),args.scanner.resolve(),args.out.resolve())
