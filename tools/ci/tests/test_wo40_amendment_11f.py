"""Exact O-20 approval boundaries and the November 12 nightly replay fixture."""
from collections import Counter
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools/ci'))
sys.path.insert(0, str(ROOT / 'tests'))
import r12_exceptions as r12
import supply_chain as sc
from r12_receipts import current_exceptions

APPROVER = 'amazen33'
RECORD = 'security/wo40-amendment-11f-approval.json'
PROPOSAL = 'security/proposals/wo40-amendment-11f.json'
PREVIOUS = 'security/wo40-amendment-11e-approval.json'
REGISTRY = 'security/vulnerability-exceptions.json'
KEV = 'CVE-2026-123158'
SNAPSHOT = date(2026, 11, 12)
APT_EARLY = {'docker.io/apache/apisix', 'docker.io/library/python', 'ghcr.io/cloudnative-pg/postgresql'}
START_DAY = {
    'CVE-2026-78661': 12, 'CVE-2026-85091': 12, 'CVE-2026-109383': 12,
    'CVE-2026-109829': 12, 'CVE-2026-87018': 12, KEV: 12,
    'CVE-2026-119194': 14, 'CVE-2026-119195': 14, 'CVE-2026-119196': 14,
    'CVE-2026-119197': 14, 'CVE-2026-116591': 20, 'CVE-2026-76844': 20,
}
BUNDLE = tuple('security/' + name for name in (
    'security-wave-2026-10-approval.json', 'licence-carry-log.json',
    'proposals/r12-vulnerability-exceptions.json', 'proposals/wo40-amendment-11a-kev.json',
    *(f'wo40-amendment-11{letter}-approval.json' for letter in 'acde'),
    *(f'proposals/wo40-amendment-11{letter}.json' for letter in 'cdef'),
))


def encoded(value):
    return (json.dumps(value, indent=2) + '\n').encode('utf-8')


