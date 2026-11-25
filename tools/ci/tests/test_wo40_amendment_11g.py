"""Exact O-22 renewals, untouched predecessor rows and nightly risk clocks."""
from collections import Counter
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools/ci'))
sys.path.insert(0, str(ROOT / 'tests'))
import r12_exceptions as r12
import supply_chain as sc
from r12_receipts import current_exceptions
from test_wo46_argocd import BUNDLE as PREDECESSOR_FILES

APPROVER = 'amazen33'
RECORD = 'security/wo40-amendment-11g-approval.json'
PROPOSAL = 'security/proposals/wo40-amendment-11g.json'
PREVIOUS = 'security/wo46-argocd-3.5.7-approval.json'
REGISTRY = 'security/vulnerability-exceptions.json'
FIELDS = (*r12.KEYS, 'severity', 'expires')


def encoded(value):
    return (json.dumps(value, indent=2) + '\n').encode()


class R13b(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proposal = sc.read(ROOT / PROPOSAL)
        cls.record = sc.read(ROOT / RECORD)
        cls.previous = sc.read(ROOT / PREVIOUS) | {'approvedBy': APPROVER}
        _, cls.base = current_exceptions(ROOT, previous_wo46=True)
        cls.indices = [index for index, row in enumerate(cls.base['exceptions'])
                       if row['expires'] == '2026-11-27']
        cls.fixture_path = Path(__file__).parent / 'fixtures/wo40-amendment-11g-nightly.json'
        cls.fixture = sc.read(cls.fixture_path)

    def project(self, owner):
        return r12.amendment_11g_batch(self.base, self.proposal,
                                      self.record | {'approvedBy': owner}, self.previous)

    def populate(self, root, owner):
        for name in (*PREDECESSOR_FILES, PROPOSAL):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((ROOT / name).read_bytes())
        (root / PREVIOUS).write_bytes(encoded(self.previous))
        (root / RECORD).write_bytes(encoded(self.record | {'approvedBy': owner}))
        (root / REGISTRY).write_bytes(encoded(self.project(owner)))

    def test_exact_hashes_both_projections_and_unchanged_positions(self):
        raw = (ROOT / PROPOSAL).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         'b6c7f1ef190fbbacc2491c47580270e7b044326e137625a62ff7ff8fe55c318c')
        self.assertEqual(len(self.indices), 74)
        for owner, key in (('', 'proposedRegistrySHA256'), (APPROVER, 'approvedRegistrySHA256')):
            with self.subTest(owner=owner):
                record = self.record | {'approvedBy': owner}
                self.assertEqual(r12.content_sha256(record), r12.AMENDMENT_11G_RECORD_HASHES[owner])
                projected = self.project(owner)
                self.assertEqual(r12.content_sha256(projected), record[key])
                self.assertEqual(Counter(row['severity'] for row in projected['exceptions']),
                                 {'Critical': 64, 'High': 420})
                self.assertEqual(Counter(row['expires'] for row in projected['exceptions']),
                                 {'2026-12-13': 1, '2026-12-17': 81, '2026-12-27': 402})
                self.assertEqual(len({r12.identity(row) for row in projected['exceptions']}), 484)
                for index, prior in enumerate(self.base['exceptions']):
                    actual = projected['exceptions'][index]
                    if index not in self.indices:
                        self.assertEqual(actual, prior)
                        continue
                    renewal = self.proposal['renewed'][self.indices.index(index)]
                    self.assertEqual(actual, renewal | {'approvedBy': owner})
                    self.assertEqual(actual, prior | {k: actual[k] for k in
                                                     ('approvedBy', 'createdOn', 'expires', 'reason')})
                    self.assertTrue(actual['reason'].endswith(prior['reason']))
                self.assertEqual(projected['exceptions'][477:],
                                 [row | {'approvedBy': owner} for row in self.proposal['exceptions']])

    def test_changed_base_and_unapproved_predecessor_are_refused(self):
        for owner in ('', APPROVER):
            record = self.record | {'approvedBy': owner}
            for previous in (self.previous | {'approvedBy': ''}, self.previous | {'authority': 'changed'}):
                with self.subTest(owner=owner), self.assertRaisesRegex(ValueError, 'unchanged WO-46'):
                    r12.amendment_11g_batch(self.base, self.proposal, record, previous)
            base = deepcopy(self.base)
            base['exceptions'][0]['controls'].append('changed')
            with self.assertRaisesRegex(ValueError, 'unchanged WO-46'):
                r12.amendment_11g_batch(base, self.proposal, record, self.previous)

    def test_changed_proposal_and_forged_record_hashes_are_refused(self):
        proposals = []
        for field, value in (('controls', ['changed']), ('expires', '2026-12-18'),
                             ('reason', 'missing prior reason'), ('approvedBy', APPROVER)):
            proposed = deepcopy(self.proposal)
            proposed['renewed'][0][field] = value
            proposals.append(proposed)
        proposals.extend((
            self.proposal | {'renewed': self.proposal['renewed'][::-1]},
            self.proposal | {'exceptions': self.proposal['exceptions'][:-1]},
            self.proposal | {'exceptions': self.proposal['exceptions'] + self.proposal['exceptions'][:1]},
        ))
        for owner in ('', APPROVER):
            record = self.record | {'approvedBy': owner}
            for index, proposed in enumerate(proposals):
                with self.subTest(owner=owner, mutation=index):
                    with self.assertRaisesRegex(ValueError, 'anchored 74 renewals'):
                        r12.amendment_11g_batch(self.base, proposed, record, self.previous)
                    forged = record | {'proposalSHA256': r12.content_sha256(proposed)}
                    with self.assertRaisesRegex(ValueError, 'Exact Amendment 11g approval'):
                        r12.amendment_11g_batch(self.base, proposed, forged, self.previous)

    def test_semantic_checks_reject_control_expiry_reason_and_outside_group(self):
        mutations = []
        for field, value in (('controls', ['changed']), ('expires', '2026-12-18'),
                             ('createdOn', '2026-11-18'), ('approvedBy', APPROVER),
                             ('reason', 'WO-40 Amendment 11g (R13b)/O-22 renewal: missing prior reason')):
            proposed = deepcopy(self.proposal)
            proposed['renewed'][0][field] = value
            mutations.append((proposed, 'renewal changes fields'))
        moved = self.proposal | {'renewed': self.proposal['renewed'][::-1]}
        mutations.append((moved, 'preserve the November 27 group'))
        outside = deepcopy(self.proposal)
        other = next(row for row in self.base['exceptions'] if row['expires'] != '2026-11-27')
        outside['renewed'][0] = outside['renewed'][0] | {key: other[key] for key in r12.KEYS}
        mutations.append((outside, 'preserve the November 27 group'))
        for owner in ('', APPROVER):
            for proposed, message in mutations:
                # Exercise semantic refusals independently of the outer immutable hashes.
                record = self.record | {
                    'approvedBy': owner, 'proposalSHA256': r12.content_sha256(proposed),
                    'renewedScope': [{k: row[k] for k in (*FIELDS, 'createdOn')}
                                     for row in proposed['renewed']],
                }
                with self.subTest(owner=owner, refusal=message):
                    with patch.dict(r12.AMENDMENT_11G_RECORD_HASHES, {owner: r12.content_sha256(record)}):
                        with self.assertRaisesRegex(ValueError, message):
                            r12.amendment_11g_batch(self.base, proposed, record, self.previous)

    def test_scope_and_both_projection_hashes_are_required(self):
        for owner in ('', APPROVER):
            for field, value, message in (
                    ('renewedScope', [], 'scope differs'),
                    ('addedScope', [], 'scope differs'),
                    ('proposedRegistrySHA256', '0' * 64, 'registry content hash differs'),
                    ('approvedRegistrySHA256', '0' * 64, 'registry content hash differs')):
                record = self.record | {'approvedBy': owner, field: value}
                with self.subTest(owner=owner, field=field):
                    with patch.dict(r12.AMENDMENT_11G_RECORD_HASHES, {owner: r12.content_sha256(record)}):
                        with self.assertRaisesRegex(ValueError, message):
                            r12.amendment_11g_batch(self.base, self.proposal, record, self.previous)

    def test_full_chain_in_both_states_refuses_partial_activation_or_moved_rows(self):
        for owner in ('', APPROVER):
            with self.subTest(owner=owner), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.populate(root, owner)
                projected = self.project(owner)
                self.assertEqual(current_exceptions(root)[1], projected)
                for index in (*self.indices, *range(477, 484)):
                    partial = deepcopy(projected)
                    partial['exceptions'][index]['approvedBy'] = '' if owner else APPROVER
                    (root / REGISTRY).write_bytes(encoded(partial))
                    with self.subTest(index=index), self.assertRaisesRegex(AssertionError, 'Active registry differs'):
                        current_exceptions(root)
                moved = deepcopy(projected)
                a, b = self.indices[:2]
                moved['exceptions'][a], moved['exceptions'][b] = moved['exceptions'][b], moved['exceptions'][a]
                (root / REGISTRY).write_bytes(encoded(moved))
                with self.assertRaisesRegex(AssertionError, 'Active registry differs'):
                    current_exceptions(root)
                (root / REGISTRY).write_bytes(encoded(projected))
                prior = self.previous | {'approvedBy': ''}
                (root / PREVIOUS).write_bytes(encoded(prior))
                with self.assertRaisesRegex(AssertionError, 'Amendment 11g approved content hash differs'):
                    current_exceptions(root)

    def test_full_chain_refuses_raw_hash_mismatch_and_incomplete_bundles(self):
        for owner in ('', APPROVER):
            with self.subTest(owner=owner), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.populate(root, owner)
                for name in (PROPOSAL, RECORD, REGISTRY, PREVIOUS):
                    path = root / name
                    raw = path.read_bytes()
                    path.write_bytes(raw + b' ')
                    with self.subTest(raw=name), self.assertRaises(AssertionError):
                        current_exceptions(root)
                    path.write_bytes(raw)
                for name in (PROPOSAL, RECORD, PREVIOUS):
                    path = root / name
                    raw = path.read_bytes()
                    path.unlink()
                    with self.subTest(missing=name), self.assertRaisesRegex(AssertionError, 'Incomplete'):
                        current_exceptions(root)
                    path.write_bytes(raw)
                (root / PROPOSAL).unlink()
                (root / RECORD).unlink()
                with self.assertRaisesRegex(AssertionError, 'Active registry differs'):
                    current_exceptions(root)

    def test_nightly_fixture_matches_the_approved_scope(self):
        self.assertEqual(hashlib.sha256(self.fixture_path.read_bytes()).hexdigest(),
                         '0b34e0dff5660cf0502d247194b3fd3adbc69e162a958f01677ee79d5d5900bb')
        self.assertEqual(self.fixture['source']['artifactId'], 14365254648)
        self.assertEqual(self.fixture['source']['databaseBuilt'], '2026-11-17T06:20:58Z')
        expected = {r12.identity(row) for row in self.proposal['renewed'] + self.proposal['exceptions']}
        self.assertEqual({r12.identity(row) for row in self.fixture['findings']}, expected)
        additions = {r12.identity(row) for row in self.proposal['exceptions']}
        for finding in self.fixture['findings']:
            if r12.identity(finding) in additions:
                self.assertEqual((finding['firstSeen'], finding['severity'], finding['fixVersions']),
                                 ('2026-11-12', 'High', ['24.22.3-r0']))
                self.assertFalse(finding['kev'])

    def test_replay_approved_pending_missing_additions_and_unrenewed_expiry(self):
        result = {'findings': self.fixture['findings']}
        first_seen = {row['key']: row['firstSeen'] for row in result['findings']}
        approved = self.project(APPROVER)
        without_additions = approved | {'exceptions': approved['exceptions'][:477]}
        unrenewed = self.base | {'exceptions': self.base['exceptions'] + approved['exceptions'][477:]}
        for offset in range(27):
            on = date(2026, 11, 17) + timedelta(days=offset)
            with self.subTest(on=on):
                current = sc.evaluate(result, approved, self.fixture['kev'], first_seen, root=ROOT, on=on)
                self.assertEqual(current['status'], 'passed')
                self.assertEqual(sum(row['blocked'] for row in current['findings']), 0)
                self.assertEqual(sum(bool(row['exception']) for row in current['findings']), 81)
                missing = sc.evaluate(result, without_additions, self.fixture['kev'], first_seen, root=ROOT, on=on)
                self.assertEqual(sum(row['blocked'] for row in missing['findings']),
                                 7 if on >= date(2026, 11, 26) else 0)
                if on >= date(2026, 11, 28):
                    with self.assertRaisesRegex(ValueError, 'Expired/invalid exception lifetime'):
                        sc.evaluate(result, unrenewed, self.fixture['kev'], first_seen, root=ROOT, on=on)
                else:
                    self.assertEqual(sc.evaluate(result, unrenewed, self.fixture['kev'], first_seen,
                                                 root=ROOT, on=on)['status'], 'passed')
        with self.assertRaisesRegex(ValueError, 'CVE-2026-123158'):
            sc.evaluate(result, approved, self.fixture['kev'], first_seen, root=ROOT, on=date(2026, 12, 14))
        with self.assertRaisesRegex(ValueError, 'Malformed vulnerability exception'):
            sc.evaluate(result, self.project(''), self.fixture['kev'], first_seen, root=ROOT, on=date(2026, 11, 17))

    def test_checked_in_bundle_preserves_both_historical_projections(self):
        # Freeze this test at its own 484-row projection as later batches append.
        for owner in ('', APPROVER):
            with self.subTest(owner=owner), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.populate(root, owner)
                _, current = current_exceptions(root)
                self.assertEqual(current, sc.read(root / REGISTRY))
                self.assertEqual(current, self.project(owner))
                _, prior = current_exceptions(root, previous_wo46=True)
                self.assertEqual(prior, self.base)
                _, r13a = current_exceptions(root, previous_r13a=True)
                self.assertEqual(len(r13a['exceptions']), 479)


if __name__ == '__main__':
    unittest.main()
