# Air-gapped image pull failures

Use this runbook for the Ubuntu/WSL node's **external containerd** CRI socket,
`unix:///run/containerd/containerd.sock`. It implements
[architecture ADR-0028](../adr/0028-air-gapped-registry.md).
Read-only checks need permission to access the CRI socket and local kubeconfig;
configuration writes need node administrator access. No Pod privilege is added.

## Identify the failing layer

```bash
kubectl -n argocd describe pod -l app.kubernetes.io/name=argocd-repo-server
kubectl -n argocd get events --sort-by=.metadata.creationTimestamp
kubectl -n argocd get sa argocd-repo-server -o yaml
kubectl -n argocd get pods -l app.kubernetes.io/name=argocd-repo-server \
  -o 'jsonpath={range .items[*]}{.metadata.name}{"\n"}{range .spec.initContainers[*]}init {.name} {.image} {.imagePullPolicy}{"\n"}{end}{range .spec.containers[*]}main {.name} {.image} {.imagePullPolicy}{"\n"}{end}{end}'
sudo journalctl -u containerd --since '20 minutes ago' --no-pager
```

Review logs for secrets before sharing. Inspect the latest ReplicaSet/pod after
an image change; the previous pod's image and errors remain unchanged.

| Error | Investigation |
| --- | --- |
| `lookup ... no such host` | Node resolver/private DNS; failure precedes TCP/TLS/auth |
| Timeout/refused on 443 | Actual endpoint, route, listener and node firewall evidence |
| `x509` error | Approved CA, certificate validity and registry hostname/SNI |
| Authenticated pull 401/403 | Scoped credentials and repository authorization |
| Manifest 404 | API root, canonical repository prefix, tag/digest and staged content |
| `ErrImageNeverPull` | Missing cache; do not use `Never` as the standard policy |

An anonymous `/v2/` HTTP 401 can be a normal registry authentication challenge.
It establishes a TLS/HTTP response, not successful authenticated image access.

## Why init succeeds while the main image fails

`Always` asks the CRI to pull on each start. With a tag this normally requires
manifest resolution even if image layers are cached. `IfNotPresent` uses a
locally available image without that pull request. Pinning a digest avoids tag
mutation; specifying the policy preserves offline behavior. Changing only the
image does not change an existing policy. A successful init ImageID proves prior
availability, not current DNS health or that the image remains in the cache.

The repository normalizes every full Argo container/init policy, applies explicit
patches to the three primary controllers, and shares the Argo digest with WSL
Core. Conftest and schema/security checks validate actual Kustomize output.

## Containerd routing and DNS setup

For `quay.io/argoproj/argocd`, use this API root in
`/etc/containerd/certs.d/quay.io/hosts.toml`:

```toml
server = "https://registry.vcloud.example.com/v2/quay.io"
capabilities = ["pull", "resolve"]
override_path = true

[host."https://registry.vcloud.example.com/v2/quay.io"]
capabilities = ["pull", "resolve"]
override_path = true
```

This produces `/v2/quay.io/argoproj/argocd/manifests/<tag-or-digest>`.
`override_path=true` alone on a bare hostname does not insert `quay.io` or `/v2`.
Leaving `server=https://quay.io` permits fallback to the upstream. These are plain
TOML URL strings. Private CA paths must appear
on both root and host settings; the generator does that automatically.

For containerd 2.x/config v3:

```toml
[plugins."io.containerd.cri.v1.images".registry]
config_path = "/etc/containerd/certs.d"
```

Config v2/containerd 1.x uses `io.containerd.grpc.v1.cri` instead. Do not replace
NVIDIA, CNI or cgroup configuration to change registry routing. Changes to
`hosts.toml` reload without a daemon restart; changing `config.toml` requires one.
K3s embedded-runtime `registries.yaml` is not read by this external runtime.

From `/mnt/e/vCloud`, preview the files and node network state:

```bash
bash scripts/bootstrap-node.sh --plan
getent ahosts registry.vcloud.example.com
curl --connect-timeout 5 --max-time 10 https://registry.vcloud.example.com/v2/
```

If a real registry has a private CA and a known site address:

