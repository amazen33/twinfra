"""WO-06 static candidate, MiniStack read views and preserved-history boundaries."""
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'console'))
import check_emulator_removal as guard
import wsl_console
from ci import historical_links

spec = importlib.util.spec_from_file_location('portal_removal', ROOT / 'console/server.py')
portal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(portal)


class Removal(unittest.TestCase):
    def test_candidate_source_guard(self):
        guard.check(ROOT)

    def test_code_lock_manifest_and_path_reintroductions_fail(self):
        for filename, text in [('console/server.py', guard.REMOVED),
                               ('deploy/image.lock.json', '{"image":"' + guard.REMOVED + '"}'),
                               ('deploy/service.yaml', 'name: ' + guard.REMOVED),
                               ('tools/' + guard.REMOVED + '.py', '# removed path')]:
            with self.subTest(path=filename), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); file = root / filename
                file.parent.mkdir(parents=True); file.write_text(text)
                self.assertTrue(guard.violations(root, [filename]))

    def test_only_exact_historical_ci_lines_are_exempt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); file = root / guard.CI_RUNNER
            file.parent.mkdir(parents=True)
            file.write_text('\n'.join(sorted(guard.HISTORICAL_LINES)))
            self.assertEqual(guard.violations(root, [guard.CI_RUNNER]), [])
            file.write_text("image = 'docker.io/" + guard.REMOVED + "/image:1.0.0'")
            self.assertTrue(guard.violations(root, [guard.CI_RUNNER]))

    def test_ministack_pin_satisfies_release_age_and_digest(self):
        dev = json.loads((ROOT / 'deploy/common/images.lock.json').read_text())['images']['ministack']
        retained = json.loads((wsl_console.HERE / 'artifacts.lock.json').read_text())['images']['ministack']
        self.assertEqual(dev['digest'], retained['digest'])
        self.assertEqual(dev['release'], 'docker.io/ministackorg/ministack:1.5.17')
        self.assertEqual(dev['digest'], 'sha256:11d7308bfc75029d55625b9525e84a2401431ed1ff2148c6311800ff5009ae9c')
        verified = datetime.fromisoformat(dev['verifiedOn']).replace(tzinfo=timezone.utc)
        for field in ('publishedAt', 'releasePublishedAt'):
            self.assertGreaterEqual(verified - datetime.fromisoformat(dev[field].replace('Z', '+00:00')), timedelta(days=14))

    def test_backend_is_only_ministack_even_with_environment_override(self):
        with patch.dict('os.environ', {'PLATFORM_DEFAULT_BACKEND': 'other', 'PLATFORM_BACKENDS': 'other'}):
            self.assertEqual(portal.valid_query({}), 'ministack')
            self.assertEqual(portal.api_response('identity', {}, {})['backends'], ['ministack'])
            for name in (guard.REMOVED, 'other'):
                with self.assertRaisesRegex(ValueError, 'Unsupported backend'):
                    portal.valid_query({'backend': [name]})

    def test_s3_ec2_dynamodb_reads_only_contact_ministack(self):
        calls = []
        def read(request):
            calls.append(request)
            if request.full_url.endswith('/_ministack/health'):
                return b'{"services":{"s3":"running","ec2":"running","iam":"running","dynamodb":"running"}}'
            if request.get_header('X-amz-target'):
                return b'{"TableNames":["users"]}'
            if request.data:
                self.assertEqual(request.data, b'Action=DescribeInstances&Version=2016-11-15')
                return b'<DescribeInstancesResponse><instancesSet><item><instanceId>i-fixture</instanceId><instanceType>test</instanceType><instanceState><name>running</name></instanceState></item></instancesSet></DescribeInstancesResponse>'
            return b'<ListAllMyBucketsResult><Buckets><Bucket><Name>fixture</Name></Bucket></Buckets></ListAllMyBucketsResult>'
        with patch.object(portal, 'read', side_effect=read):
            self.assertEqual(portal.api_response('storage', {}, {})['buckets'], ['fixture'])
            self.assertEqual(portal.api_response('dynamodb', {}, {})['tables'], ['users'])
            cloud = portal.api_response('cloud', {}, {})
            self.assertEqual(cloud['backend'], 'ministack')
            self.assertEqual(cloud['instances'][0]['id'], 'i-fixture')
        self.assertEqual(len(calls), 4)
        self.assertTrue(all(r.full_url.startswith(portal.signed_request('ministack', 's3').full_url) for r in calls))
        self.assertTrue(all(r.get_method() in ('GET', 'POST') for r in calls))

    def test_retained_routes_and_policies_have_only_ministack(self):
        objects = wsl_console.routes() + wsl_console.workloads() + wsl_console.network()
        self.assertNotIn(guard.REMOVED, json.dumps(objects).lower())
        self.assertEqual({b['name'] for b in wsl_console.profile()['backends'] if b['enabled']}, {'ministack', 'storage', 'dynamodb'})

    def test_unchanged_historical_links_verify_frozen_runbook(self):
        for referer in historical_links.REFERERS:
            self.assertTrue(historical_links.verified_deleted_link(ROOT, ROOT / referer, ROOT / historical_links.TARGET))
        self.assertFalse(historical_links.verified_deleted_link(ROOT, ROOT / 'README.md', ROOT / historical_links.TARGET))
        self.assertFalse(historical_links.verified_deleted_link(ROOT, ROOT / next(iter(historical_links.REFERERS)), ROOT / 'missing.md'))


if __name__ == '__main__':
    unittest.main()
