"""Exception closures require exact before evidence and current full-image pins."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import close_console_exceptions as closure
import compare_console_images as comparison


class Closures(unittest.TestCase):
    def test_counts_separate_fixability(self):
        self.assertEqual(comparison.counts([{'severity':'Critical','fixAvailable':True},
                                           {'severity':'High','fixAvailable':False}]),
                         {'CriticalWithFix':1,'CriticalWithoutFix':0,'HighWithFix':0,'HighWithoutFix':1})

    def test_pin_mismatch_or_fixable_critical_never_writes_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'console').mkdir()
            (root/'console/image.lock.json').write_text(json.dumps({'canonical':'approved','base':'approved-base'}))
            rows=[dict(name=n,reference='mismatched',coverage='complete-oci-archive-linux-amd64',counts={'CriticalWithFix':0})
                  for n in ('console-after','python-after')]
            with patch.object(closure,'ROOT',root),self.assertRaisesRegex(ValueError,'Scan pins'):
                closure.close({'images':rows},'https://github.com/amazen33/twinfra/actions/runs/1')
            rows[0]['counts']['CriticalWithFix']=1
            with patch.object(closure,'ROOT',root),self.assertRaisesRegex(ValueError,'zero fixable Critical'):
                closure.close({'images':rows},'https://github.com/amazen33/twinfra/actions/runs/1')
            self.assertFalse((root/'security/vulnerability-exceptions.json').exists())

    def test_run_url_must_be_the_exact_repository(self):
        with self.assertRaises(ValueError):closure.close({},'https://github.com/other/repo/actions/runs/1')


if __name__=='__main__':unittest.main()