```bash
# Public CA already installed through the approved certificate process.
# Set this address to the actual registry, not the WSL node unless it hosts it.
: "${VCLOUD_REGISTRY_ADDRESS:?Set the actual registry IP}"
sudo bash scripts/bootstrap-node.sh --apply \
  --registry-address "$VCLOUD_REGISTRY_ADDRESS" \
  --ca-file /etc/ssl/certs/vcloud-registry-ca.pem
```

The address is checked with TLS/SNI for `registry.vcloud.example.com` **before**
the hosts entry is changed. No site address is embedded in source. Repeated
configuration is idempotent and preserves the first `.vcloud-registry-original`
backup. WSL bootstrap can receive the same explicit `VCLOUD_REGISTRY_ADDRESS`
and `VCLOUD_REGISTRY_CA_FILE` inputs. Without an address, it reports DNS state and
does not fabricate a fallback. Deployment acceptance remains a separate gate.
WSL can regenerate `/etc/hosts` at startup. Use owned private DNS for a durable
record, or rerun the idempotent bootstrap with the same verified site inputs after
restart; the script does not change WSL's host/DNS generation settings.

If the registry has no deployed service, adding DNS will not supply one. Keep the
cache-only lab profile and import every vetted image. Do not globally replace
WSL's DNS tunneling resolver, use public DNS for a private name, weaken Cilium
Host Firewall, or introduce upstream runtime fallback to hide this fault.

## Deployment gates and profile selection

```bash
# Default gate: mirror DNS/TLS AND every full-profile image in the CRI cache.
sudo bash scripts/validate-node.sh

# Explicit offline profile: mirror can be unavailable; exact cache is mandatory.
sudo bash scripts/validate-node.sh --cache-only

# WSL Core's separate image set, derived from its audited current render:
python3 tools/wsl_platform.py render --build .build/wsl-platform-preflight
sudo bash scripts/validate-node.sh --cache-only \
  --manifest .build/wsl-platform-preflight/infrastructure.yaml
```

`crictl images -o json` is queried with the explicit external socket. The gate
checks canonical tags/digests, including init images. Upstream aliases or matching
layers alone are insufficient. No gate pulls, modifies, deletes or garbage
collects images. Stage approved offline archives, verify their checksums, import
them into containerd's `k8s.io` namespace, and create the exact canonical aliases
before rollout. Cold-cache/no-internet acceptance is still a backlog item.

The [full overlay](../../deploy/kustomize/overlays/vcloud-local/kustomization.yaml)
targets an explicitly chosen `argocd` installation. The existing WSL default is
Argo Core in `platform-services`. Confirm a single owner for each Application and
cluster-scoped Argo resources before any deployment. Neither preflight script
installs Argo or migrates ownership. Do not apply full Argo beside the existing
Core installation as a repair. The full reference profile's existing upstream
RBAC and network policies require the platform's namespace/egress review before
adoption; CI does not claim that live integration gate has passed.

Render and validate locally with staged tools, without downloading manifests:

```bash
make airgap-validate airgap-test
```

If this full installation is already the selected owner, create its namespace
before server-side dry-run, then review the rendered diff through your normal
deployment process. Do not use a moving `/stable/` install URL. Persist changes in
the owning GitOps source; repeated upstream installs can revert pull settings.

`vcloud-registry-cred` is a namespace-local `kubernetes.io/dockerconfigjson`
Secret managed outside Git. Provision it in the selected installation namespace
before authenticated cold pulls. A CSI file mount by itself is unavailable to
the kubelet before image pull; a managed/synced Kubernetes pull Secret is needed.
Never put its data in YAML, shell arguments or troubleshooting output.

## Rollback and evidence

Review only the exact configuration files changed. Restore their saved originals
through a controlled node change and restart containerd only if daemon config
changed. Keep unrelated hosts entries, CA trust, runtime settings and firewall
rules. Restoring upstream policies can reintroduce the failure.

Record the rendered image digest, CRI endpoint/cache result, DNS/TLS result,
latest pod events, and controller readiness separately. Shell/schema/policy
success does not establish registry availability, authenticated pulls or rollout.
