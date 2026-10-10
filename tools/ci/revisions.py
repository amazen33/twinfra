#!/usr/bin/env python3
"""Resolve revisions without inserting PR input into a shell or workflow syntax."""
import json
import os
from pathlib import Path
import re
import urllib.request

ROOT = Path(__file__).resolve().parent
REPOSITORY = 'amazen33/twinfra'


def commit(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{40}', value):
        raise ValueError('Expected an immutable 40-character commit SHA')
    return value


def resolve(requested, candidate, repository, fetch):
    if repository != REPOSITORY:
        raise ValueError('This workflow only tests amazen33/twinfra')
    if requested:
        if not re.fullmatch(r'[1-9][0-9]{0,8}', requested):
            raise ValueError('pr_number must be a positive integer of at most nine digits')
        data = fetch(int(requested))
        if data['base']['repo']['full_name'] != REPOSITORY or data['number'] != int(requested):
            raise ValueError('PR metadata does not match the requested repository/number')
        selected = data['merge_commit_sha'] if data.get('merged') else data['head']['sha']
        return dict(label='requested-pr-' + requested, commit=commit(selected))
    return dict(label='candidate', commit=commit(candidate))


def matrix(selected, baselines):
    if baselines['repository'] != REPOSITORY:
        raise ValueError('Historical baseline repository mismatch')
    entries = [selected]
    for baseline in baselines['baselines']:
        number = baseline['number']
        if type(number) is not int or number < 1:
            raise ValueError('Invalid historical PR number')
        sha = commit(baseline['commit'])
        if sha not in [entry['commit'] for entry in entries]:
            entries.append(dict(label=f'prior-pr-{number}', commit=sha))
    return dict(include=entries)


def main():
    def fetch(number):
        headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}
        token = os.environ.get('GH_TOKEN')
        if token:
            headers['Authorization'] = 'Bearer ' + token
        request = urllib.request.Request(f'https://api.github.com/repos/{REPOSITORY}/pulls/{number}', headers=headers)
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    selected = resolve(os.environ.get('REQUESTED_PR', '').strip(), os.environ['GITHUB_SHA'],
                       os.environ['GITHUB_REPOSITORY'], fetch)
    result = json.dumps(matrix(selected, json.loads((ROOT / 'pr-baselines.json').read_text())), separators=(',', ':'))
    with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
        output.write('matrix=' + result + '\n')
    print(result)


if __name__ == '__main__':
    main()
