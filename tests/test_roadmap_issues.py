"""Mocked tests for roadmap issue and milestone reconciliation."""
import io
import json
from urllib.parse import parse_qs, urlparse
import unittest
from unittest.mock import patch

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import create_roadmap_issues as roadmap


def response(payload):
    return io.BytesIO(json.dumps(payload).encode('utf-8'))


class RoadmapIssueTests(unittest.TestCase):
    def setUp(self):
        self.milestones = [
            {'number': index, 'title': item['title'], 'state': 'open'}
            for index, item in enumerate(roadmap.ROADMAP, start=1)
        ]
        self.issues = []
        number = 1
        for milestone_number, milestone in enumerate(roadmap.ROADMAP, start=1):
            for title, _body in milestone['issues']:
                self.issues.append({
                    'number': number,
                    'title': title,
                    'milestone': {'number': milestone_number},
                })
                number += 1

    def mock_urlopen(self, issue_pages=None, milestone_pages=None, writes=None):
        issue_pages = issue_pages or {1: self.issues}
        milestone_pages = milestone_pages or {1: self.milestones}
        writes = writes if writes is not None else []

        def open_request(request, timeout):
            parsed = urlparse(request.full_url)
            path = parsed.path.removeprefix(f'/repos/{roadmap.REPOSITORY}')
            method = request.get_method()
            if method == 'GET':
                page = int(parse_qs(parsed.query)['page'][0])
                if path == '/milestones':
                    return response(milestone_pages.get(page, []))
                if path == '/issues':
                    return response(issue_pages.get(page, []))

            payload = json.loads(request.data.decode('utf-8')) if request.data else {}
            writes.append((method, path, payload))
            if method == 'POST' and path == '/milestones':
                return response({
                    'number': 100 + len(writes),
                    'title': payload['title'],
                    'state': 'open',
                })
            if method == 'POST' and path == '/issues':
                return response({'number': 200 + len(writes), **payload})
            return response({'number': int(path.rsplit('/', 1)[1]), **payload})

        return open_request

    def test_exact_titles_are_reused_across_paginated_lists_and_prs_are_ignored(self):
        filler_milestones = [
            {'number': 1000 + index, 'title': f'Unrelated {index}', 'state': 'open'}
            for index in range(roadmap.PAGE_SIZE)
        ]
        filler_issues = [
            {'number': 3000 + index, 'title': f'Unrelated {index}'}
            for index in range(roadmap.PAGE_SIZE - 1)
        ]
        pull_request = {
            'number': 4000,
            'title': self.issues[0]['title'],
            'pull_request': {'url': 'https://api.github.com/repos/example/pulls/4000'},
        }
        issue_pages = {1: filler_issues + [pull_request], 2: self.issues}
        milestone_pages = {1: filler_milestones, 2: self.milestones}
        writes = []
        output = []
        with patch.object(
            roadmap, 'urlopen',
            side_effect=self.mock_urlopen(issue_pages, milestone_pages, writes),
        ) as mocked:
            roadmap.manage_roadmap(
                roadmap.GitHubAPI('test-token'), output=output.append
            )

        self.assertEqual(writes, [])
        requests = [call.args[0] for call in mocked.call_args_list]
        query_pages = [
            int(parse_qs(urlparse(request.full_url).query)['page'][0])
            for request in requests
        ]
        self.assertIn(2, query_pages)
        self.assertEqual(len(requests), 4)

    def test_matching_issue_is_assigned_to_intended_milestone(self):
        issue = dict(self.issues[0], milestone=None)
        issues = [issue] + self.issues[1:]
        writes = []
        with patch.object(
            roadmap, 'urlopen',
            side_effect=self.mock_urlopen(
                issue_pages={1: issues}, writes=writes
            ),
        ):
            roadmap.manage_roadmap(roadmap.GitHubAPI('test-token'), output=lambda _line: None)

        self.assertEqual(
            writes,
            [('PATCH', f'/issues/{issue["number"]}', {'milestone': 1})],
        )

    def test_dry_run_performs_no_writes(self):
        writes = []
        output = []
        with patch.object(
            roadmap, 'urlopen',
            side_effect=self.mock_urlopen(
                issue_pages={1: []}, milestone_pages={1: []}, writes=writes
            ),
        ):
            roadmap.manage_roadmap(
                roadmap.GitHubAPI('test-token'),
                dry_run=True,
                output=output.append,
            )

        self.assertEqual(writes, [])
        self.assertIn('Dry run complete; no changes were made.', output)
        self.assertEqual(
            sum(line.startswith('Would create milestone:') for line in output),
            len(roadmap.ROADMAP),
        )
        self.assertEqual(
            sum(line.startswith('Would create issue:') for line in output),
            sum(len(item['issues']) for item in roadmap.ROADMAP),
        )

    def test_closed_matching_milestone_stops_before_any_write(self):
        milestones = list(self.milestones)
        milestones[0] = dict(milestones[0], state='closed')
        writes = []
        with patch.object(
            roadmap, 'urlopen',
            side_effect=self.mock_urlopen(
                milestone_pages={1: milestones}, writes=writes
            ),
        ):
            with self.assertRaisesRegex(roadmap.RoadmapError, 'milestone is closed'):
                roadmap.manage_roadmap(roadmap.GitHubAPI('test-token'), output=lambda _line: None)
        self.assertEqual(writes, [])


if __name__ == '__main__':
    unittest.main()
