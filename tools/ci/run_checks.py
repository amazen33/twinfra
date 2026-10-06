#!/usr/bin/env python3
"""Run the repository's offline gates, including gates absent from old workflows.

The selected revision supplies module implementations; the current CI checkout
supplies the harness and dependency locks. No host provisioning, cluster apply,
credential issuance or external delivery operation is performed.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

import yaml

ROOT = Path(__file__).resolve().parent
OPTIONAL = {
    'module-3': ['tools/module3.py', 'tools/render_module3.py', 'tests/test_module3.py',
                 'tests/module3-alerts.test.yaml', 'module-3/app/test_app.py'],
    'module-4a': ['tools/module4a.py', 'tools/render_module4a.py', 'tests/test_module4a.py'],
    'module-4b': ['tools/module4b.py', 'tools/render_module4b.py', 'tests/test_module4b.py'],
    'module-5a': ['tools/module5a.py', 'tools/render_module5a.py', 'tools/stage_module5a_models.py', 'tools/module5a_encoder_smoke.py',
                  'tests/test_module5a.py', 'module-5a/config/rag.yaml', 'module-5a/rag/pipeline.py',
                  'module-5a/sql/migrate.sql', 'module-5a/examples/vllm.knative.yaml',
                  'module-5a/requirements-runtime.lock.txt', 'module-5a/images/rag.Dockerfile',
                  'module-5a/README.md'],
    'module-5b': ['tools/module5b.py', 'tools/render_module5b.py', 'tests/test_module5b.py',
                  'tests/module5b-alerts.test.yaml', 'module-5b/reference-profile.json'],
    'lab/wsl': ['lab/wsl/profile.json', 'lab/wsl/bootstrap.sh', 'lab/wsl/api-firewall.sh',
                'tools/wsl_lab.py', 'tools/wsl_lab_acceptance.py', 'tools/wsl_lab_dns_image.py', 'tools/stage_wsl_lab.py',
                'tests/test_wsl_lab.py'],
    'lab/wsl/gitops': ['tools/wsl_platform.py', 'tools/wsl_db_scaler.py', 'tools/wsl_db_test.py', 'tools/wsl_pg_image.py',
                       'tools/stage_wsl_platform.py', 'lab/wsl/platform.sh', 'lab/wsl/prepare-storage.sh',
                       'lab/wsl/prepare-tls.sh', 'lab/wsl/test-network.sh', 'lab/wsl/platform-artifacts.lock.json',
                       'lab/wsl/gitops/workload.yaml', 'lab/wsl/gitops/network.yaml', 'tests/test_wsl_platform.py'],
}


def coverage(source):
    required = ['00-setup-ubuntu-host.sh', 'user-data.yaml', 'tests/test_bootstrap.py',
                'tools/render_ssot.py', 'tools/render_cloud_init.py', 'docs/module-1-topology.md',
                'tools/module2.py', 'tests/test_module2.py', 'module-2/vendor/cilium-1.20.2.tgz']
    missing = [file for file in required if not (source / file).is_file()]
    if missing:
        raise ValueError('Required baseline files missing: ' + ', '.join(missing))
    result = {'module--1': 'present', 'module-1': 'present', 'module-2': 'present'}
    for name, files in OPTIONAL.items():
        present = (source / name).exists() or any((source / file).exists() for file in files)
        if present and not all((source / file).is_file() for file in files):
            raise ValueError('Incomplete ' + name + ' implementation; refusing to omit its tests')
        result[name] = 'present' if present else 'not_present_in_revision'
    return result


def require_complete_tests(output):
    match = re.search(r'^Ran (\d+) tests? in ', output, re.MULTILINE)
    if not match or int(match[1]) == 0 or not re.search(r'^OK\s*$', output, re.MULTILINE):
        raise ValueError('Test runner did not report a complete, successful suite without skips')
    return int(match[1])


def prepare_workspace(source):
    # Existing host tests pass -cache to kubeconform. It requires the directory
    # to exist even when every schema is provided locally by the CI wrapper.
    (source / '.tools/schema-cache').mkdir(parents=True, exist_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    for name in ('bash', 'helm', 'kubeconform', 'shellcheck', 'promtool', 'yq', 'jq', 'node'):
        parser.add_argument('--' + name)
    args = parser.parse_args()
    source, assets, report_dir = args.source.resolve(), args.assets.resolve(), args.report.resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    binaries = {name: str(getattr(args, name) or assets / 'bin' / name)
                for name in ('helm', 'kubeconform', 'shellcheck', 'promtool', 'yq', 'jq')}
    binaries.update(bash=args.bash or 'bash', node=args.node or 'node')
    binaries = {name: str(Path(value).resolve()) if Path(value).is_file() else value
                for name, value in binaries.items()}
    env = dict(os.environ)
    env['PATH'] = str(assets / 'bin') + os.pathsep + env['PATH']
    env['BASH_BINARY'], env['JQ_BINARY'] = binaries['bash'], binaries['jq']
    env['HELM'], env['KUBECONFORM'] = binaries['helm'], binaries['kubeconform']
    report = dict(status='running', scope='offline validation; no live acceptance', tests=0, checks=[])

    def run(label, command, *, unit=False):
        start = time.monotonic()
        result = subprocess.run([str(part) for part in command], cwd=source, env=env,
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (report_dir / (label + '.log')).write_text(result.stdout, encoding='utf-8', newline='\n')
        check = dict(name=label, status='passed' if result.returncode == 0 else 'failed',
                     exitCode=result.returncode, seconds=round(time.monotonic() - start, 2))
        report['checks'].append(check)
        if result.returncode:
            print(result.stdout[-12000:], file=sys.stderr)
            raise RuntimeError(label + ' failed')
        if unit:
            check['tests'] = require_complete_tests(result.stdout)
            report['tests'] += check['tests']
        print(label + ': passed', flush=True)
        return result.stdout

    try:
        sha = run('selected-commit', ['git', 'rev-parse', 'HEAD']).strip()
        if os.environ.get('EXPECTED_COMMIT') and sha != os.environ['EXPECTED_COMMIT']:
            raise ValueError('Selected checkout differs from the resolved immutable commit')
        report['commit'] = sha
        report['workingTreeChanges'] = run('selected-tree', ['git', 'status', '--porcelain']).splitlines()
        report['modules'] = coverage(source)
        python = sys.executable
        run('ssot-drift', [python, 'tools/render_ssot.py', '--check'])
        run('cloud-init-drift', [python, 'tools/render_cloud_init.py', '--check'])
        prepare_workspace(source)
        rendered = source / '.tools/rendered'
        run('host-fixtures', [python, 'tests/test_bootstrap.py', '--bash', binaries['bash'],
                              '--render-dir', rendered, '--render-only'])
        cilium = run('host-cilium-render', [binaries['helm'], 'template', 'cilium',
                      'module-2/vendor/cilium-1.20.2.tgz', '--namespace', 'kube-system',
                      '-f', rendered / 'cilium-values.yaml'])
        (rendered / 'cilium-rendered.yaml').write_text(cilium, encoding='utf-8', newline='\n')
        nvidia = run('host-nvidia-render', [binaries['helm'], 'template', 'nvidia-device-plugin',
                      assets / 'nvidia-device-plugin-0.20.1.tgz', '--namespace', 'kube-system',
                      '--set', 'runtimeClassName=nvidia', '--set', 'gfd.enabled=false',
                      '--set', 'nfd.enabled=false', '--set',
                      'image.repository=registry.vcloud.example.com/nvcr.io/nvidia/k8s-device-plugin',
                      '--set', 'image.tag=v0.20.1'])
        (rendered / 'nvidia-raw.yaml').write_text(nvidia, encoding='utf-8', newline='\n')
        objects = [obj for obj in yaml.safe_load_all(nvidia) if obj and
                   not (obj['kind'] == 'DaemonSet' and obj['metadata']['name'] == 'nvidia-device-plugin-mps-control-daemon')]
        # The host suite separately exercises the real generated post-renderer,
        # including malformed schemas and forbidden mounts, using mock transports.
        (rendered / 'nvidia-rendered.yaml').write_text(yaml.safe_dump_all(objects), encoding='utf-8', newline='\n')
        schema_files = [rendered / name for name in ('cilium-rendered.yaml', 'nvidia-rendered.yaml',
                       'foundation.yaml', 'smoke-base.yaml', 'smoke-allowed.yaml', 'smoke-denied.yaml',
                       'smoke-hugepages.yaml', 'smoke-gpu.yaml', 'runtimeclass.yaml')]
        schema_options = []
        for template in (assets / 'schemas/{{.ResourceKind}}.json',
                         source / 'module-2/schemas/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json',
                         source / 'module-2/schemas/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json'):
            schema_options.extend(['-schema-location', str(template)])
        run('host-schema', [binaries['kubeconform'], '-strict', '-summary', '-kubernetes-version', '1.36.5', *schema_options, *schema_files])
        run('host-tests', [python, 'tests/test_bootstrap.py', '--bash', binaries['bash'],
                           '--cloud-schema', assets / 'cloud-config-schema.json', '--render-dir', rendered,
                           '--yq', binaries['yq'], '--kubeconform', binaries['kubeconform']], unit=True)
        run('topology-parser', [binaries['node'], ROOT / 'mermaid/check.mjs', source, report_dir / 'mermaid.json'])
        run('architecture-docs', [python, ROOT / 'check_docs.py', source, report_dir / 'architecture.json', report_dir / 'mermaid.json'])
        shell_files = [source / '00-setup-ubuntu-host.sh']
        for module in OPTIONAL:
            if report['modules'][module] == 'present':
                shell_files.extend(sorted((source / module).rglob('*.sh')))
        run('shellcheck', [binaries['shellcheck'], '-S', 'style', *shell_files])
        run('module2-validate', [python, 'tools/module2.py', '--site', 'module-2/site-values.example.yaml',
                                '--helm', binaries['helm'], '--kubeconform', binaries['kubeconform'], 'validate'])
        run('module2-tests', [python, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_module2.py', '-v'], unit=True)
        for module, stem in [('module-3', 'module3'), ('module-4a', 'module4a'), ('module-4b', 'module4b'), ('module-5a', 'module5a'), ('module-5b', 'module5b')]:
            if report['modules'][module] == 'not_present_in_revision':
                print(module + ': absent from historical revision', flush=True)
                continue
            options = ['--helm', binaries['helm']] if stem == 'module5b' else []
            run(stem + '-validate', [python, f'tools/{stem}.py', '--kubeconform', binaries['kubeconform'], *options])
            run(stem + '-tests', [python, '-m', 'unittest', 'discover', '-s', 'tests', '-p', f'test_{stem}.py', '-v'], unit=True)
            if stem == 'module3':
                run('app-tests', [python, '-m', 'unittest', 'discover', '-s', 'module-3/app', '-p', 'test_app.py', '-v'], unit=True)
                run('alert-rules', [binaries['promtool'], 'check', 'rules', 'module-3/observability/rules.yaml'])
                run('alert-tests', [binaries['promtool'], 'test', 'rules', 'tests/module3-alerts.test.yaml'])
            if stem == 'module5b':
                run('hpc-alert-rules', [binaries['promtool'], 'check', 'rules', 'module-5b/observability/rules.yaml'])
                run('hpc-alert-tests', [binaries['promtool'], 'test', 'rules', 'tests/module5b-alerts.test.yaml'])
        if report['modules']['lab/wsl'] == 'present':
            # Offline renders must never overwrite an active lab's live evidence
            # or address-specific Helm values in .build/wsl-lab.
            wsl_build = report_dir / 'wsl-rendered'
            run('wsl-lab-render', [python, 'tools/wsl_lab.py', 'render', '--build', wsl_build])
            run('wsl-lab-validate', [python, 'tools/wsl_lab.py', 'validate', '--helm', binaries['helm'],
                                   '--kubeconform', binaries['kubeconform'], '--schemas', assets / 'schemas',
                                   '--build', wsl_build])
            run('wsl-lab-tests', [python, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_wsl_lab.py', '-v'], unit=True)
        if report['modules']['lab/wsl/gitops'] == 'present':
            platform_build = report_dir / 'wsl-platform-rendered'
            run('wsl-platform-render', [python, 'tools/wsl_platform.py', 'render', '--build', platform_build])
            run('wsl-platform-validate', [python, 'tools/wsl_platform.py', 'validate', '--build', platform_build,
                                        '--kubeconform', binaries['kubeconform'], '--schemas', assets / 'schemas'])
            run('wsl-platform-tests', [python, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_wsl_platform.py', '-v'], unit=True)
        report['status'] = 'passed'
        return 0
    except (ValueError, RuntimeError, OSError) as error:
        report['status'], report['error'] = 'failed', str(error)
        print(str(error), file=sys.stderr)
        return 1
    finally:
        (report_dir / 'summary.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')


if __name__ == '__main__':
    raise SystemExit(main())
