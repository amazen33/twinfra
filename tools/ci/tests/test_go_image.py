"""All-image binary triage fixtures; image code/scanners never execute."""
import io
import json
from pathlib import Path
import sys
import tarfile
import unittest

sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parents[2])]
import triage_go_image as triage


class Source:
    def __init__(self,layers):self.layers=layers;self.manifest={'layers':list(range(len(layers)))}
    def blob(self,index):return self.layers[index]


def layer(files):
    buf=io.BytesIO()
    with tarfile.open(fileobj=buf,mode='w') as archive:
        for name,raw in files:
            entry=tarfile.TarInfo(name);entry.size=len(raw);archive.addfile(entry,io.BytesIO(raw))
    return buf.getvalue()


class GoImages(unittest.TestCase):
    def test_all_go_elfs_in_final_layers_are_inspected_not_native_or_deleted_files(self):
        go=b'\x7fELF fixture \xff Go buildinf:'
        source=Source([layer([('a',go),('b',go),('native',b'\x7fELF native')]),
                       layer([('.wh.a',b''),('c',go)])])
        self.assertEqual(set(triage.go_files(source)),{'b','c'})

    def test_path_escape_rejected(self):
        with self.assertRaisesRegex(ValueError,'Unsafe image path'):
            triage.go_files(Source([layer([('../escape',b'\x7fELF \xff Go buildinf:')])]))

    def test_symbol_presence_is_conservative_and_module_only_is_distinct(self):
        data=[{'osv':{'id':'GO-example','aliases':['CVE-example']}},
              {'finding':{'osv':'GO-example','fixed_version':'v2','trace':[{'module':'stdlib','version':'v1'}]}},
              {'finding':{'osv':'GO-example','trace':[{'module':'stdlib','version':'v1','package':'net/http','function':'Serve'}]}}]
        result=triage.classify('\n'.join(json.dumps(v,indent=2) for v in data))
        self.assertEqual(result[0]['classification'],'affected-symbols-present')
        self.assertEqual(result[0]['aliases'],['CVE-example'])
        self.assertEqual(triage.classify(json.dumps(data[1]))[0]['classification'],'module-only-binary-finding')

    def test_no_trace_or_truncated_output_is_not_a_clean_scan(self):
        with self.assertRaises(ValueError):triage.classify('{"finding":{"osv":"GO-example"}}')
        with self.assertRaises(ValueError):triage.classify('{')


if __name__=='__main__':unittest.main()
