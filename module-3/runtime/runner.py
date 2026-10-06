#!/usr/bin/env python3
"""Trusted CI entrypoint baked into the tooling image; never execute source with Git credentials."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

REPO = 'https://github.com/amazen33/vCloud.git'
BRANCH = 'gitops/prod'
IMAGE = 'registry.vcloud.example.com/vcloud/api'
MANIFEST = 'module-3/gitops/workload.yaml'


def revision(value):
    if not re.fullmatch(r'[0-9a-f]{40}', value) or value == '0' * 40:
        raise ValueError('A nonzero exact Git commit is required')
    return value


def digest(value):
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', value):
        raise ValueError('A SHA-256 OCI digest is required')
    return value


def run(argv, cwd=None, env=None):
    # No shell, command interpolation, credential-bearing URL or subprocess output in errors.
    result = subprocess.run([str(a) for a in argv], cwd=cwd, env=env,
                            text=True, capture_output=True, encoding='utf-8')
    if result.returncode:
        raise RuntimeError('Command failed: ' + str(argv[0]) + ' (exit ' + str(result.returncode) + ')')
    return result.stdout.strip()


def git_env(secret=None):
    env = os.environ.copy()
    env.update(GIT_TERMINAL_PROMPT='0', GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
               HOME='/tmp', GIT_CONFIG_COUNT='3', GIT_CONFIG_KEY_0='credential.helper',
               GIT_CONFIG_VALUE_0='', GIT_CONFIG_KEY_1='http.sslVerify', GIT_CONFIG_VALUE_1='true',
               GIT_CONFIG_KEY_2='core.hooksPath', GIT_CONFIG_VALUE_2=os.devnull)
    if secret:
        env['GIT_ASKPASS'] = '/opt/vcloud-ci/askpass.py'
        env['VCLOUD_GIT_SECRET_DIRECTORY'] = str(secret)
    return env


def clone(work, commit):
    commit = revision(commit)
    source = work / 'source'
    if source.exists():
        raise ValueError('Checkout directory already exists; use a fresh per-run CSI workspace')
    source.mkdir()
    env = git_env()
    observed=run(['git','ls-remote',REPO,'refs/heads/main'],env=env).split()[0]
    ensure_current_source(observed,commit)
    run(['git', 'init', '--quiet', source], env=env)
    run(['git', '-C', source, 'remote', 'add', 'origin', REPO], env=env)
    run(['git', '-C', source, 'fetch', '--depth=1', '--no-tags', 'origin', commit], env=env)
    if run(['git', '-C', source, 'rev-parse', 'FETCH_HEAD'], env=env) != commit:
        raise ValueError('Source commit drift')
    # No submodules or symlinks can escape the context or redirect later CI reads.
    tree = run(['git', '-C', source, 'ls-tree', '-r', commit], env=env)
    if any(line.startswith(('120000 ', '160000 ')) for line in tree.splitlines()):
        raise ValueError('Source symlinks and submodules require a separate reviewed build profile')
    run(['git', '-C', source, 'checkout', '--quiet', '--detach', commit], env=env)


def test(work):
    source = work / 'source'
    for command in [
        ['python3', 'tools/render_ssot.py', '--check'],
        ['python3', 'tools/render_cloud_init.py', '--check'],
        ['make', 'SITE=module-2/site-values.example.yaml', 'validate', 'test'],
        ['make', 'module3-validate', 'module3-test', 'module3-alerts'],
        ['make', 'module4a-validate', 'module4a-test'],
        ['make', 'module4b-validate', 'module4b-test']]:
        run(command, cwd=source)
    if (source / 'module-5b').exists():
        run(['make', 'module5b-validate', 'module5b-test', 'module5b-alerts'], cwd=source)
    print('Application tests, repository schemas and guardrail tests passed', flush=True)


def image_reference(commit, image_digest):
    return IMAGE + ':git-' + revision(commit) + '@' + digest(image_digest)


def build(work, commit, result_path):
    commit = revision(commit)
    # Never consult .git/config or files left by test code in a credential-bearing Task.
    build_workspace=work/'build-context'
    if build_workspace.exists(): raise ValueError('Build context already exists')
    build_workspace.mkdir()
    clone(build_workspace,commit) # fixed HTTPS repository, fresh Git config, exact tested SHA
    source=build_workspace/'source'
    metadata = work / 'build-metadata.json'
    epoch=run(['git','-C',source,'show','-s','--format=%ct',commit],env=git_env())
    if not epoch.isdigit(): raise ValueError('Invalid source timestamp')
    command = ['buildctl', '--addr', 'tcp://buildkit.vcloud.example.com:1234',
               '--tlsservername', 'buildkit.vcloud.example.com',
               '--tlscacert', '/var/run/vcloud/buildkit/ca.crt',
               '--tlscert', '/var/run/vcloud/buildkit/tls.crt',
               '--tlskey', '/var/run/vcloud/buildkit/tls.key',
               'build', '--frontend', 'dockerfile.v0',
               '--local', 'context=' + str(source / 'module-3/app'),
               '--local', 'dockerfile=' + str(source / 'module-3/app'),
               '--opt', 'platform=linux/amd64', '--opt', 'force-network-mode=none',
               '--opt', 'build-arg:SOURCE_REVISION=' + commit,
               '--opt', 'build-arg:SOURCE_DATE_EPOCH=' + epoch,
               '--output', 'type=image,name=' + IMAGE + ':git-' + commit + ',push=true,rewrite-timestamp=true',
               '--metadata-file', str(metadata)]
    run(command)
    image_digest = digest(json.loads(metadata.read_text())['containerimage.digest'])
    result_path.write_text(image_digest, encoding='utf-8')
    (work / 'candidate.json').write_text(json.dumps({'source': commit, 'digest': image_digest}) + '\n',
                                       encoding='utf-8', newline='\n')
    print('Built and published ' + image_reference(commit, image_digest), flush=True)


def update_manifest(path, commit, image_digest):
    # Manifest contains JSON (valid YAML); no YAML serializer can alter sibling documents.
    if path.is_symlink() or not path.is_file():
        raise ValueError('GitOps manifest must be an existing regular file')
    obj = json.loads(path.read_text())
    if (obj.get('apiVersion'), obj.get('kind'), obj.get('metadata', {}).get('name'),
        obj.get('metadata', {}).get('namespace')) != ('serving.knative.dev/v1', 'Service', 'vcloud-api', 'workload-apps'):
        raise ValueError('GitOps workload identity drift')
    containers = obj['spec']['template']['spec']['containers']
    if len(containers) != 1 or containers[0]['name'] != 'api':
        raise ValueError('GitOps container identity drift')
    old = obj.get('metadata', {}).get('annotations', {}).get('vcloud.io/source-revision')
    image = image_reference(commit, image_digest)
    if old == commit and containers[0]['image'] != image:
        raise ValueError('Same source produced a different digest; review reproducibility before promotion')
    obj['metadata'].setdefault('annotations', {})['vcloud.io/source-revision'] = revision(commit)
    containers[0]['image'] = image
    return obj


def ensure_current_source(observed_tip, candidate):
    if revision(observed_tip) != revision(candidate):
        raise ValueError('Stale build: protected main has advanced; do not promote this run')


def publish(work, commit, image_digest, result_path):
    commit, image_digest = revision(commit), digest(image_digest)
    destination = work / 'gitops'
    env = git_env('/var/run/vcloud/git')
    if destination.exists():
        raise ValueError('Promotion directory already exists')
    run(['git', 'clone', '--quiet', '--single-branch', '--branch', BRANCH, '--no-tags', REPO, destination], env=env)
    run(['git', '-C', destination, 'config', 'user.name', 'vCloud GitOps Bot'], env=env)
    run(['git', '-C', destination, 'config', 'user.email', 'vcloud-gitops-bot@users.noreply.github.com'], env=env)
    for attempt in range(3):
        tip = run(['git', '-C', destination, 'ls-remote', 'origin', 'refs/heads/main'], env=env).split()[0]
        ensure_current_source(tip, commit)
        path = destination / MANIFEST
        if any(parent.is_symlink() for parent in (path, *path.parents)):
            raise ValueError('GitOps path ancestry contains a symlink')
        candidate = update_manifest(path, commit, image_digest)
        path.write_text(json.dumps(candidate, indent=2) + '\n', encoding='utf-8', newline='\n')
        # Trusted image verifier audits the exact final candidate, not a source-controlled script.
        run(['python3', '/opt/vcloud-ci/validate_workload.py', str(path)])
        schemas = Path('/opt/vcloud-ci/schemas')
        run(['kubeconform', '-strict', '-summary', '-schema-location',
             str(schemas / '{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json'), str(path)])
        run(['git', '-C', destination, 'add', '--', MANIFEST], env=env)
        changes = run(['git', '-C', destination, 'diff', '--cached', '--name-only'], env=env).splitlines()
        if not changes:
            result_path.write_text(run(['git', '-C', destination, 'rev-parse', 'HEAD'], env=env), encoding='utf-8')
            print('Digest already promoted; no new commit', flush=True)
            return
        if changes != [MANIFEST]:
            raise ValueError('Promotion attempted to change an unauthorized GitOps path')
        run(['git', '-C', destination, 'commit', '--quiet', '-m', 'ci: promote vcloud-api ' + commit], env=env)
        try:
            # Ordinary fast-forward push; never force or overwrite another publisher.
            run(['git', '-C', destination, 'push', '--porcelain', 'origin', 'HEAD:refs/heads/' + BRANCH], env=env)
        except RuntimeError:
            if attempt == 2:
                raise
            run(['git', '-C', destination, 'fetch', '--no-tags', 'origin', BRANCH], env=env)
            run(['git', '-C', destination, 'reset', '--hard', 'FETCH_HEAD'], env=env) # isolated per-run clone only
            time.sleep(1)
            continue
        result_path.write_text(run(['git', '-C', destination, 'rev-parse', 'HEAD'], env=env), encoding='utf-8')
        print('Promoted verified digest through Git; Argo CD reconciles the workload', flush=True)
        return


def main():
    command = sys.argv[1]
    work = Path(os.environ['VCLOUD_WORKSPACE'])
    work.mkdir(parents=True, exist_ok=True)
    commit = os.environ.get('VCLOUD_REVISION', '')
    if command == 'clone': clone(work, commit)
    elif command == 'test': test(work)
    elif command == 'build': build(work, commit, Path(os.environ['VCLOUD_DIGEST_RESULT']))
    elif command == 'publish': publish(work, commit, os.environ['VCLOUD_DIGEST'], Path(os.environ['VCLOUD_COMMIT_RESULT']))
    else: raise ValueError('Unknown CI action')


if __name__ == '__main__':
    main()
