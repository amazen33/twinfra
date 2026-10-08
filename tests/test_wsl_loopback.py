"""Loopback repair must preserve Windows replies and refuse foreign host state."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import wsl_loopback_routing as routing


class LoopbackTests(unittest.TestCase):
    def fixture(self):
        objects = routing.expected_table()
        for index, obj in enumerate(objects):
            next(iter(obj.values()))['handle'] = index + 1
        return {'nftables': [{'metainfo': {'version': 'fixture'}}, *objects]}

    def test_existing_state_is_idempotent(self):
        self.assertEqual(routing.plan(self.fixture(), copy.deepcopy(routing.RULES)), ('', []))

    def test_missing_rules_are_repaired_without_replacing_table(self):
        batch, commands = routing.plan(self.fixture(), [routing.RULES[0]])
        self.assertEqual(batch, '')
        self.assertEqual(len(commands), 1)
        self.assertIn('loopback0', commands[0])

    def test_remove_is_exact_and_preserves_unrelated_routes(self):
        unrelated = {'priority': 9, 'fwmark': '0x200', 'table': '2004'}
        batch, commands = routing.plan(self.fixture(), routing.RULES + [unrelated], remove=True)
        self.assertEqual(batch, 'delete table ip vcloud_wsl_loopback\n')
        self.assertEqual(len(commands), 2)
        self.assertTrue(all('delete' in c and '127.0.0.1/32' in c for c in commands))
        self.assertNotIn('flush', batch)

    def test_broader_or_foreign_priority_zero_rules_fail(self):
        for mutation in ({'dst': '127.0.0.0/8'}, {'fwmark': '0x1'}, {'iif': 'eth2'}):
            rules = copy.deepcopy(routing.RULES)
            rules[0].update(mutation)
            with self.assertRaises(ValueError):
                routing.plan(self.fixture(), rules)
        with self.assertRaises(ValueError):
            routing.plan(self.fixture(), [{'priority': 0, 'src': 'all', 'table': 'local'}])

    def test_foreign_table_content_and_duplicate_rules_fail(self):
        fixture = self.fixture()
        fixture['nftables'][-1]['rule']['expr'].append({'accept': None})
        with self.assertRaises(ValueError):
            routing.plan(fixture, routing.RULES, remove=True)
        with self.assertRaises(ValueError):
            routing.plan(self.fixture(), routing.RULES + [routing.RULES[0]])

    def test_windows_reply_flows_are_not_classified_as_local_original(self):
        batch, commands = routing.plan(None, [])
        self.assertIn('ct direction original', batch)
        self.assertEqual(batch.count('ip saddr 127.0.0.1 ip daddr 127.0.0.1'), 2)
        self.assertNotIn('accept comment', batch)
        self.assertEqual(len(commands), 2)
        with self.assertRaises(ValueError):
            routing.plan(None, routing.RULES)


if __name__ == '__main__':
    unittest.main()
