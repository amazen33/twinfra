# Hyper-V provisioning · dev cairo-1

Owner-only entry point: `New-TwinfraDev.ps1`. Codex/CI never run it.
See [the dev runbook](../../docs/dev-environment.md) for prerequisites, approved
network exclusions/ownership and owner execution. Python 3 and Administrator
PowerShell 7 with Hyper-V tools are required. All scripts are MIT.

Offline tests import `Twinfra.psm1` with explicit fixture inventory, parse the
entry point without execution, and exercise all six Amendment 3 cases.

```powershell
pwsh -NoProfile -File deploy/hyperv/test-plan.ps1
```

## Fixture -Plan output

The fixture has 30 GiB free RAM and 150 GiB disk. This is **not this host’s real
inventory** and gives no approval to provision. No downloads, VM creation or
network changes occurred.

```text
PLAN ONLY: no downloads, files, network or VM changes
VM: twinfra-dev-cairo-1 | Generation 2 | 8 vCPU | 24 GiB static RAM | 100 GiB dynamic VHDX
Nested virtualization: enabled; VM remains Off until owner starts it
Switch: twinfra-nat | 10.50.0.0/24 | gateway 10.50.0.1 | VM 10.50.0.10
Pods: 10.110.0.0/16 | Services: 10.111.0.0/16
Image URL: https://cloud-images.ubuntu.com/noble/20260926/noble-server-cloudimg-amd64.img
File: noble-server-cloudimg-amd64.img | Size: 625612288 bytes | SHA256: 6a81c37564db9b1ee84e141922625e1d7c5b389b99bb3c572e0243607d5bb4d2
Checksums: https://cloud-images.ubuntu.com/noble/20260926/SHA256SUMS
Disk: E:\Twinfra\twinfra-dev-cairo-1\twinfra-dev-cairo-1.vhdx | Seed: E:\Twinfra\twinfra-dev-cairo-1\seed.iso
Actions: Verify Canonical download; Create NoCloud ISO; Create/verify owned NAT; Convert/resize dynamic VHDX; Create Generation 2 VM (left Off)
Existing VM already verified: False
```

The owner must review a fresh real `-Plan`, supply an SSH public key and ensure
registry/PKI prerequisites before execution. The VM remains Off until explicitly
started. Generic QCOW2 conversion is bounded and tested with synthetic plain,
zero and compressed clusters; live Ubuntu/NoCloud/Hyper-V boot remains Pending.
