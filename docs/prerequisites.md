# Node diagnostic CLI prerequisites

Run node health-probe verification on the Kubernetes node with credentials for
the intended cluster. The following CLIs are mandatory for
[`apply-and-verify.sh`](../deploy/network/platform-probes/apply-and-verify.sh):

| CLI | Purpose | Verification |
| --- | --- | --- |
| `kubectl` | Read cluster state and apply the probe policies | `kubectl version --client` |
| `jq` | Parse pod readiness, restart counters and node IPs from Kubernetes JSON | `jq --version` |
| `curl` | Check node-to-pod HTTP/HTTPS probe responses | `curl --version` |
| `ip` (`iproute2`) | Confirm the diagnostic runs on a cluster node | `ip -Version` |

Mirrored WSL nodes also require `nft` from Ubuntu's `nftables` package for the
[Cilium DNS proxy mark repair](troubleshooting/argocd-repo-health-wsl.md).
The WSL bootstrap installs it and an owned-profile reconciliation timer. The
host rule update requires root/CAP_NET_ADMIN; it does not introduce a privileged
container or change the probe verifier's four mandatory CLIs above.

The [Ubuntu host bootstrap](../00-setup-ubuntu-host.sh) installs `jq`, `curl` and
`iproute2`, then installs the pinned `kubectl` package from the configured
Kubernetes repository. The [WSL bootstrap](../lab/wsl/bootstrap.sh) installs the
same diagnostic packages and provides `kubectl` through its pinned K3s binary.

For an existing prepared node missing `jq`, install the Ubuntu diagnostic
packages without rerunning the cluster bootstrap:

```bash
sudo apt-get update
sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends jq curl iproute2 ca-certificates
```

Use the node's configured signed Ubuntu package sources or internal APT mirror.
`kubectl` comes from the selected bootstrap above; its pinned installation is
separate from these Ubuntu utility packages.

Verify the installed node CLIs without adding the repository's staged CI tools
to `PATH`:

```bash
command -v kubectl jq curl ip
jq --version
kubectl version --client
```

Then follow the [platform probe runbook](../deploy/network/platform-probes/README.md)
to select the kubeconfig/context and run verification. Installing `jq` resolves
the missing CLI dependency; probe HTTP 200 and pod readiness remain separate
runtime acceptance checks.
