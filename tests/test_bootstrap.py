#!/usr/bin/env python3
"""Offline checks; apply ordering tests replace all host operations with mocks."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import gzip
import hashlib
import importlib.util
import copy
try:
    import tomllib
except ImportError:
    import tomli as tomllib
import unittest

import yaml
import jsonschema

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--bash", default="bash")
parser.add_argument("--cloud-schema", type=Path)
parser.add_argument("--render-dir", type=Path)
parser.add_argument('--render-only', action='store_true', help='Generate artifacts without running tests')
parser.add_argument('--yq', type=Path)
parser.add_argument('--kubeconform', type=Path)
OPTIONS, REMAINING = parser.parse_known_args()


def shell_path(path):
    value = str(Path(path).resolve()).replace("\\", "/")
    if os.name == "nt":
        value = "/" + value[0].lower() + value[2:]
    return value


def bash(code, check=True):
    # Source only the library. All commands below are pure render/config helpers or
    # temporary file convergence tests; source does not call main or require root.
    prefix = (
        "set -Eeuo pipefail; export PATH=/usr/bin:/bin:$PATH; "
        f"source {shlex.quote(shell_path(ROOT / '00-setup-ubuntu-host.sh'))}; "
        f"python3() {{ {shlex.quote(shell_path(sys.executable))} \"$@\"; }}; "
        "VCLOUD_CONFIG_FILE=/vcloud-offline-no-config; load_config; "
    )
    result = subprocess.run([OPTIONS.bash, "-c", prefix + code], cwd=ROOT, text=True, capture_output=True)
    if check and result.returncode:
        raise AssertionError(f"Bash exited {result.returncode}: {result.stdout}\n{result.stderr}")
    return result


def contract_module():
    module_spec = importlib.util.spec_from_file_location('contract', ROOT / 'tools/check_manifest_contract.py')
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def control_plane_fixtures():
    """Synthetic static Pods reflecting approved mounts; NOT actual kubeadm output."""
    # Independent, source-derived expectations, deliberately not generated from the policy.
    layouts = {
        'kube-apiserver': [('/etc/kubernetes/pki', True, 'DirectoryOrCreate'), ('/etc/ssl/certs', True, 'DirectoryOrCreate')],
        'kube-controller-manager': [('/etc/kubernetes/pki', True, 'DirectoryOrCreate'), ('/etc/ssl/certs', True, 'DirectoryOrCreate'), ('/etc/kubernetes/controller-manager.conf', True, 'FileOrCreate')],
        'kube-scheduler': [('/etc/kubernetes/scheduler.conf', True, 'FileOrCreate')],
        'etcd': [('/etc/kubernetes/pki/etcd', True, 'DirectoryOrCreate'), ('/var/lib/etcd', False, 'DirectoryOrCreate')],
    }
    result = []
    for name, layout in layouts.items():
        volumes, mounts = [], []
        for index, (path, read_only, path_type) in enumerate(layout):
            volume_name = 'etcd-certs' if path == '/etc/kubernetes/pki/etcd' else f'host-{index}'
            volumes.append(dict(name=volume_name, hostPath=dict(path=path, type=path_type)))
            mounts.append(dict(name=volume_name, mountPath=path, readOnly=read_only))
        image = 'registry.vcloud.example.com/registry.k8s.io/' + name + ':' + ('3.6.8-0' if name == 'etcd' else 'v1.36.5')
        result.append(dict(apiVersion='v1', kind='Pod', metadata=dict(name=name, namespace='kube-system'),
            spec=dict(hostNetwork=True, securityContext=dict(seccompProfile=dict(type='RuntimeDefault')),
                      containers=[dict(name=name, image=image, command=[name], volumeMounts=mounts)], volumes=volumes)))
    return result


class BootstrapTests(unittest.TestCase):
    def test_bash_syntax(self):
        result = subprocess.run([OPTIONS.bash, "-n", str(ROOT / "00-setup-ubuntu-host.sh")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_default_profile(self):
        output = bash("validate_config; plan").stdout
        self.assertIn("128 x 2 MiB + 1 x 1 GiB", output)
        self.assertIn("Upstream Kubernetes v1.36.5 via kubeadm", output)
        self.assertIn("bootstrap=true", output)
        self.assertIn("GPU=auto", output)
        self.assertIn("gpu-smoke=false", output)

    def test_source_has_no_host_mutation(self):
        self.assertEqual(bash("printf 'source-safe'").stdout, "source-safe")

    def test_bad_modes(self):
        result = bash("main --destroy", check=False)
        self.assertEqual(result.returncode, 2)

    def test_invalid_hugepage_counts_rejected(self):
        for value in ("-1", "010", "1G", "1000000", "x"):
            with self.subTest(value=value):
                result = bash(f"HUGEPAGES_1G={shlex.quote(value)}; validate_config", check=False)
                self.assertEqual(result.returncode, 2)

    def test_invalid_registry_rejected(self):
        for value in ("http://mirror.test", "https://user:secret@mirror.test", 'https://mirror.test/harbor', 'https://mirror.test\"'):
            with self.subTest(value=value):
                result = bash(f"REGISTRY_MIRROR={shlex.quote(value)}; validate_config", check=False)
                self.assertEqual(result.returncode, 2)

    def test_overlapping_cidrs_rejected(self):
        result = bash("SERVICE_CIDR=10.42.0.0/20; validate_config", check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("overlap", result.stderr)

    def test_node_ip_rejected_if_inside_cluster(self):
        result = bash("NODE_IP=10.42.1.1; validate_config", check=False)
        self.assertEqual(result.returncode, 2)

    def test_incompatible_kubernetes_rejected(self):
        result = bash("KUBERNETES_VERSION=v1.37.1; validate_config", check=False)
        self.assertEqual(result.returncode, 2)

    def test_crictl_minor_must_match(self):
        result = bash("CRICTL_VERSION=v1.35.0; validate_config", check=False)
        self.assertEqual(result.returncode, 2)

    def test_version_boundary(self):
        result = bash("version_at_least 6.8 6.8; version_at_least 6.11.0 6.8; ! version_at_least 6.5.0 6.8; version_at_least 580.1 550; ! version_at_least 535 550")
        self.assertEqual(result.returncode, 0)

    def test_containerd_1_and_2(self):
        for major, plugin, version in [(1,"io.containerd.grpc.v1.cri",2),(2,"io.containerd.cri.v1.runtime",3)]:
            with self.subTest(major=major):
                config = tomllib.loads(bash(f"render_containerd {major}").stdout)
                self.assertEqual(config["version"], version)
                runtime = config["plugins"][plugin]["containerd"]
                self.assertEqual(runtime["default_runtime_name"], "runc")
                self.assertIs(runtime["runtimes"]["runc"]["options"]["SystemdCgroup"], True)
                image_plugin = plugin if major == 1 else "io.containerd.cri.v1.images"
                self.assertEqual(config["plugins"][image_plugin]["registry"]["config_path"], "/etc/containerd/certs.d")
                self.assertNotIn("cri", config.get("disabled_plugins", []))

    def test_containerd_20_uses_compatible_cni_key(self):
        config = tomllib.loads(bash("render_containerd 2.0.5").stdout)
        self.assertEqual(config["plugins"]["io.containerd.cri.v1.runtime"]["cni"]["bin_dir"], "/opt/cni/bin")
        self.assertNotIn("bin_dirs", config["plugins"]["io.containerd.cri.v1.runtime"]["cni"])
        self.assertNotIn("use_local_image_pull", config["plugins"]["io.containerd.cri.v1.images"])

    def test_registry_fallback_and_tls(self):
        config = tomllib.loads(bash("render_mirror").stdout)
        self.assertEqual(config['server'], 'https://registry.vcloud.example.com')
        host = config["host"]["https://registry.vcloud.example.com"]
        self.assertEqual(host["capabilities"], ["pull", "resolve"])
        self.assertNotIn("skip_verify", host)

    def test_registry_mirror_only_and_ca(self):
        config = tomllib.loads(bash("MIRROR_REQUIRED=true; REGISTRY_CA_FILE=/etc/ssl/pcloud.pem; render_mirror").stdout)
        self.assertEqual(config["server"], "https://registry.vcloud.example.com")
        self.assertEqual(config["host"][config["server"]]["ca"], "/etc/ssl/pcloud.pem")

    def test_grub_preserves_args_and_removes_duplicate_pools(self):
        result = bash("GRUB_CMDLINE_LINUX='console=ttyS0 hugepagesz=1G hugepages=4 cgroup_no_v1=none'; GRUB_CMDLINE_LINUX_DEFAULT='quiet hugepages=10'; source <(render_grub); first=$GRUB_CMDLINE_LINUX; source <(render_grub); [[ $first == \"$GRUB_CMDLINE_LINUX\" ]]; printf '%s\\n%s' \"$GRUB_CMDLINE_LINUX\" \"$GRUB_CMDLINE_LINUX_DEFAULT\"")
        self.assertIn("console=ttyS0", result.stdout)
        self.assertIn("hugepagesz=1G hugepages=1", result.stdout)
        self.assertIn("hugepagesz=2M hugepages=128", result.stdout)
        self.assertEqual(result.stdout.count("hugepagesz=1G"), 1)
        self.assertNotIn("hugepages=10", result.stdout)
        self.assertIn("quiet", result.stdout)

    def test_write_file_is_idempotent_and_keeps_original(self):
        with tempfile.TemporaryDirectory(prefix="vcloud-test-", dir=ROOT / ".tools") as temp:
            path = shell_path(temp)
            result = bash(f"WORK_DIR={shlex.quote(path)}; destination=\"$WORK_DIR/config\"; printf 'original' > \"$destination\"; printf 'desired' | cat > \"$WORK_DIR/input\"; write_file \"$destination\" < \"$WORK_DIR/input\"; [[ $FILE_CHANGED == true ]]; first=$(stat -c '%Y' \"$destination\"); write_file \"$destination\" < \"$WORK_DIR/input\"; [[ $FILE_CHANGED == false ]]; [[ $first == \"$(stat -c '%Y' \"$destination\")\" ]]; [[ $(cat \"$destination.vcloud-original\") == original ]]; printf 'changed' > \"$WORK_DIR/input\"; write_file \"$destination\" < \"$WORK_DIR/input\"; [[ $(cat \"$destination.vcloud-original\") == original ]]")
            self.assertEqual(result.returncode, 0)

    def test_kubeadm_config(self):
        config = list(yaml.safe_load_all(bash("NODE_IP=192.168.50.10; NODE_NAME=vcloud01; render_kubeadm").stdout))
        init, cluster, kubelet = config
        self.assertEqual(init["apiVersion"], "kubeadm.k8s.io/v1beta4")
        self.assertEqual(init["nodeRegistration"]["criSocket"], "unix:///run/containerd/containerd.sock")
        self.assertEqual(init["skipPhases"], ["addon/kube-proxy"])
        self.assertEqual(init["nodeRegistration"]["taints"], [])
        self.assertEqual(cluster["kubernetesVersion"], "v1.36.5")
        self.assertEqual(cluster['clusterName'], 'vCloud-prod-01')
        self.assertEqual(cluster['imageRepository'], 'registry.vcloud.example.com/registry.k8s.io')
        self.assertEqual(kubelet["cgroupDriver"], "systemd")

    def test_cilium_config(self):
        config = yaml.safe_load(bash("NODE_IP=192.168.50.10; render_cilium_values").stdout)
        self.assertIs(config["kubeProxyReplacement"], True)
        self.assertIs(config["bpf"]["autoMount"]["enabled"], False)
        self.assertEqual(config["ipam"]["mode"], "kubernetes")
        self.assertEqual(config["cgroup"]["hostRoot"], "/sys/fs/cgroup")
        self.assertEqual(config["cni"]["binPath"], "/opt/cni/bin")
        self.assertEqual(config["operator"]["replicas"], 1)
        self.assertEqual(config['routingMode'], 'native')
        self.assertNotIn('tunnelProtocol', config)
        self.assertEqual(config['ipv4NativeRoutingCIDR'], '10.42.0.0/16')
        self.assertFalse(config['autoDirectNodeRoutes'])
        self.assertEqual(config['cluster']['name'], 'vcloud-prod-01')

    def test_smoke_policy_and_positive_control(self):
        objects = list(yaml.safe_load_all(bash("render_smoke").stdout))
        policies = {x["metadata"]["name"]: x for x in objects if x["kind"] == "NetworkPolicy"}
        self.assertEqual(policies["deny-all"]["spec"]["policyTypes"], ["Ingress", "Egress"])
        allowed_selector = policies["server-ingress"]["spec"]["ingress"][0]["from"][0]["podSelector"]
        self.assertEqual(allowed_selector["matchLabels"]["access"], "allowed")
        allowed = yaml.safe_load(bash("render_probe_job allowed").stdout)
        denied = yaml.safe_load(bash("render_probe_job denied").stdout)
        self.assertIn("POLICY_NOT_ENFORCED", denied["spec"]["template"]["spec"]["containers"][0]["command"][2])
        self.assertIn("grep -q vcloud-ok", allowed["spec"]["template"]["spec"]["containers"][0]["command"][2])

    def test_hugepage_mmap_probe(self):
        job = yaml.safe_load(bash("render_hugepage_job").stdout)
        container = job["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(container["resources"]["limits"]["hugepages-2Mi"], "2Mi")
        self.assertEqual(container["resources"]["limits"]["hugepages-1Gi"], "1Gi")
        self.assertIn("mmap.mmap", container["command"][2])
        self.assertEqual({v["emptyDir"]["medium"] for v in job["spec"]["template"]["spec"]["volumes"]}, {"HugePages-2Mi", "HugePages-1Gi"})
        for size in ("2Mi", "1Gi"):
            self.assertEqual(container["resources"]["limits"]["hugepages-"+size], container["resources"]["requests"]["hugepages-"+size])

    def test_cuda_smoke_requires_explicit_opt_in_without_affecting_cpu_smoke(self):
        self.assertEqual(bash('render_gpu_job').stdout, '')
        self.assertNotIn('/nvidia/cuda:', bash('render_smoke').stdout)
        self.assertIn('/nvidia/cuda:', bash('GPU_SMOKE_TEST=true; render_gpu_job').stdout)
        self.assertEqual(bash('GPU_SMOKE_TEST=auto; validate_config', check=False).returncode, 2)
        for enabled in (False, True):
            with self.subTest(enabled=enabled), tempfile.TemporaryDirectory(dir=ROOT / '.tools') as temp:
                code = f'''
STATE_DIR={shlex.quote(shell_path(temp))}
GPU_ENABLED=true; GPU_SMOKE_TEST={str(enabled).lower()}
HUGEPAGES_2M=0; HUGEPAGES_1G=0
kubectl() {{
    [[ $1 != get ]] || return 1
    printf '%s\\n' "$*" >> "$STATE_DIR/commands"
}}
validate_manifests() {{ :; }}
run_smoke_tests
'''
                bash(code)
                state = Path(temp)
                commands = (state / 'commands').read_text()
                self.assertIn('job/allowed', commands)
                self.assertIn('job/denied', commands)
                self.assertEqual('job/gpu' in commands, enabled)
                self.assertEqual((state / 'smoke-gpu.yaml').exists(), enabled)
                rendered = ''.join(p.read_text() for p in state.glob('*.yaml'))
                self.assertEqual('/nvidia/cuda:' in rendered, enabled)

    def mocked_apply(self, reboot):
        with tempfile.TemporaryDirectory(prefix="vcloud-order-", dir=ROOT / ".tools") as temp:
            path = shlex.quote(shell_path(temp))
            code = f"""
