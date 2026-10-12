#!/usr/bin/env python3
"""Real kubeadm manifest preview on a disposable Ubuntu CI runner only.

No kubelet, CRI, image pull, cluster initialization or host provisioner is run.
Sudo generates manifests with --dry-run, then returns only those four public
Pod YAML files to the runner user for assertion and artifact upload.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import urllib.request

VERSION = 'v1.36.5'
URL = 'https://dl.k8s.io/release/' + VERSION + '/bin/linux/amd64/kubeadm'
SHA256 = 'be2f2c73cd6d3414b37aafb05016bc3a1da3e17c8393aa75c34636198fefa77c'
MANIFESTS = ('kube-apiserver.yaml', 'kube-controller-manager.yaml', 'kube-scheduler.yaml', 'etcd.yaml')


def verify_binary(binary, published, expected=None):
    expected = SHA256 if expected is None else expected
    if published.decode('ascii').strip() != expected:
        raise ValueError('Published kubeadm SHA256 differs from the reviewed pin')
    if hashlib.sha256(binary.read_bytes()).hexdigest() != expected:
        raise ValueError('kubeadm binary SHA256 mismatch')


def phase_commands(binary, config, preview):
    return [['sudo', '-n', 'env', 'KUBEADM_INIT_DRYRUN_DIR=' + str(preview),
             str(binary), 'init', 'phase', *phase, '--config', str(config), '--dry-run']
            for phase in [('control-plane', 'all'), ('etcd', 'local')]]


def artifact_owner_command(preview, uid, gid):
    # kubeadm writes mode 0600 as root. Never recurse, change host paths, or
    # expose generated credentials: these are exactly four static Pod manifests.
    return ['sudo', '-n', 'chown', str(uid) + ':' + str(gid),
            *[str(preview / name) for name in MANIFESTS]]


def execute(command, log, *, env=None, timeout=180, allowed=(0,)):
    result = subprocess.run(command, env=env, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=timeout)
    log.write_text(result.stdout, encoding='utf-8')
    if result.returncode not in allowed:
        raise RuntimeError('Command failed: ' + shlex.join(command) + '\n' + result.stdout[-8000:])
    return result.stdout.strip()


def version_commands(source):
    body=source.read_text().split('validate_host() {\n',1)[1].split('\nwrite_result()',1)[0]
    lines=re.findall(r'^    (kubectl version [^\n]+|kubeconform -v;[^\n]+)$',body,re.M)
    commands=[shlex.split(part.strip()) for line in lines for part in line.split(';')]
    expected=['kubectl','kubeadm','helm','cilium','kubeconform','tkn','argocd','yq','jq']
    if [cmd[0] for cmd in commands]!=expected:raise ValueError('Missing/unexpected validate_host client version commands')
    return commands


def verify_cli_install(work, state, binaries, lock):
    for name,row in lock['artifacts'].items():
        archive=work/row['asset'];binary=binaries/name
        if hashlib.sha256(archive.read_bytes()).hexdigest()!=row['sha256']:
            raise ValueError('Pinned CLI release checksum mismatch: '+name)
        stamp=(state/('cli-'+name)).read_text().splitlines()
        if stamp!=[row['version']+'/amd64',hashlib.sha256(binary.read_bytes()).hexdigest()]:
            raise ValueError('Shared install_cli stamp/version/binary mismatch: '+name)


def validate_clis(source,assets,report):
    """Execute the shared installer, redirecting only its writes/hash target."""
    root=assets/'host-cli-install';root.mkdir(exist_ok=True)
    work=root/'work';state=root/'state';binaries=root/'bin'
    for path in (work,state,binaries):path.mkdir(exist_ok=True)
    env=dict(os.environ,PATH=str(assets/'bin')+os.pathsep+os.environ['PATH'],
             HOME=str(root),KUBECONFIG=str(root/'nonexistent-kubeconfig'))
    script=source/'00-setup-ubuntu-host.sh'
    code=('set -Eeuo pipefail; source '+shlex.quote(str(script))+'; '
          'VCLOUD_CONFIG_FILE=/nonexistent-ci-config; load_config; ARCH=amd64; TKN_ARCH=x86_64; '
          'STATE_DIR='+shlex.quote(str(state))+'; WORK_DIR='+shlex.quote(str(work))+'; '
          'CLI_BIN='+shlex.quote(str(binaries))+';\n'+r'''
# Original URLs, release digest verification, archive members and stamps remain.
# Refuse every install destination except the expected /usr/local/bin basename;
# the actual write and its final stamp hash go to this disposable directory.
install() {
    [[ $# == 4 && $1 == -m && $2 == 0755 && $4 == /usr/local/bin/* ]] || return 93
    command install -m 0755 "$3" "$CLI_BIN/${4##*/}"
}
sha256sum() {
    if [[ $# == 1 && $1 == /usr/local/bin/* ]]; then
        command sha256sum "$CLI_BIN/${1##*/}"
    else command sha256sum "$@"; fi
}
install_tooling
''')
    execute(['bash','-c',code],report/'cli-install.log',env=env,timeout=900)
    lock=json.loads((source/'tools/ci/host-cli.lock.json').read_text())
    verify_cli_install(work,state,binaries,lock)
    # kubectl uses the same Kubernetes version as the node's APT package; the
    # official binary is staged with its published checksum, without APT/CRI.
    kubectl=json.loads((source/'tools/ci/toolchain.lock.json').read_text())['artifacts']['kubectl']
    if kubectl['url']!=URL.removesuffix('kubeadm')+'kubectl':raise ValueError('Unexpected kubectl release')
    with urllib.request.urlopen(kubectl['url']+'.sha256',timeout=60) as response:
        verify_binary(assets/'bin/kubectl',response.read(1024),kubectl['sha256'])
    env['PATH']=str(binaries)+os.pathsep+env['PATH']
    commands=version_commands(script);results=[]
    for index,cmd in enumerate(commands):
        # Help comes from the installed pinned binary, before its exact call.
        help_command=[cmd[0],*([cmd[1]] if len(cmd)>1 and not cmd[1].startswith('-') else []),'--help']
        help_output=execute(help_command,report/('cli-help-'+str(index)+'.log'),env=env,
                            allowed=(0,1) if cmd[0]=='kubeconform' else (0,))
        # Pinned kubeconform deliberately returns 1 after printing its help.
        # This allowance is confined to help; its exact -v call must return 0.
        if cmd[0]=='kubeconform' and not (help_output.startswith('Usage: kubeconform') and '-v' in help_output):
            raise ValueError('Unexpected kubeconform help response')
        output=execute(cmd,report/('cli-version-'+str(index)+'.log'),env=env)
        results.append(dict(command=cmd,status='passed',output=output))
    (report/'cli-summary.json').write_text(json.dumps(dict(status='passed',commands=results),indent=2)+'\n')
    print('Pinned CLI installation and exact validate_host client commands passed',flush=True)
    return results


def run(source, assets, report):
    source, assets, report = (p.resolve() for p in (source, assets, report))
    report.mkdir(parents=True, exist_ok=True)
    summary = dict(status='failed', scope='real kubeadm manifest dry-run; no live acceptance',
                   version=VERSION, sha256=SHA256, profiles=[])
    try:
        binary = assets / 'bin/kubeadm'
        with urllib.request.urlopen(URL + '.sha256', timeout=60) as response:
            verify_binary(binary, response.read(1024))
        if execute([str(binary), 'version', '-o', 'short'], report / 'version.log') != VERSION:
            raise ValueError('Unexpected kubeadm version')
        env = dict(os.environ, PATH=str(assets / 'bin') + os.pathsep + os.environ['PATH'])
        summary['cliCommands']=validate_clis(source,assets,report)
        script = shlex.quote(str(source / '00-setup-ubuntu-host.sh'))
        for name in ('dev-cairo-1', 'production'):
            directory = report / name
            directory.mkdir(exist_ok=True)
            preview = directory / 'preview'
            preview.mkdir(exist_ok=True)
            config = directory / 'kubeadm.yaml'
            profile = ('source ' + shlex.quote(str(source / 'deploy/environments/dev/cairo-1/host.env'))
                       if name == 'dev-cairo-1' else 'NODE_IP=192.168.50.10; NODE_NAME=ci-production')
            prefix = ('set -Eeuo pipefail; source ' + script + '; '
                      'VCLOUD_CONFIG_FILE=/nonexistent-ci-config; load_config; ' + profile + '; '
                      'STATE_DIR=' + shlex.quote(str(directory)) + '; ')
            render = (prefix + 'mkdir -p "$STATE_DIR/kubeadm-patches"; '
                      'render_kubeadm > "$STATE_DIR/kubeadm.yaml"; '
                      'render_etcd_patch "$STATE_DIR/kubeadm.yaml" > "$STATE_DIR/kubeadm-patches/etcd+strategic.yaml"')
            execute(['bash', '-c', render], directory / 'render.log', env=env)
            for index, command in enumerate(phase_commands(binary, config, preview)):
                execute(command, directory / ('phase-' + str(index) + '.log'))
            if {p.name for p in preview.iterdir()} != set(MANIFESTS):
                raise ValueError('Dry-run did not produce exactly four static Pod manifests')
            if any(p.is_symlink() or not p.is_file() for p in preview.iterdir()):
                raise ValueError('Dry-run manifests must be regular files, not links')
            execute(artifact_owner_command(preview, os.getuid(), os.getgid()), directory / 'artifact-owner.log')
            execute(['bash', '-c', prefix + 'validate_etcd_cert_mount ' + shlex.quote(str(preview))],
                    directory / 'assert-etcd.log', env=env)
            summary['profiles'].append(dict(name=name, status='passed', phases=2, etcdMount='read-only; unique; config-derived'))
            print(name + ': real kubeadm control-plane/etcd dry-run and etcd mount assertion passed', flush=True)
        summary['status'] = 'passed'
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        summary['error'] = str(error)
        print(str(error), flush=True)
    finally:
        (report / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    return int(summary['status'] != 'passed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.source, args.assets, args.report))