class R13a(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proposal = sc.read(ROOT / PROPOSAL)
        cls.previous = sc.read(ROOT / PREVIOUS)
        cls.record = sc.read(ROOT / RECORD)
        _, cls.base = current_exceptions(ROOT, previous_r13a=True)
        cls.base['exceptions'] = cls.base['exceptions'][:435]

    def projection(self, attribution):
        return r12.amendment_11f_batch(self.base, self.proposal,
                                     self.record | {'approvedBy': attribution}, self.previous)

    def populate(self, directory, attribution):
        for name in BUNDLE:
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((ROOT / name).read_bytes())
        (directory / RECORD).write_bytes(encoded(self.record | {'approvedBy': attribution}))
        (directory / REGISTRY).write_bytes(encoded(self.projection(attribution)))

    def test_proposal_and_both_projections_are_hash_bound(self):
        raw = (ROOT / PROPOSAL).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         'f90ade429a5aa439928c31f342dd5fcaf37079043d83e9b1122ad7fb010223aa')
        for owner, key in (('', 'proposedRegistrySHA256'), (APPROVER, 'approvedRegistrySHA256')):
            with self.subTest(approval=owner):
                registry = self.projection(owner)
                self.assertEqual(r12.content_sha256(registry), self.record[key])
                self.assertEqual(registry['exceptions'][:435], self.base['exceptions'])
                self.assertEqual(registry['exceptions'][435:], [
                    row | {'approvedBy': owner} for row in self.proposal['exceptions']
                ])
                self.assertEqual(Counter(row['severity'] for row in registry['exceptions']),
                                 {'Critical': 64, 'High': 415})
                self.assertEqual(len({r12.identity(row) for row in registry['exceptions']}), 479)

    def test_unapproved_or_modified_antecedents_are_rejected(self):
        record = self.record | {'approvedBy': ''}
        for prior in (self.previous | {'approvedBy': ''}, self.previous | {'replacementBefore': '2026-12-27'}):
            with self.assertRaisesRegex(ValueError, 'activated, unchanged O-17'):
                r12.amendment_11f_batch(self.base, self.proposal, record, prior)
        for index in range(435):
            base = deepcopy(self.base)
            base['exceptions'][index]['reason'] += ' changed'
            with self.subTest(row=index), self.assertRaisesRegex(ValueError, 'existing row'):
                r12.amendment_11f_batch(base, self.proposal, record, self.previous)

    def test_refuses_row_shape_order_and_content_changes(self):
        record = self.record | {'approvedBy': APPROVER}
        rows = self.proposal['exceptions']
        mutations = [rows[:-1], rows[::-1], rows + rows[:1]]
        for field, value in (('reason', 'changed risk'), ('expires', '2026-12-28'),
                             ('workOrder', 'WO-47'), ('controls', []), ('approvedBy', APPROVER)):
            mutations.append([rows[0] | {field: value}, *rows[1:]])
        for index, changed in enumerate(mutations):
            proposal = self.proposal | {'exceptions': changed}
            with self.subTest(mutation=index), self.assertRaisesRegex(ValueError, '44 anchored'):
                r12.amendment_11f_batch(self.base, proposal, record, self.previous)
            forged = record | {'proposalSHA256': r12.content_sha256(proposal)}
            with self.assertRaisesRegex(ValueError, 'Exact Amendment 11f approval'):
                r12.amendment_11f_batch(self.base, proposal, forged, self.previous)

    def test_record_does_not_accept_unapproved_mutations(self):
        for key in self.record:
            record = self.record | {'approvedBy': '', key: 'tampered'}
            with self.subTest(field=key), self.assertRaisesRegex(ValueError, 'Exact Amendment 11f approval'):
                r12.amendment_11f_batch(self.base, self.proposal, record, self.previous)

    def test_full_chain_accepts_only_matching_approval_states(self):
        for owner in ('', APPROVER):
            with self.subTest(approval=owner), tempfile.TemporaryDirectory() as tmp:
                directory = Path(tmp)
                self.populate(directory, owner)
                expected = self.projection(owner)
                self.assertEqual(current_exceptions(directory)[1], expected)
                for index in range(435, 479):
                    altered = deepcopy(expected)
                    altered['exceptions'][index]['approvedBy'] = '' if owner else APPROVER
                    (directory / REGISTRY).write_bytes(encoded(altered))
                    with self.subTest(partial_row=index), self.assertRaisesRegex(AssertionError, 'Active registry differs'):
                        current_exceptions(directory)
                other = self.projection('' if owner else APPROVER)
                (directory / REGISTRY).write_bytes(encoded(other))
                with self.assertRaisesRegex(AssertionError, 'Active registry differs'):
                    current_exceptions(directory)

    def test_hash_or_bundle_loss_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            self.populate(directory, '')
            for name in (RECORD, PROPOSAL, PREVIOUS, REGISTRY):
                path = directory / name
                original = path.read_bytes()
                path.write_bytes(original + b' ')
                with self.subTest(hash_mismatch=name), self.assertRaises(AssertionError):
                    current_exceptions(directory)
                path.write_bytes(original)
            for name in (RECORD, PROPOSAL, PREVIOUS, 'security/proposals/wo40-amendment-11e.json'):
                path = directory / name
                original = path.read_bytes()
                path.unlink()
                with self.subTest(missing=name), self.assertRaisesRegex(AssertionError, 'Incomplete'):
                    current_exceptions(directory)
                path.write_bytes(original)
            (directory / RECORD).unlink()
            (directory / PROPOSAL).unlink()
            with self.assertRaisesRegex(AssertionError, 'Active registry differs'):
                current_exceptions(directory)

    def test_nightly_fixture_enforces_each_block_date_and_kev_without_fix(self):
        fixture, first_seen, block_from = [], {}, {}
        for row in self.proposal['exceptions']:
            fields = {key: row[key] for key in r12.KEYS}
            key = sc.sha(json.dumps(list(fields.values()), separators=(',', ':')).encode())
            advisory = row['vulnerability']
            is_kev = advisory == KEV
            if advisory == 'CVE-2026-109518':
                day = 19 if row['target'].split('@')[0] in APT_EARLY else 20
            else:
                day = START_DAY[advisory]
            block_from[key] = date(2026, 11, day)
            first_seen[key] = (block_from[key] - timedelta(days=14)).isoformat()
            fixture.append(fields | dict(key=key, severity='High', aliases=[advisory],
                                         kev=is_kev, fixAvailable=not is_kev, introduced=False))
        self.assertEqual(Counter(block_from.values()), {
            SNAPSHOT: 20, date(2026, 11, 14): 4, date(2026, 11, 19): 6, date(2026, 11, 20): 14,
        })
        ssh = [finding for finding in fixture if finding['kev']]
        self.assertEqual(len(ssh), 1)
        self.assertEqual(ssh[0]['vulnerability'], KEV)
        self.assertFalse(ssh[0]['fixAvailable'])
        approved = self.projection(APPROVER)
        ssh_row = next(row for row in approved['exceptions'] if row['vulnerability'] == KEV)
        self.assertEqual(ssh_row['expires'], '2026-12-13')
        catalogue = dict(catalogVersion='2026.11.10', vulnerabilities=[dict(cveID=KEV)])
        for offset in range(13):
            on = SNAPSHOT + timedelta(days=offset)
            with self.subTest(on=on):
                baseline = sc.evaluate({'findings': fixture}, self.base, catalogue, first_seen, on=on, root=ROOT)
                blocked = {item['key'] for item in baseline['findings'] if item['blocked']}
                self.assertEqual(blocked, {key for key, start in block_from.items() if start <= on})
                evaluated_ssh = next(item for item in baseline['findings'] if item['vulnerability'] == KEV)
                self.assertTrue(evaluated_ssh['kev'])
                self.assertEqual(evaluated_ssh['blockReason'], 'KEV')
                if offset:
                    result = sc.evaluate({'findings': fixture}, approved, catalogue, first_seen, on=on, root=ROOT)
                    self.assertEqual(result['status'], 'passed')
                    self.assertEqual(sum(item['blocked'] for item in result['findings']), 0)
                    self.assertEqual(sum(bool(item['exception']) for item in result['findings']), 44)
        pending = self.projection('')
        with self.assertRaisesRegex(ValueError, 'Malformed vulnerability exception'):
            sc.validate_exceptions(pending, ROOT, date(2026, 11, 13))

    def test_checked_in_bundle_matches_the_current_chain(self):
        _, current = current_exceptions(ROOT, previous_r13a=True)
        self.assertEqual(current, self.projection(APPROVER))
        self.assertEqual(len(current['exceptions']), 479)


if __name__ == '__main__':
    unittest.main()
