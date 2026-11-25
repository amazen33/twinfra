"""O-23's exact evidence refresh, required JVM control and full nightly replay."""
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

import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'tools/ci'), str(ROOT / 'tests'), str(ROOT / 'tools')]
import r12_exceptions as r12
import supply_chain as sc
import platform_dev as dev
import r12_receipts
from r12_receipts import current_exceptions
import test_wo40_amendment_11g as r13b

APPROVER = 'amazen33'
RECORD = 'security/wo40-amendment-11h-approval.json'
PROPOSAL = 'security/proposals/wo40-amendment-11h.json'
PREVIOUS = r13b.RECORD
REGISTRY = r13b.REGISTRY
BUNDLE = (*r13b.PREDECESSOR_FILES, r13b.PROPOSAL, PREVIOUS, PROPOSAL)
FIELDS = (*r12.KEYS, 'severity', 'expires')


def encoded(value):
    return (json.dumps(value, indent=2) + '\n').encode()


class R13c(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proposal = sc.read(ROOT / PROPOSAL)
        cls.record = sc.read(ROOT / RECORD)
        cls.previous = sc.read(ROOT / PREVIOUS) | {'approvedBy': APPROVER}
        _, cls.base = current_exceptions(ROOT, previous_r13b=True)
        cls.fixture_path = Path(__file__).parent / 'fixtures/wo40-amendment-11h-nightly.json'
        cls.fixture = sc.read(cls.fixture_path)
        cls.indices = [next(i for i, row in enumerate(cls.base['exceptions'])
                            if r12.identity(row) == r12.identity(refreshed))
                       for refreshed in cls.proposal['refreshed']]

    def project(self, owner):
        return r12.amendment_11h_batch(self.base, self.proposal,
                                      self.record | {'approvedBy': owner}, self.previous)

    def populate(self, root, owner):
        for name in BUNDLE:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((ROOT / name).read_bytes())
        (root / PREVIOUS).write_bytes(encoded(self.previous))
        (root / RECORD).write_bytes(encoded(self.record | {'approvedBy': owner}))
        (root / REGISTRY).write_bytes(encoded(self.project(owner)))

    def test_exact_hashes_positions_counts_and_both_approval_states(self):
        self.assertEqual(hashlib.sha256((ROOT / PROPOSAL).read_bytes()).hexdigest(),
                         '284a8af5103e66ee90e162e60f7965ed74a4c6db1be8417dd4e2c6ba389f7231')
        self.assertEqual(r12.content_sha256(self.base), self.record['baseApprovedRegistrySHA256'])
        for owner, key in (('', 'proposedRegistrySHA256'), (APPROVER, 'approvedRegistrySHA256')):
            with self.subTest(owner=owner):
                record = self.record | {'approvedBy': owner}
                self.assertEqual(r12.content_sha256(record), r12.AMENDMENT_11H_RECORD_HASHES[owner])
                projected = self.project(owner)
                self.assertEqual(r12.content_sha256(projected), record[key])
                self.assertEqual(Counter(row['severity'] for row in projected['exceptions']),
                                 {'Critical': 65, 'High': 456})
                self.assertEqual(Counter(row['expires'] for row in projected['exceptions']),
                                 {'2026-12-17': 119, '2026-12-27': 402})
                refreshed = {r12.identity(row): row | {'approvedBy': owner}
                             for row in self.proposal['refreshed']}
                expected = [refreshed.get(r12.identity(row), row) for row in self.base['exceptions']
                            if row != self.proposal['removed'][0]]
                self.assertEqual(projected['exceptions'][:483], expected)
                self.assertEqual(projected['exceptions'][483:],
                                 [row | {'approvedBy': owner} for row in self.proposal['exceptions']])
                self.assertEqual(len({r12.identity(row) for row in projected['exceptions']}), 521)

    def test_changed_base_and_unapproved_or_changed_predecessor_are_refused(self):
        for owner in ('', APPROVER):
            record = self.record | {'approvedBy': owner}
            for previous_by, record_by in (('', owner), ('intruder', owner)):
                previous = self.previous | {'approvedBy': previous_by}
                with self.assertRaisesRegex(ValueError, 'unchanged 11g predecessor'):
                    r12.amendment_11h_batch(self.base, self.proposal,
                                          record | {'approvedBy': record_by}, previous)
            changed = deepcopy(self.base)
            changed['exceptions'][0]['controls'].append('changed')
            with self.assertRaisesRegex(ValueError, 'unchanged 11g predecessor'):
                r12.amendment_11h_batch(changed, self.proposal, record, self.previous)

    def test_changed_proposal_or_forged_record_is_refused(self):
        mutations = []
        for field, value in (('reason', 'changed'), ('expires', '2026-12-18'),
                             ('workOrder', 'WO-other'), ('controls', ['changed'])):
            proposed = deepcopy(self.proposal)
            proposed['exceptions'][0][field] = value
            mutations.append(proposed)
        mutations.extend((self.proposal | {'refreshed': self.proposal['refreshed'][::-1]},
                          self.proposal | {'removed': self.proposal['removed'] * 2},
                          self.proposal | {'removed': []},
                          self.proposal | {'exceptions': self.proposal['exceptions'][:-1]},
                          self.proposal | {'exceptions': self.proposal['exceptions'] * 2},
                          self.proposal | {'exceptions': self.proposal['exceptions'][::-1]}))
        for owner in ('', APPROVER):
            record = self.record | {'approvedBy': owner}
            for index, proposed in enumerate(mutations):
                with self.subTest(owner=owner, mutation=index):
                    with self.assertRaisesRegex(ValueError, 'anchored two refreshes'):
                        r12.amendment_11h_batch(self.base, proposed, record, self.previous)
                    with self.assertRaisesRegex(ValueError, 'Exact Amendment 11h approval'):
                        r12.amendment_11h_batch(self.base, proposed,
                                              record | {'proposalSHA256': r12.content_sha256(proposed)},
                                              self.previous)

    def test_semantic_refresh_refusals_independent_of_outer_hashes(self):
        mutations = []
        for field, value in (('controls', ['changed']), ('expires', '2026-12-18'),
                             ('workOrder', 'WO-other'), ('approvedBy', APPROVER),
                             ('reason', 'WO-40 Amendment 11h (R13c)/O-23 evidence refresh: missing prior text')):
            proposed = deepcopy(self.proposal)
            proposed['refreshed'][0][field] = value
            mutations.append(proposed)
        for field, value in (('fixVersions', ['0.58.0']), ('checkedOn', '2026-11-26'),
                             ('noEligibleFixedRelease', False)):
            proposed = deepcopy(self.proposal)
            proposed['refreshed'][0]['toolchainWave'][field] = value
            mutations.append(proposed)
        for owner in ('', APPROVER):
            for index, proposed in enumerate(mutations):
                record = self.record | {'approvedBy': owner, 'proposalSHA256': r12.content_sha256(proposed),
                    'refreshedScope': [{**{k: row[k] for k in FIELDS},
                        'fixVersions': row['toolchainWave']['fixVersions'],
                        'checkedOn': row['toolchainWave']['checkedOn']} for row in proposed['refreshed']]}
                with self.subTest(owner=owner, mutation=index):
                    with patch.dict(r12.AMENDMENT_11H_RECORD_HASHES, {owner: r12.content_sha256(record)}):
                        with self.assertRaisesRegex(ValueError, 'refresh changes fields'):
                            r12.amendment_11h_batch(self.base, proposed, record, self.previous)

    def test_exact_removal_and_distinct_additions_semantic_refusals(self):
        for group, field, value, message in (
                ('removed', 'controls', ['changed'], 'removal must equal'),
                ('exceptions', 'approvedBy', APPROVER, 'distinct pending identities')):
            proposed = deepcopy(self.proposal)
            proposed[group][0][field] = value
            for owner in ('', APPROVER):
                record = self.record | {'approvedBy': owner, 'proposalSHA256': r12.content_sha256(proposed)}
                with patch.dict(r12.AMENDMENT_11H_RECORD_HASHES, {owner: r12.content_sha256(record)}):
                    with self.assertRaisesRegex(ValueError, message):
                        r12.amendment_11h_batch(self.base, proposed, record, self.previous)

    def test_scope_and_both_projection_hashes_are_required(self):
        for owner in ('', APPROVER):
            for field in ('refreshedScope', 'removedScope', 'addedScope',
                          'proposedRegistrySHA256', 'approvedRegistrySHA256'):
                record = self.record | {'approvedBy': owner, field: [] if field.endswith('Scope') else '0' * 64}
                with self.subTest(owner=owner, field=field):
                    with patch.dict(r12.AMENDMENT_11H_RECORD_HASHES, {owner: r12.content_sha256(record)}):
                        with self.assertRaisesRegex(ValueError, 'scope differs|registry content hash differs'):
                            r12.amendment_11h_batch(self.base, self.proposal, record, self.previous)

    def test_full_chain_refuses_partial_activation_moved_and_removed_rows(self):
        for owner in ('', APPROVER):
            with self.subTest(owner=owner), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.populate(root, owner)
                projected = self.project(owner)
                self.assertEqual(current_exceptions(root)[1], projected)
                changed = {r12.identity(row) for row in self.proposal['refreshed'] + self.proposal['exceptions']}
                for index, row in enumerate(projected['exceptions']):
                    if r12.identity(row) not in changed:
                        continue
                    partial = deepcopy(projected)
                    partial['exceptions'][index]['approvedBy'] = '' if owner else APPROVER
                    (root / REGISTRY).write_bytes(encoded(partial))
                    with self.subTest(index=index), self.assertRaisesRegex(AssertionError, 'Active registry differs'):
                        current_exceptions(root)
                moved = deepcopy(projected)
                a, b = self.indices
                # The removed row is later in the original list than both refreshes.
                moved['exceptions'][a], moved['exceptions'][b] = moved['exceptions'][b], moved['exceptions'][a]
                second_removal = deepcopy(projected)
                del second_removal['exceptions'][0]
                kept = deepcopy(projected)
                kept['exceptions'].append(self.proposal['removed'][0])
                for invalid in (moved, second_removal, kept):
                    (root / REGISTRY).write_bytes(encoded(invalid))
                    with self.assertRaisesRegex(AssertionError, 'Active registry differs'):
                        current_exceptions(root)
                (root / REGISTRY).write_bytes(encoded(projected))
                (root / PREVIOUS).write_bytes(encoded(self.previous | {'approvedBy': ''}))
                with self.assertRaisesRegex(AssertionError, 'Amendment 11h approved content hash differs'):
                    current_exceptions(root)

    def test_full_chain_raw_hashes_and_incomplete_bundles(self):
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

    def test_rendered_keycloak_control_matches_record_and_not_init(self):
        expected = [{'name': c['env'], 'value': c['value']} for c in self.record['requiredControls']]
        self.assertEqual(self.record['requiredControls'], [{'workload': 'twinfra-keycloak',
            'container': 'keycloak', 'env': 'JAVA_OPTS_APPEND', 'value': '-XX:-UseBASE64Intrinsics'}])
        rendered = list(yaml.safe_load_all((ROOT / 'deploy/environments/dev/cairo-1/services/workloads.yaml').read_text()))
        for objects in (dev.endpoints(), rendered):
            workload = next(obj for obj in objects if obj['kind'] == 'Deployment'
                            and obj['metadata']['name'] == 'twinfra-keycloak')
            pod = workload['spec']['template']['spec']
            container = next(c for c in pod['containers'] if c['name'] == 'keycloak')
            self.assertEqual(container['env'], expected)
            self.assertTrue(all(not any(e['name'] == 'JAVA_OPTS_APPEND' for e in c.get('env', []))
                                for c in pod['initContainers']))

    def test_nightly_fixture_integrity_and_full_input_provenance(self):
        self.assertEqual(hashlib.sha256(self.fixture_path.read_bytes()).hexdigest(),
                         '93339ffea91411fe143174b469df31e7ce7f7a4d03438be2222282e9432ca2f1')
        self.assertEqual(self.fixture['source']['artifactId'], 14921701038)
        self.assertEqual(self.fixture['source']['firstSeenArtifactId'], 14749711581)
        self.assertEqual(self.fixture['source']['databaseBuilt'], '2026-11-24T06:22:05Z')
        self.assertEqual(len(self.fixture['findings']), 2821)
        identities = {r12.identity(row) for row in self.fixture['findings']}
        self.assertTrue({r12.identity(row) for row in self.proposal['refreshed'] + self.proposal['exceptions']} <= identities)
        self.assertNotIn(r12.identity(self.proposal['removed'][0]), identities)

    def test_r12_render_receipt_allows_only_record_control_at_its_position(self):
        path = 'deploy/environments/dev/cairo-1/services/workloads.yaml'
        other = 'deploy/environments/dev/cairo-1/platform/workloads.yaml'
        original_read = Path.read_text
        actual = (ROOT / path).read_text(encoding='utf-8')
        control = self.record['requiredControls'][0]
        block = '        env:\n        - name: ' + control['env'] + '\n          value: ' + control['value'] + '\n'
        self.assertEqual(actual.count(block), 1)
        self.assertEqual(r12_receipts.receipt(path), r12_receipts.old(path))
        without = actual.replace(block, '')
        prepare_anchor = '      - name: prepare\n        image: ' + dev.image('keycloak') + '\n'
        self.assertEqual(without.count(prepare_anchor), 1)
        changed = [actual.replace(control['value'], 'different-value'),
                   actual.replace(block, block + '        - name: EXTRA\n          value: forbidden\n'),
                   without.replace(prepare_anchor, prepare_anchor + block),
                   actual.replace('replicas: 1', 'replicas: 2', 1)]
        self.assertTrue(all(text != actual for text in changed))
        cases = [(path, text) for text in changed]
        cases.append((other, (ROOT / other).read_text(encoding='utf-8') + block))
        for relative, invalid in cases:
            def read(candidate, *args, **kwargs):
                if candidate == ROOT / relative:
                    return invalid
                return original_read(candidate, *args, **kwargs)
            with self.subTest(path=relative, mutation=cases.index((relative, invalid))):
                with patch.object(Path, 'read_text', read):
                    with self.assertRaisesRegex(AssertionError, 'R12 render differs'):
                        r12_receipts.receipt(relative)

    def test_full_nightly_replay_approved_pending_missing_additions_and_refresh(self):
        result = {'findings': self.fixture['findings']}
        state = sc.FirstSeenState(self.fixture['firstSeen'])
        state.identities = self.fixture['identityState']
        approved = self.project(APPROVER)
        for offset in range(7):
            on = date(2026, 11, 25) + timedelta(days=offset)
            with self.subTest(on=on):
                report = sc.evaluate(result, approved, self.fixture['kev'], state, root=ROOT, on=on)
                self.assertEqual((report['status'], sum(row['blocked'] for row in report['findings'])), ('passed', 0))
                self.assertEqual(sum(bool(row['exception']) for row in report['findings']), 519)
        without_additions = approved | {'exceptions': approved['exceptions'][:483]}
        report = sc.evaluate(result, without_additions, self.fixture['kev'], state, root=ROOT, on=date(2026, 11, 25))
        self.assertEqual({r12.identity(row) for row in report['findings'] if row['blocked']},
                         {r12.identity(row) for row in self.proposal['exceptions']})
        prior = {r12.identity(row): row for row in self.base['exceptions']}
        refresh_ids = {r12.identity(row) for row in self.proposal['refreshed']}
        without_refresh = approved | {'exceptions': [prior[r12.identity(row)] if r12.identity(row) in refresh_ids else row
                                                     for row in approved['exceptions']]}
        with self.assertRaisesRegex(ValueError, 'Toolchain-wave scanner fixes changed; refresh evidence'):
            sc.evaluate(result, without_refresh, self.fixture['kev'], state, root=ROOT, on=date(2026, 11, 25))
        with self.assertRaisesRegex(ValueError, 'Malformed vulnerability exception'):
            sc.evaluate(result, self.project(''), self.fixture['kev'], state, root=ROOT, on=date(2026, 11, 25))

    def test_checked_in_bundle_matches_current_and_unchanged_historical_projections(self):
        self.assertEqual(current_exceptions(ROOT)[1], sc.read(ROOT / REGISTRY))
        self.assertEqual(current_exceptions(ROOT)[1], self.project(self.record['approvedBy']))
        self.assertEqual(current_exceptions(ROOT, previous_r13b=True)[1], self.base)
        self.assertEqual(len(current_exceptions(ROOT, previous_wo46=True)[1]['exceptions']), 477)
        self.assertEqual(len(current_exceptions(ROOT, previous_r13a=True)[1]['exceptions']), 479)


if __name__ == '__main__':
    unittest.main()
