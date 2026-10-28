"""Exact R12 pin/render delta and completed historical receipt boundaries."""
from copy import deepcopy
import unittest
from r12_receipts import assert_images, receipt


class R12Scope(unittest.TestCase):
    def test_three_pins_and_exact_generated_substitutions(self):
        for path in ('deploy/common/images.lock.json','lab/wsl/console/artifacts.lock.json',
                     'lab/wsl/console/workloads.yaml','lab/wsl/console/gitops/workloads.yaml',
                     'deploy/environments/dev/cairo-1/platform/workloads.yaml',
                     'deploy/environments/dev/cairo-1/services/workloads.yaml'):
            with self.subTest(path=path):receipt(path)

    def test_other_pin_and_candidate_tampering_refused(self):
        _,data=assert_images()
        for name in ('argocd','cnpg','console','openbao'):
            bad=deepcopy(data);bad['images'][name]['digest']='sha256:'+'a'*64
            with self.subTest(name=name),self.assertRaises(AssertionError):assert_images(bad)


if __name__=='__main__':unittest.main()
