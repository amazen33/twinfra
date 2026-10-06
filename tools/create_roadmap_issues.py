#!/usr/bin/env python3
"""Create or reconcile the vCloud roadmap milestones and tracking issues."""
import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


REPOSITORY = 'amazen33/vCloud'
API_BASE = 'https://api.github.com'
PAGE_SIZE = 100

ROADMAP = (
    {
        'title': 'v0.1.0-alpha - Core Foundation & Local Lab Setup',
        'description': 'Establish the reproducible local Kubernetes lab and its bounded network access.',
        'issues': (
            (
                'Bootstrap a reproducible WSL2 K3s local lab',
                'Document and automate the supported WSL2 prerequisites, K3s installation, and '
                'cluster readiness checks. Verify a clean setup can reach a healthy, usable '
                'single-node cluster and record the tested Windows/WSL versions.',
            ),
            (
                'Validate Cilium deny-all policies with connectivity probes',
                'Exercise the baseline Cilium deny-all policy with repeatable positive and '
                'negative connectivity probes. Demonstrate that unapproved traffic is blocked, '
                'explicitly allowed traffic succeeds, and probe results are retained as evidence.',
            ),
            (
                'Define scoped Windows and host firewall bridge exceptions',
                'Identify the exact addresses, protocols, and ports required across the Windows, '
                'WSL2, and K3s host firewall boundary. Document the narrow exceptions, apply only '
                'those rules, and verify required paths work while unrelated paths remain blocked.',
            ),
        ),
    },
    {
        'title': 'v0.2.0-beta - GitOps & Platform Services',
        'description': 'Stabilize GitOps reconciliation and deploy the core stateful and identity services.',
        'issues': (
            (
                'Resolve the ArgoCD repo-server ComparisonError',
                'Reproduce and identify the cause of the ArgoCD repo-server ComparisonError. '
                'Correct the repository or repo-server configuration, then verify the affected '
                'Application renders, compares, and syncs successfully without recurring errors.',
            ),
            (
                'Run CloudNativePG on a 4 GiB Local PV',
                'Deploy the CloudNativePG workload using a local persistent volume sized for the '
                '4 GiB lab constraint. Verify scheduling and ownership, database readiness, '
                'persistence across pod restart, and documented recovery behavior.',
            ),
            (
                'Integrate Keycloak identity and OpenBao secrets',
                'Deploy and connect Keycloak and OpenBao for the platform identity and secret '
                'flows. Document the trust boundaries, configure least-privilege integration, '
                'and validate an end-to-end authenticated secret retrieval without exposing '
                'credentials in logs or manifests.',
            ),
        ),
    },
    {
        'title': 'v0.3.0-rc - ISTQB & Compliance Validation',
        'description': 'Produce traceable integration evidence and validate zero-trust and GitOps controls.',
        'issues': (
            (
                'Build traceable system integration testing evidence',
                'Create a system integration test (SIT) set that traces each requirement to test '
                'cases, execution results, and retained evidence. Record coverage gaps and '
                'retest outcomes so release readiness is auditable.',
            ),
            (
                'Perform authorized zero-trust penetration auditing',
                'Define written authorization, scope, exclusions, and safety limits before '
                'testing. Audit zero-trust boundaries using approved techniques, preserve '
                'traceable findings and evidence, and track remediation and retest results.',
            ),
            (
                'Test ArgoCD self-healing against controlled drift',
                'Introduce controlled, reversible drift to representative managed resources. '
                'Verify ArgoCD detects and self-heals drift, records a clear status, and does not '
                'overwrite explicitly excluded or unmanaged resources.',
            ),
        ),
    },
    {
        'title': 'v1.0.0-GA - Production-Ready Hybrid Release',
        'description': 'Validate performance and scale, and publish a reproducible MIT-licensed release.',
        'issues': (
            (
                'Add k6 performance suites and release thresholds',
                'Create repeatable k6 smoke, load, and stress suites for the supported hybrid '
                'workflows. Define measurable latency/error thresholds, publish execution '
                'instructions, and attach results for the release candidate.',
            ),
            (
                'Validate multi-node cluster expansion',
                'Document and test expansion from the local baseline to a multi-node cluster. '
                'Verify node admission, workload placement, storage/network behavior, and '
                'recovery during a node interruption without weakening existing security policy.',
            ),
            (
                'Package a reproducible MIT-licensed release',
                'Prepare the release artifact and operator documentation, include the MIT '
                'license and required notices, and verify the package can be reproduced and '
                'installed from a clean environment. Publish checksums and the release manifest.',
            ),
        ),
    },
)


class RoadmapError(Exception):
    """An actionable roadmap API or configuration error."""