eval "$(declare -f load_config | sed '1s/load_config/original_load_config/')"
load_config() {{ original_load_config; STATE_DIR={path}; }}
preflight() {{ :; }}
# ONLY the mocked apply-order scenario bypasses the gate; no real host ops run.
check_policy_gate() {{ :; }}
flock() {{ :; }}
apt-get() {{ :; }}
install_missing() {{ :; }}
add-apt-repository() {{ :; }}
prepare_kernel() {{ printf 'kernel\\n' >> "$STATE_DIR/order"; NEEDS_REBOOT={str(reboot).lower()}; }}
prepare_memory_network() {{ printf 'memory\\n' >> "$STATE_DIR/order"; }}
install_gpu() {{ printf 'gpu\\n' >> "$STATE_DIR/order"; }}
install_tooling() {{ printf 'tools\\n' >> "$STATE_DIR/order"; }}
install_kubernetes_packages() {{ printf 'packages\\n' >> "$STATE_DIR/order"; }}
install_hpc_kvm() {{ printf 'hpc\\n' >> "$STATE_DIR/order"; }}
configure_containerd() {{ printf 'runtime\\n' >> "$STATE_DIR/order"; }}
bootstrap_kubernetes() {{ printf 'kubernetes\\n' >> "$STATE_DIR/order"; }}
validate_host() {{ printf 'validate\\n' >> "$STATE_DIR/order"; }}
run_smoke_tests() {{ printf 'smoke\\n' >> "$STATE_DIR/order"; }}
dpkg-query() {{ printf 'mock-package\\t1.0\\n'; }}
write_result() {{ printf '%s' "$1" > "$STATE_DIR/result-status"; }}
cleanup() {{ :; }}
main --apply
"""
            result = bash(code, check=False)
            state = Path(temp)
            return result, (state / "order").read_text().splitlines(), (state / "result-status").read_text(), (state / "complete").exists(), (state / "containerd-owned").exists()

    def test_reboot_defers_all_runtime_and_cluster_actions(self):
        result, order, status, complete, owned = self.mocked_apply(True)
        self.assertEqual(result.returncode, 20, result.stderr)
        self.assertNotIn("runtime", order)
        self.assertNotIn("kubernetes", order)
        self.assertNotIn("validate", order)
        self.assertEqual(status, "reboot-required")
        self.assertFalse(complete)
        self.assertTrue(owned, "APT runtime ownership must survive the first reboot")

    def test_ready_is_written_only_after_smoke(self):
        result, order, status, complete, owned = self.mocked_apply(False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(order[-4:], ["runtime", "kubernetes", "validate", "smoke"])
        self.assertEqual(status, "ready")
        self.assertTrue(complete)
        self.assertTrue(owned)

    def test_cloud_init_embeds_script_exactly(self):
        data = yaml.safe_load((ROOT / "user-data.yaml").read_text(encoding="utf-8"))
        files = {x["path"]: x for x in data["write_files"]}
        self.assertEqual(files["/usr/local/sbin/00-setup-ubuntu-host.sh"]["content"], (ROOT / "00-setup-ubuntu-host.sh").read_text(encoding="utf-8"))
        self.assertEqual(files["/etc/vcloud-host.env"]["permissions"], "0600")
        self.assertEqual(data["runcmd"][1][1], "enable")
        self.assertNotIn("--now", data["runcmd"][1])
        self.assertEqual(data["power_state"]["condition"], ["test", "-f", "/var/lib/vcloud-host/reboot-required"])

    def test_gzip_contains_full_cloud_init(self):
        self.assertEqual(gzip.decompress((ROOT / "user-data.yaml.gz").read_bytes()), (ROOT / "user-data.yaml").read_bytes())

    def test_remote_variant_pins_current_hash_and_fits_provider_limit(self):
        payload = (ROOT / "user-data-remote.yaml").read_bytes()
        self.assertLess(len(payload), 16 * 1024)
        data = yaml.safe_load(payload)
        files = {x["path"]: x for x in data["write_files"]}
        downloader = files["/usr/local/sbin/vcloud-fetch-host.sh"]["content"]
        self.assertIn(hashlib.sha256((ROOT / "00-setup-ubuntu-host.sh").read_bytes()).hexdigest(), downloader)
        self.assertIn("sha256sum -c", downloader)
        self.assertIn("vcloud-fetch-host.sh &&", data["runcmd"][2][2])
        result = subprocess.run([OPTIONS.bash, "-n"], input=downloader, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_gpu_runtime_and_probe_contract(self):
        runtime = yaml.safe_load(bash("render_gpu_runtime_class").stdout)
        self.assertEqual(runtime["handler"], "nvidia")
        job = yaml.safe_load(bash("GPU_SMOKE_TEST=true; render_gpu_job").stdout)
        pod_spec = job["spec"]["template"]["spec"]
        self.assertEqual(pod_spec["runtimeClassName"], runtime["metadata"]["name"])
        self.assertEqual(pod_spec["containers"][0]["resources"]["limits"]["nvidia.com/gpu"], 1)

    def test_ssot_generation_and_cloud_env_drift(self):
        result = subprocess.run([sys.executable, str(ROOT / 'tools/render_ssot.py'), '--check'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = yaml.safe_load((ROOT / 'user-data.yaml').read_text())
        env = next(x['content'] for x in data['write_files'] if x['path'] == '/etc/vcloud-host.env')
        self.assertEqual(env, (ROOT / 'host.env.example').read_text())

    def test_foundation_has_no_implicit_allow(self):
        objects = list(yaml.safe_load_all(bash('render_foundation').stdout))
        self.assertEqual(objects, list(yaml.safe_load_all((ROOT / 'manifests/foundation.yaml').read_text())))
        namespaces = {o['metadata']['name'] for o in objects if o['kind'] == 'Namespace'}
        self.assertEqual(namespaces, {'platform-services', 'workload-apps', 'hpc-compute'})
        for obj in objects:
            if obj['kind'] == 'NetworkPolicy':
                self.assertEqual(obj['spec'], dict(podSelector={}, policyTypes=['Ingress', 'Egress'], ingress=[], egress=[]))
            else:
                self.assertEqual(obj['metadata']['labels']['pod-security.kubernetes.io/enforce'], 'restricted')

    def test_policy_gate_blocks_before_preflight(self):
        self.assertEqual(bash('check_policy_gate').returncode, 0)
        result = bash("CILIUM_VERSION=1.20.3; preflight() { printf PREFLIGHT_RAN; }; main --apply", check=False)
        self.assertEqual(result.returncode, 42)
        self.assertNotIn('PREFLIGHT_RAN', result.stdout)
        self.assertEqual(bash('BOOTSTRAP_K8S=false; check_policy_gate').returncode, 0)

    def test_registry_identity_and_unpinned_images_rejected(self):
        for code in ('CLUSTER_NAME=other', 'MIRROR_REQUIRED=false', 'BASE_DOMAIN=other.test',
                     'REGISTRY_PROBE_IMAGE=registry.vcloud.example.com/busybox:latest',
                     'HUGEPAGE_SMOKE_IMAGE=registry.vcloud.example.com/python:3.12-slim'):
            self.assertEqual(bash(code + '; validate_config', check=False).returncode, 2)

    def test_smoke_workloads_are_nonroot_and_have_no_hostpaths(self):
        codes = ['render_smoke', 'render_probe_job allowed', 'render_probe_job denied', 'render_hugepage_job', 'GPU_SMOKE_TEST=true; render_gpu_job']
        for code in codes:
            for obj in yaml.safe_load_all(bash(code).stdout):
                if obj['kind'] not in ('Pod', 'Job'):
                    continue
                spec = obj['spec'] if obj['kind'] == 'Pod' else obj['spec']['template']['spec']
                self.assertFalse(spec['automountServiceAccountToken'])
                self.assertTrue(spec['securityContext']['runAsNonRoot'])
                self.assertGreater(spec['securityContext']['runAsUser'], 0)
                for c in spec['containers']:
                    self.assertFalse(c['securityContext']['allowPrivilegeEscalation'])
                    self.assertTrue(c['securityContext']['readOnlyRootFilesystem'])
                    self.assertEqual(c['securityContext']['capabilities']['drop'], ['ALL'])
                self.assertFalse(any('hostPath' in v for v in spec.get('volumes', [])))

    def test_contract_checker_catches_hostpaths_root_and_images(self):
        module = contract_module()
        with tempfile.TemporaryDirectory(dir=ROOT / '.tools') as temp:
            path = Path(temp) / 'pod.yaml'
            pod = yaml.safe_load(bash('GPU_SMOKE_TEST=true; render_gpu_job').stdout)
            path.write_text(yaml.safe_dump(pod))
            self.assertEqual(module.audit([path])['status'], 'passed')
            spec = pod['spec']['template']['spec']
            spec['containers'][0]['image'] = 'registry.vcloud.example.com/probe:latest'
            spec['securityContext']['runAsUser'] = 0
            spec['volumes'] = [dict(name='root', hostPath=dict(path='/'))]
            path.write_text(yaml.safe_dump(pod))
            result = module.audit([path])
            self.assertEqual(result['status'], 'blocked')
            self.assertEqual(len(result['violations']), 3)

    @unittest.skipUnless(OPTIONS.yq and OPTIONS.kubeconform, 'Supply --yq and --kubeconform to exercise real Helm post-renderers')
    def test_post_renderer_filters_mps_and_validates_exact_output(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.tools') as temp:
            directory = shlex.quote(shell_path(temp))
            result = bash(f'''
STATE_DIR={directory}
render_exception_policy > "$STATE_DIR/node-exceptions.json"
render_policy_checker > "$STATE_DIR/check-manifest-contract.py"
render_chart_validator > "$STATE_DIR/validate-chart"
render_nvidia_filter > "$STATE_DIR/filter-nvidia-chart"
chmod +x "$STATE_DIR/validate-chart" "$STATE_DIR/filter-nvidia-chart"
yq() {{ {shlex.quote(shell_path(OPTIONS.yq))} "$@"; }}
kubeconform() {{ {shlex.quote(shell_path(OPTIONS.kubeconform))} -cache {shlex.quote(shell_path(ROOT / '.tools/schema-cache'))} "$@"; }}
export -f yq kubeconform python3
"$STATE_DIR/filter-nvidia-chart" < {shlex.quote(shell_path(ROOT / '.tools/rendered/nvidia-raw.yaml'))}
''')
            objects = [o for o in yaml.safe_load_all(result.stdout) if o]
            self.assertFalse(any(o.get('metadata', {}).get('name', '').endswith('mps-control-daemon') for o in objects))
            self.assertTrue(any(o['kind'] == 'DaemonSet' for o in objects))
            for obj in objects:
                if obj['kind'] == 'DaemonSet':
                    for container in obj['spec']['template']['spec']['containers']:
                        self.assertFalse(container.get('securityContext', {}).get('privileged', False))
            self.assertIn('Invalid: 0', result.stderr)
            invalid = bash(f'''
STATE_DIR={directory}
kubeconform() {{ {shlex.quote(shell_path(OPTIONS.kubeconform))} -cache {shlex.quote(shell_path(ROOT / '.tools/schema-cache'))} "$@"; }}
export -f kubeconform
printf 'apiVersion: v1\\nkind: Pod\\nmetadata: {{name: bad}}\\nspec: {{containers: [{{name: bad, image: 123}}]}}\\n' | "$STATE_DIR/validate-chart"
''', check=False)
            self.assertNotEqual(invalid.returncode, 0)
            self.assertEqual(invalid.stdout, '')

    def test_approved_node_agents_and_revoked_scope(self):
        module = contract_module()
        paths = [ROOT / '.tools/rendered' / n for n in ('cilium-rendered.yaml', 'nvidia-rendered.yaml')]
        result = module.audit(paths)
        self.assertEqual(result['violations'], [])
        self.assertEqual(len(result['acceptedExceptions']), 4)
        import manifest_contract
        policy = module.load_policy()
        policy['status'] = 'unapproved'
        objects = [o for p in paths for o in yaml.safe_load_all(p.read_text(encoding='utf-8-sig')) if o]
        self.assertEqual(manifest_contract.audit_objects(objects, policy)['status'], 'blocked')

    def test_node_mount_and_security_drift_rejected(self):
        module = contract_module()
        import manifest_contract
        policy = module.load_policy()
        objects = [o for o in yaml.safe_load_all((ROOT / '.tools/rendered/cilium-rendered.yaml').read_text(encoding='utf-8-sig')) if o]
        agent = next(o for o in objects if o['kind'] == 'DaemonSet' and o['metadata']['name'] == 'cilium')
        def mutate(case, obj):
            spec = obj['spec']['template']['spec']
            if case == 'path':
                next(v for v in spec['volumes'] if 'hostPath' in v)['hostPath']['path'] = '/etc/shadow'
            elif case == 'mount-mode':
                names = {v['name'] for v in spec['volumes'] if 'hostPath' in v}
                mount = next(m for c in spec['containers'] for m in c['volumeMounts'] if m.get('readOnly') and m['name'] in names)
                mount['readOnly'] = False
            elif case == 'capability':
                spec['containers'][0]['securityContext']['capabilities']['add'].append('SYS_BOOT')
            elif case == 'privileged':
                spec['containers'][0]['securityContext']['privileged'] = True
            elif case == 'namespace':
                obj['metadata']['namespace'] = 'workload-apps'
            elif case == 'image':
                spec['containers'][0]['image'] = 'registry.vcloud.example.com/probe:1.2.3'
            elif case == 'hostPID':
                spec['hostPID'] = True
            elif case == 'command':
                spec['containers'][0]['command'] = ['sh', '-c', 'id']
            else:
                spec['initContainers'].append(dict(name='unexpected', image=spec['containers'][0]['image']))
        for case in ('path', 'mount-mode', 'capability', 'privileged', 'namespace', 'image', 'hostPID', 'command', 'extra-container'):
            with self.subTest(case=case):
                obj = copy.deepcopy(agent)
                mutate(case, obj)
                self.assertEqual(manifest_contract.audit_objects([obj], policy)['status'], 'blocked')

    def test_static_control_plane_contract(self):
        module = contract_module()
        import manifest_contract
        policy, objects = module.load_policy(), control_plane_fixtures()
        self.assertEqual(manifest_contract.audit_objects(objects, policy, 'control-plane')['violations'], [])
        self.assertEqual(manifest_contract.audit_objects(objects, policy)['status'], 'blocked', 'Bare application Pods cannot claim static control-plane exceptions')
        for case in ('path', 'writable-certs', 'image', 'capability', 'missing', 'duplicate'):
            with self.subTest(case=case):
                changed = copy.deepcopy(objects)
                etcd = next(o for o in changed if o['metadata']['name'] == 'etcd')
                if case == 'path':
                    etcd['spec']['volumes'][0]['hostPath']['path'] = '/etc'
                elif case == 'writable-certs':
                    etcd['spec']['containers'][0]['volumeMounts'][0]['readOnly'] = False
                elif case == 'image':
                    etcd['spec']['containers'][0]['image'] = 'registry.vcloud.example.com/registry.k8s.io/etcd:3.6.9-0'
                elif case == 'capability':
                    etcd['spec']['containers'][0]['securityContext'] = dict(capabilities=dict(add=['SYS_ADMIN']))
                elif case == 'missing':
                    changed.pop()
                else:
                    changed.append(copy.deepcopy(etcd))
                self.assertEqual(manifest_contract.audit_objects(changed, policy, 'control-plane')['status'], 'blocked')

    def test_embedded_policy_and_checker_are_exact(self):
        self.assertEqual(bash('render_exception_policy').stdout, (ROOT / 'security/node-exceptions.json').read_text())
        self.assertEqual(bash('render_policy_checker').stdout, (ROOT / 'tools/manifest_contract.py').read_text())
        patch = yaml.safe_load(bash('render_etcd_patch').stdout)
        self.assertEqual(patch['spec']['containers'][0]['volumeMounts'], [dict(name='etcd-certs', readOnly=True)])

    def test_policy_hash_and_reviewed_inventory_integrity(self):
        module = contract_module()
        policy = module.load_policy()
        self.assertEqual(policy['approval']['inventorySHA256'], hashlib.sha256((ROOT / 'docs/node-agent-inventory.json').read_bytes()).hexdigest())
        with tempfile.TemporaryDirectory(dir=ROOT / '.tools') as temp:
            directory = Path(temp)
            (directory / 'security').mkdir()
            (directory / 'vcloud-ssot.yaml').write_bytes((ROOT / 'vcloud-ssot.yaml').read_bytes())
            (directory / 'security/node-exceptions.json').write_bytes((ROOT / 'security/node-exceptions.json').read_bytes() + b'\n')
            module.ROOT = directory
            with self.assertRaisesRegex(ValueError, 'approved SSoT hash'):
                module.load_policy()

    def test_node_approval_does_not_approve_application_storage(self):
        module = contract_module()
        import manifest_contract
        policy = module.load_policy()
        spec = dict(local=dict(path='/etc'), accessModes=['ReadOnlyMany'], volumeMode='Filesystem',
                    storageClassName='local', nodeAffinity=dict(required=dict(nodeSelectorTerms=[])))
        pv = dict(apiVersion='v1', kind='PersistentVolume', metadata=dict(name='unreviewed',
            annotations={'vcloud.io/vetted': 'true'}), spec=spec)
        result = manifest_contract.audit_objects([pv], policy)
        self.assertIn('PersistentVolume/cluster/unreviewed: Local PV outside vetted storage allowlist', result['violations'])

    @unittest.skipUnless(OPTIONS.yq and OPTIONS.kubeconform, 'Supply --yq and --kubeconform for the kubeadm preview contract test')
    def test_kubeadm_preview_checks_all_pods_without_starting_cluster(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.tools') as temp:
            directory = shlex.quote(shell_path(temp))
            fixtures = Path(temp) / 'fixtures'
            fixtures.mkdir()
            for obj in control_plane_fixtures():
                (fixtures / (obj['metadata']['name'] + '.yaml')).write_text(yaml.safe_dump(obj))
            code = f'''
STATE_DIR={directory}; WORK_DIR="$STATE_DIR"
render_exception_policy > "$STATE_DIR/node-exceptions.json"
render_policy_checker > "$STATE_DIR/check-manifest-contract.py"
yq() {{ {shlex.quote(shell_path(OPTIONS.yq))} "$@"; }}
kubeconform() {{ {shlex.quote(shell_path(OPTIONS.kubeconform))} -cache {shlex.quote(shell_path(ROOT / '.tools/schema-cache'))} "$@"; }}
kubeadm() {{
    printf '%s\\n' "$*" >> "$STATE_DIR/commands"
    [[ $* == *'--dry-run'* ]] || return 99
    [[ $KUBEADM_INIT_DRYRUN_DIR == "$WORK_DIR"/kubeadm-preview.* ]] || return 98
    cp "$STATE_DIR/fixtures/"*.yaml "$KUBEADM_INIT_DRYRUN_DIR/"
}}
validate_kubeadm_preview
'''
            result = bash(code)
            commands = (Path(temp) / 'commands').read_text().splitlines()
            self.assertEqual(len(commands), 2)
            self.assertTrue(commands[0].startswith('init phase control-plane all'))
            self.assertTrue(commands[1].startswith('init phase etcd local'))
            self.assertIn('Valid: 4', result.stdout)
            self.assertIn('SSoT contract: passed', result.stderr)
            # A schema-valid unapproved node path must stop the preview.
            target = fixtures / 'kube-scheduler.yaml'
            obj = yaml.safe_load(target.read_text())
            obj['spec']['volumes'][0]['hostPath']['path'] = '/etc/shadow'
            target.write_text(yaml.safe_dump(obj))
            self.assertNotEqual(bash(code, check=False).returncode, 0)
            # An additional static Pod is rejected before kubelet could see it.
            for original in control_plane_fixtures():
                (fixtures / (original['metadata']['name'] + '.yaml')).write_text(yaml.safe_dump(original))
            (fixtures / 'extra.yaml').write_text('apiVersion: v1\nkind: Pod\n')
            extra = bash(code, check=False)
            self.assertNotEqual(extra.returncode, 0)
            self.assertIn('Unapproved static Pod directory entry', extra.stderr)

    @unittest.skipUnless(OPTIONS.cloud_schema, "Supply --cloud-schema for upstream Cloud-Init JSON Schema validation")
    def test_cloud_init_upstream_schema(self):
        schema = json.loads(OPTIONS.cloud_schema.read_text(encoding="utf-8-sig"))
        data = yaml.safe_load((ROOT / "user-data.yaml").read_text(encoding="utf-8"))
        jsonschema.Draft4Validator(schema).validate(data)
        jsonschema.Draft4Validator(schema).validate(yaml.safe_load((ROOT / "user-data-remote.yaml").read_text(encoding="utf-8")))


def render_artifacts(destination):
    destination.mkdir(parents=True, exist_ok=True)
    for filename, code in {
        "kubeadm.yaml": "NODE_IP=192.168.50.10; NODE_NAME=vcloud01; render_kubeadm",
        "cilium-values.yaml": "NODE_IP=192.168.50.10; render_cilium_values",
        "foundation.yaml": "render_foundation",
        "validate-chart": "render_chart_validator",
        "filter-nvidia-chart": "render_nvidia_filter",
        "node-exceptions.json": "render_exception_policy",
        "check-manifest-contract.py": "render_policy_checker",
        "smoke-base.yaml": "render_smoke",
        "smoke-allowed.yaml": "render_probe_job allowed",
        "smoke-denied.yaml": "render_probe_job denied",
        "smoke-hugepages.yaml": "render_hugepage_job",
        "smoke-gpu.yaml": "GPU_SMOKE_TEST=true; render_gpu_job",
        "runtimeclass.yaml": "render_gpu_runtime_class",
        "containerd-1.toml": "render_containerd 1",
        "containerd-2.toml": "render_containerd 2",
        "registry-hosts.toml": "render_mirror",
    }.items():
        (destination / filename).write_text(bash(code).stdout, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    (ROOT / ".tools").mkdir(exist_ok=True)
    if OPTIONS.render_dir:
        render_artifacts(OPTIONS.render_dir)
    if OPTIONS.render_only:
        if not OPTIONS.render_dir:
            parser.error('--render-only requires --render-dir')
        raise SystemExit(0)
    unittest.main(argv=[sys.argv[0], *REMAINING], verbosity=2)
