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
    'dev-runnable': ['tools/platform_dev_ca.py','tools/platform_image_staging.py','tools/platform_bootstrap_inventory.py','deploy/common/stage-images.py','deploy/common/bootstrap-images.lock.json','deploy/common/vendor/kubeadm-constants-v1.36.5.go','tests/test_dev_runnable.py','docs/work-orders/WO-29-make-dev-environment-runnable.md'],
    'deploy/hyperv': ['deploy/hyperv/New-TwinfraDev.ps1','deploy/hyperv/Twinfra.psm1','deploy/hyperv/test-plan.ps1','deploy/hyperv/qcow2_to_vhd.py','deploy/hyperv/ubuntu-image.lock.json','deploy/upstream-names.json','tools/platform_dev.py','tools/platform_validate.py','tools/check_upstream_names.py','tests/test_dev_environment.py','deploy/environments/dev/cairo-1/root.yaml','deploy/environments/dev/cairo-1/platform/workloads.yaml','deploy/environments/dev/cairo-1/services/workloads.yaml'],
    'console': ['console/package.json', 'console/package-lock.json', 'console/server.py', 'console/Dockerfile',
        'console/image.lock.json', 'console/src/App.tsx', 'console/src/App.test.tsx', 'console/src/styles.css',
        'tools/vcloud_console.py', 'tools/configure_console_identity.py', 'tools/build_console_image.py',
        'tools/test_console_live.py', 'console/browser-acceptance.mjs', 'console/browser-login.mjs', 'console/README.md',
        'deploy/console/deploy-wsl.py', 'deploy/console/copy-password.ps1',
        'tests/test_vcloud_console.py', 'deploy/console/profile.json', 'deploy/console/deployment.yaml',
        'deploy/console/service.yaml', 'deploy/console/bootstrap.yaml', 'deploy/console/apisix-routes.yaml', 'deploy/console/callback-guard.lua',
        'deploy/console/keycloak-client.json', 'deploy/console/argocd.yaml', 'deploy/console/gitops/workloads.yaml'],
    'keycloak-admin-bootstrap': ['tools/wsl_keycloak_admin.py', 'tests/test_wsl_keycloak_admin.py',
        'lab/wsl/endpoints/copy-keycloak-password.ps1', 'docs/keycloak-admin-access.md'],
    'lab/wsl/console': ['tools/wsl_console.py', 'tools/wsl_console_preflight.py', 'tests/test_wsl_console.py',
        'lab/wsl/console/profile.json', 'lab/wsl/console/artifacts.lock.json', 'lab/wsl/console/ui.py',
        'lab/wsl/console/keycloak-client.json', 'lab/wsl/console/test-backends.py', 'lab/wsl/console/test-denied.py', 'lab/wsl/console/workloads.yaml', 'lab/wsl/console/network.yaml',
        'lab/wsl/console/apisix-routes.yaml', 'lab/wsl/console/gitops/workloads.yaml',
        'lab/wsl/console/reference/apisix-routes-disabled.yaml', 'lab/wsl/console/reference/argocd.yaml',
        'lab/wsl/console/deploy-backends.sh', 'lab/wsl/console/apply.sh', 'lab/wsl/console/verify.sh',
        'lab/wsl/console/README.md', 'lab/wsl/console/LICENSE'],
    'lab/wsl/localstack': ['lab/wsl/localstack/artifacts.lock.json','lab/wsl/localstack/deployment.yaml',
        'lab/wsl/localstack/service.yaml','lab/wsl/localstack/apisix-route.yaml',
        'lab/wsl/localstack/configure-apisix.py','lab/wsl/localstack/access.sh',
        'lab/wsl/localstack/deploy.sh',
        'lab/wsl/localstack/verify.sh','lab/wsl/localstack/test-api.py',
        'tools/wsl_localstack.py','tests/test_wsl_localstack.py'],
    'lab/wsl/values': ['lab/wsl/values/cilium-routing.yaml', 'tools/check_host_routing.py',
                       'tests/test_host_routing.py'],
    'roadmap-automation': ['tools/create_roadmap_issues.py', 'tests/test_roadmap_issues.py'],
    'deploy/network/platform-probes': ['deploy/network/platform-probes/cilium-platform-probes.yaml',
                                      'deploy/network/platform-probes/k8s-platform-probes.yaml',
                                      'deploy/network/platform-probes/apply-and-verify.sh',
                                      'deploy/network/platform-probes/recover.sh',
                                      'deploy/network/platform-probes/README.md',
                                      'tests/test_platform_probes.py'],
    'deploy/kustomize': ['deploy/registry-images.lock.json', 'deploy/required-images.txt',
                         'deploy/vendor/argocd-v3.5.3-install.yaml.gz',
                         'deploy/kustomize/base/argocd/install.yaml',
                         'deploy/kustomize/overlays/vcloud-local/kustomization.yaml',
                         'tools/airgap.py', 'tools/node_registry.py', 'scripts/bootstrap-node.sh',
                         'scripts/validate-node.sh', 'tests/ci/test_airgap.py', 'tests/ci/policy/airgap.rego',
                         'tests/ci/policy/airgap_test.rego'],
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
    'lab/wsl/endpoints': ['lab/wsl/endpoints/artifacts.lock.json', 'lab/wsl/endpoints/deploy.sh', 'lab/wsl/endpoints/access.sh',
                'lab/wsl/endpoints/runtime-config.py','lab/wsl/endpoints/demo.py','tools/wsl_endpoints.py',
                'tools/openbao_pgp_init.py','tools/wsl_endpoint_acceptance.py','lab/wsl/test-e2e.sh',
                'tools/wsl_endpoints_gitops.py','lab/wsl/endpoints/argocd.yaml','lab/wsl/endpoints/gitops/workloads.yaml',
                'lab/wsl/reconcile-host-routing.sh','tools/wsl_runtime_secrets.py','tools/wsl_git_dns.py',
                'lab/wsl/openbao-init.sh','tests/test_openbao_pgp_init.py','tests/test_wsl_endpoints.py'],
    'lab/wsl': ['lab/wsl/profile.json', 'lab/wsl/bootstrap.sh', 'lab/wsl/api-firewall.sh',
                'tools/wsl_lab.py', 'tools/wsl_lab_acceptance.py', 'tools/wsl_lab_dns_image.py', 'tools/stage_wsl_lab.py',
                'tests/test_wsl_lab.py'],
    'lab/wsl/proxy-marks': ['tools/wsl_proxy_marks.py', 'lab/wsl/vcloud-wsl-proxy-marks.service',
                          'lab/wsl/vcloud-wsl-proxy-marks.timer'],
    'lab/wsl/loopback': ['tools/wsl_loopback_routing.py', 'tests/test_wsl_loopback.py'],
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
    for name in ('bash', 'helm', 'kubeconform', 'shellcheck', 'promtool', 'yq', 'jq', 'node', 'kustomize', 'conftest'):
        parser.add_argument('--' + name)
    args = parser.parse_args()
    source, assets, report_dir = args.source.resolve(), args.assets.resolve(), args.report.resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    binaries = {name: str(getattr(args, name) or assets / 'bin' / name)
                for name in ('helm', 'kubeconform', 'shellcheck', 'promtool', 'yq', 'jq', 'kustomize', 'conftest')}
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
        # Governance is evaluated against the CI control checkout (the candidate),
        # never against the dependencies of the six pre-policy historical revisions.
        run('candidate-licences', [python, ROOT / 'check_licences.py', '--root', ROOT.parents[1],
                                  '--report', report_dir / 'licences.json'])
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
        if report['modules']['roadmap-automation'] == 'present':
            run('roadmap-tests', [python, '-m', 'unittest', 'discover', '-s', 'tests',
                                 '-p', 'test_roadmap_issues.py', '-v'], unit=True)
        shell_files = [source / '00-setup-ubuntu-host.sh']
        if report['modules']['deploy/kustomize'] == 'present':
            shell_files.extend(sorted((source / 'scripts').rglob('*.sh')))
        for module in OPTIONAL:
            if report['modules'][module] == 'present':
                shell_files.extend(sorted((source / module).rglob('*.sh')))
        run('shellcheck', [binaries['shellcheck'], '-S', 'style', *shell_files])
        if report['modules']['deploy/network/platform-probes'] == 'present':
            run('platform-probe-schema', [binaries['kubeconform'], '-strict', '-summary',
                '-kubernetes-version', '1.36.5', *schema_options,
                source / 'deploy/network/platform-probes/cilium-platform-probes.yaml',
                source / 'deploy/network/platform-probes/k8s-platform-probes.yaml'])
            run('platform-probe-tests', [python, '-m', 'unittest', 'discover', '-s', 'tests',
                                       '-p', 'test_platform_probes.py', '-v'], unit=True)
        if report['modules']['deploy/kustomize'] == 'present':
            run('airgap-validate', [python, 'tools/airgap.py', '--build', report_dir / 'airgap-rendered',
                                  '--kustomize', binaries['kustomize'], '--kubeconform', binaries['kubeconform'],
                                  '--conftest', binaries['conftest']])
            run('airgap-tests', [python, '-m', 'unittest', 'discover', '-s', 'tests/ci', '-v'], unit=True)
        run('module2-validate', [python, 'tools/module2.py', '--site', 'module-2/site-values.example.yaml',
                                '--helm', binaries['helm'], '--kubeconform', binaries['kubeconform'], 'validate'])
        for chart in ('cilium-1.20.2','apisix-2.18.0'):
            run(chart+'-helm-lint',[binaries['helm'],'lint','module-2/vendor/'+chart+'.tgz',
                                  '-f','module-2/values/'+chart.split('-')[0]+'.yaml'])
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
                run('kueue-helm-lint',[binaries['helm'],'lint','module-5b/vendor/kueue-0.20.0.tgz',
                                     '-f','module-5b/values/kueue.yaml'])
                run('hpc-alert-rules', [binaries['promtool'], 'check', 'rules', 'module-5b/observability/rules.yaml'])
                run('hpc-alert-tests', [binaries['promtool'], 'test', 'rules', 'tests/module5b-alerts.test.yaml'])
        if report['modules']['deploy/hyperv'] == 'present':
            dev_build=report_dir/'dev-rendered'
            run('dev-render-drift',[python,'tools/platform_dev.py','check'])
            run('neutral-source-drift',[python,'tools/platform_sources.py','check'])
            run('dev-conformance-tests',[python,'-m','unittest','discover','-s','tests','-p','test_dev_environment.py','-v'],unit=True)
            run('hyperv-offline-plan',['pwsh','-NoProfile','-File','deploy/hyperv/test-plan.ps1'])
            run('worker-join-shellcheck',[binaries['shellcheck'],'deploy/common/join-worker.sh'])
            run('dev-schema-policy',[python,'tools/platform_validate.py','--helm',binaries['helm'],'--kustomize',binaries['kustomize'],'--kubeconform',binaries['kubeconform'],'--conftest',binaries['conftest'],'--bash',binaries['bash'],'--schemas',assets/'schemas','--build',dev_build])
        if report['modules']['dev-runnable'] == 'present':
            run('dev-runnable-tests',[python,'-m','unittest','discover','-s','tests','-p','test_dev_runnable.py','-v'],unit=True)
            run('dev-bootstrap-image-inventory',[python,'tools/platform_bootstrap_inventory.py','--bash',binaries['bash'],'--helm',binaries['helm']])
        if report['modules']['lab/wsl'] == 'present':
            # Offline renders must never overwrite an active lab's live evidence
            # or address-specific Helm values in .build/wsl-lab.
            wsl_build = report_dir / 'wsl-rendered'
            run('wsl-lab-render', [python, 'tools/wsl_lab.py', 'render', '--build', wsl_build])
            run('wsl-lab-validate', [python, 'tools/wsl_lab.py', 'validate', '--helm', binaries['helm'],
                                   '--kubeconform', binaries['kubeconform'], '--schemas', assets / 'schemas',
                                   '--build', wsl_build])
            run('wsl-lab-tests', [python, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_wsl_lab.py', '-v'], unit=True)
        if report['modules']['lab/wsl/loopback'] == 'present':
            run('wsl-loopback-tests', [python, '-m', 'unittest', 'discover', '-s', 'tests',
                                      '-p', 'test_wsl_loopback.py', '-v'], unit=True)
        if report['modules']['lab/wsl/values'] == 'present':
            run('host-routing-governance', [python, ROOT.parent / 'check_host_routing.py',
                '--root', source, '--helm', binaries['helm'], '--build', report_dir / 'host-routing'])
            run('host-routing-tests', [python, '-m', 'unittest', 'discover', '-s', 'tests',
                                      '-p', 'test_host_routing.py', '-v'], unit=True)
        if report['modules']['lab/wsl/gitops'] == 'present':
            platform_build = report_dir / 'wsl-platform-rendered'
            run('wsl-platform-render', [python, 'tools/wsl_platform.py', 'render', '--build', platform_build])
            run('wsl-platform-validate', [python, 'tools/wsl_platform.py', 'validate', '--build', platform_build,
                                        '--kubeconform', binaries['kubeconform'], '--schemas', assets / 'schemas'])
            run('wsl-platform-tests', [python, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_wsl_platform.py', '-v'], unit=True)
        if report['modules']['lab/wsl/endpoints'] == 'present':
            endpoint_build=report_dir/'wsl-endpoints-rendered'
            run('wsl-endpoints-render',[python,'tools/wsl_endpoints.py','render','--build',endpoint_build])
            run('wsl-endpoints-schema',[python,'tools/wsl_endpoints.py','validate','--build',endpoint_build,
                '--kubeconform',binaries['kubeconform'],'--schemas',assets/'schemas'])
            run('wsl-endpoints-gitops',[python,'tools/wsl_endpoints_gitops.py','--check','--build',endpoint_build,
                '--kubeconform',binaries['kubeconform'],'--schemas',assets/'schemas'])
            run('wsl-endpoints-pss',[binaries['conftest'],'test','--namespace','vcloud_wsl','--policy','tests/ci/policy/wsl-endpoints.rego',
                 endpoint_build/'controllers.yaml',endpoint_build/'identity.yaml',endpoint_build/'application.yaml',endpoint_build/'observability.yaml'])
            for suite in ('test_wsl_endpoints.py','test_openbao_pgp_init.py'):
                run(suite[:-3],[python,'-m','unittest','discover','-s','tests','-p',suite,'-v'],unit=True)
        if report['modules']['lab/wsl/localstack'] == 'present':
            run('wsl-localstack-tests',[python,'-m','unittest','discover','-s','tests','-p','test_wsl_localstack.py','-v'],unit=True)
        if report['modules']['keycloak-admin-bootstrap'] == 'present':
            admin_pod = report_dir/'keycloak-admin-bootstrap.json'
            run('keycloak-admin-tests',[python,'-m','unittest','discover','-s','tests','-p','test_wsl_keycloak_admin.py','-v'],unit=True)
            run('keycloak-admin-render',[python,'tools/wsl_keycloak_admin.py','--render-pod',admin_pod])
            run('keycloak-admin-schema',[binaries['kubeconform'],'-strict','-summary','-schema-location',
                str(assets/'schemas/{{.ResourceKind}}.json'),admin_pod])
            run('keycloak-admin-pss',[binaries['conftest'],'test','--namespace','vcloud_wsl','--policy',
                'tests/ci/policy/wsl-endpoints.rego',admin_pod])
        if report['modules']['lab/wsl/console'] == 'present':
            run('wsl-console-render',[python,'tools/wsl_console.py','--check'])
            run('wsl-console-tests',[python,'-m','unittest','discover','-s','tests','-p','test_wsl_console.py','-v'],unit=True)
            run('wsl-console-schema',[python,'tools/wsl_console.py','--validate','--build',endpoint_build,
                '--kubeconform',binaries['kubeconform'],'--schemas',assets/'schemas'])
            run('wsl-console-pss',[binaries['conftest'],'test','--namespace','vcloud_wsl','--policy','tests/ci/policy/wsl-endpoints.rego',
                'lab/wsl/console/workloads.yaml','lab/wsl/console/gitops/workloads.yaml'])
            run('wsl-console-shellcheck',[binaries['shellcheck'],'lab/wsl/console/deploy-backends.sh','lab/wsl/console/apply.sh','lab/wsl/console/verify.sh'])
        if report['modules']['console'] == 'present':
            run('portal-render',[python,'tools/vcloud_console.py','--check'])
            run('portal-tests',[python,'-m','unittest','discover','-s','tests','-p','test_vcloud_console.py','-v'],unit=True)
            run('portal-schema',[python,'tools/vcloud_console.py','--validate','--build',report_dir/'portal-schema',
                '--kubeconform',binaries['kubeconform'],'--schemas',assets/'schemas'])
            run('portal-pss',[binaries['conftest'],'test','--namespace','vcloud_wsl','--policy','tests/ci/policy/wsl-endpoints.rego',
                'deploy/console/deployment.yaml','deploy/console/gitops/workloads.yaml'])
        control_sha = subprocess.check_output(['git', '-C', str(ROOT.parents[1]), 'rev-parse', 'HEAD'], text=True).strip()
        if sha == control_sha:
            # Inspect actual locked-chart renders as well as checked-in generator output.
            # Do not classify historical render contents using the new policy.
            render_inputs = [rendered / 'cilium-rendered.yaml', rendered / 'nvidia-rendered.yaml']
            # WO-25: classify the actual Argo base, every overlay, and WSL output.
            if report['modules']['deploy/kustomize'] == 'present':
                render_inputs.extend(sorted((report_dir / 'airgap-rendered').glob('*.yaml')))
            if report['modules']['lab/wsl/gitops'] == 'present':
                render_inputs.extend(sorted(platform_build.glob('*.yaml')))
            if report['modules']['deploy/hyperv']=='present':render_inputs.extend([dev_build/'dev.yaml',dev_build/'cilium.yaml'])
            render_options = [part for file in render_inputs for part in ('--rendered', file)]
            run('candidate-rendered-licences', [python, ROOT / 'check_licences.py', '--root', ROOT.parents[1],
                                              '--report', report_dir / 'licences.json', *render_options])
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