class GitHubAPI:
    def __init__(self, token, repository=REPOSITORY):
        self.repository = repository
        self.headers = {
            'Accept': 'application/vnd.github+json',
            'Authorization': f'Bearer {token}',
            'X-GitHub-Api-Version': '2022-11-28',
        }

    def request(self, method, path, payload=None):
        data = None
        headers = dict(self.headers)
        if payload is not None:
            data = json.dumps(payload).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        request = Request(
            f'{API_BASE}/repos/{self.repository}{path}',
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=30) as response:
                body = response.read()
        except HTTPError as error:
            detail = error.read().decode('utf-8', errors='replace')
            try:
                detail = json.loads(detail).get('message', detail)
            except (json.JSONDecodeError, AttributeError):
                pass
            raise RoadmapError(
                f'GitHub API returned HTTP {error.code} for {method} {path}: {detail}'
            ) from error
        except URLError as error:
            raise RoadmapError(f'GitHub API request failed for {method} {path}: {error.reason}') from error

        if not body:
            return None
        try:
            return json.loads(body.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RoadmapError(f'GitHub API returned invalid JSON for {method} {path}.') from error

    def list_all(self, path, **query):
        results = []
        page = 1
        while True:
            params = dict(query, per_page=PAGE_SIZE, page=page)
            page_results = self.request('GET', f'{path}?{urlencode(params)}')
            if not isinstance(page_results, list):
                raise RoadmapError(f'GitHub API returned an invalid listing for {path}.')
            results.extend(page_results)
            if len(page_results) < PAGE_SIZE:
                return results
            page += 1

    def milestones(self):
        return self.list_all(
            '/milestones', state='all', sort='due_on', direction='asc'
        )

    def issues(self):
        return self.list_all('/issues', state='all')


def _milestone_number(milestone):
    return milestone.get('number') if milestone else None


def manage_roadmap(api, dry_run=False, output=print):
    milestones = api.milestones()
    milestone_by_title = {}
    for milestone in milestones:
        if milestone.get('title') in {item['title'] for item in ROADMAP}:
            milestone_by_title[milestone['title']] = milestone

    closed = [
        title for title, milestone in milestone_by_title.items()
        if milestone.get('state') != 'open'
    ]
    if closed:
        titles = ', '.join(f'"{title}"' for title in closed)
        raise RoadmapError(f'Matching roadmap milestone is closed: {titles}. Reopen it before continuing.')

    issues = api.issues()
    issue_by_title = {}
    for issue in issues:
        if 'pull_request' not in issue:
            issue_by_title.setdefault(issue.get('title'), issue)

    for milestone_spec in ROADMAP:
        title = milestone_spec['title']
        milestone = milestone_by_title.get(title)
        if milestone is None:
            if dry_run:
                output(f'Would create milestone: {title}')
            else:
                milestone = api.request('POST', '/milestones', {
                    'title': title,
                    'description': milestone_spec['description'],
                    'state': 'open',
                })
                if not isinstance(milestone, dict) or not isinstance(milestone.get('number'), int):
                    raise RoadmapError(f'GitHub API returned an invalid milestone for "{title}".')
                milestone_by_title[title] = milestone
                output(f'Created milestone: {title}')

        milestone_number = _milestone_number(milestone)
        if milestone_number is None and not dry_run:
            raise RoadmapError(f'GitHub API listing has no number for milestone "{title}".')
        for issue_title, body in milestone_spec['issues']:
            issue = issue_by_title.get(issue_title)
            if issue is None:
                if dry_run:
                    output(f'Would create issue: {issue_title} (milestone: {title})')
                else:
                    created = api.request('POST', '/issues', {
                        'title': issue_title,
                        'body': body,
                        'milestone': milestone_number,
                    })
                    if not isinstance(created, dict) or not isinstance(created.get('number'), int):
                        raise RoadmapError(f'GitHub API returned an invalid issue for "{issue_title}".')
                    issue_by_title[issue_title] = created
                    output(f'Created issue #{created["number"]}: {issue_title}')
                continue

            if not isinstance(issue.get('number'), int):
                raise RoadmapError(f'GitHub API listing has no number for issue "{issue_title}".')
            current_milestone = _milestone_number(issue.get('milestone'))
            if current_milestone != milestone_number:
                if dry_run:
                    output(
                        f'Would assign issue #{issue["number"]} to milestone: {title}'
                    )
                else:
                    api.request('PATCH', f'/issues/{issue["number"]}', {
                        'milestone': milestone_number,
                    })
                    issue['milestone'] = milestone
                    output(f'Assigned issue #{issue["number"]} to milestone: {title}')

    if dry_run:
        output('Dry run complete; no changes were made.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='list intended changes without creating or updating anything',
    )
    args = parser.parse_args(argv)
    token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    if not token:
        print('Error: set GH_TOKEN or GITHUB_TOKEN to authenticate with GitHub.', file=sys.stderr)
        return 1
    try:
        manage_roadmap(GitHubAPI(token), dry_run=args.dry_run)
    except RoadmapError as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
