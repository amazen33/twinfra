# cairo-1: etcd and CoreDNS maintenance, October 2026

Owner-run procedure for **twinfra-operator@192.168.1.3**, after this PR merges.
Scope: etcd **3.6.8-0 → 3.6.15-0**, CoreDNS **v1.14.2 → v1.14.7**,
Kubernetes/kubeadm remain **v1.36.5**. Authority:
[WO-40 Amendments 2 and 3](../work-orders/WO-40-twinfra-v0-1-0-release.md).
Reserve 30 minutes; expect an API interruption during the etcd restart, not a
guaranteed duration. Stop on any unexpected result. The architect reviews owner
outputs after previews and between components. These commands have **not run on
the Dell**; live paths, state, timing and results remain unverified until the
owner checks them. Do not edit or sign receipts as part of this procedure.

There is no full initialization, reset, upgrade apply or bootstrap rerun here.
The two explicitly named `init phase` commands render only their named component.
No automatic etcd snapshot restore is authorized. Keep the same SSH session for
the Dell commands; each block is one command. Never paste kubeconfigs, snapshots,
private keys or unredacted dry-run API logs into Git, chat or receipts.

## 1. Transfer reviewed inputs and read-only preflight

On the laptop in PowerShell, use the existing owner checkout. Expected: current
reviewed main, with this maintenance PR merged; do not use an unreviewed branch.

```powershell
Set-Location E:/twinfra-live
```

Expected: the reviewed commit (record it outside Git with the maintenance notes).

```powershell
git rev-parse HEAD
```

Expected: a newly created private directory; **existing directory is a stop**,
not permission to overwrite a prior backup. Use the owner's configured SSH key
and known_hosts entry; no password or host-key bypass.

```powershell
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes twinfra-operator@192.168.1.3 'mkdir -m 700 /home/twinfra-operator/wo40c-2026-10-17'
```

Expected: exactly the three reviewed files copied outside any Git checkout.
The lock is a copy of `deploy/common/bootstrap-images.lock.json`, not edited.

```powershell
scp -o BatchMode=yes -o StrictHostKeyChecking=yes tools/control_plane_candidate.py deploy/common/stage-images.py deploy/common/bootstrap-images.lock.json twinfra-operator@192.168.1.3:/home/twinfra-operator/wo40c-2026-10-17/
```

Expected: a key-authenticated Dell shell; all following bash blocks run there
until the laptop backup-copy step explicitly says PowerShell.

```powershell
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes twinfra-operator@192.168.1.3
```

Expected: private default permissions for all new local evidence files.

```bash
umask 077
```

Expected: `MAINT` points outside Git; reuse this variable for the entire window.

```bash
export MAINT=/home/twinfra-operator/wo40c-2026-10-17
```

Expected: v1.36.5. A different version stops maintenance.

```bash
kubeadm version -o short
```

Expected: `be2f2c73cd6d3414b37aafb05016bc3a1da3e17c8393aa75c34636198fefa77c`;
this is the reviewed Linux amd64 binary pin, not just a version string.

```bash
sha256sum "$(command -v kubeadm)"
```

Expected: yq v4.54.1 (already admitted by Module -1); Python 3 is installed.

```bash
yq --version
```

Expected: this node is Ready, address 192.168.1.3, Kubernetes v1.36.5.

```bash
kubectl get node twinfra-dev-cairo-1 -o wide
```

Expected: `ok`, with no TLS bypass.

```bash
kubectl get --raw=/readyz
```

Expected: etcd currently 3.6.8-0 and CoreDNS v1.14.2; if already changed, stop
and reconcile the procedure against the architect's last reviewed state.

```bash
kubectl -n kube-system get pods -l 'k8s-app=kube-dns' -o wide
```

Expected: the saved manifest displays the current canonical etcd image,
unchanged node name, certificate mount, arguments and data directory.

```bash
sudo yq '.spec.containers[] | select(.name == "etcd")' /etc/kubernetes/manifests/etcd.yaml
```

Expected: the current CoreDNS container reference, no extra containers.

```bash
kubectl -n kube-system get deployment coredns -o jsonpath='{.spec.template.spec.containers[*].image}{"\n"}'
```

Expected: the stored cluster identity, registry and current image tags. This is
read-only; the strict comparison in section 4 decides whether they match the host.

```bash
kubectl -n kube-system get configmap kubeadm-config -o jsonpath='{.data.ClusterConfiguration}'
```

Expected: enough free space for a snapshot and a second copy of the etcd data;
do not proceed if free space is less than twice `du` plus 1 GiB headroom.

```bash
df -h /var/lib/etcd /home/twinfra-operator
```

Expected: data size used to evaluate the preceding free-space condition.

```bash
sudo du -sh /var/lib/etcd
```

Expected: root-owned bootstrap configuration/patches exist, and the referenced
patch directory is `/var/lib/vcloud-host/kubeadm-patches`. These are source-derived
paths, not a claim that the live files have already been inspected.

```bash
sudo stat /var/lib/vcloud-host/kubeadm.yaml /var/lib/vcloud-host/kubeadm-patches/etcd+strategic.yaml
```

Expected: read-only `etcd-certs` patch at the configured certificate directory.

```bash
sudo cat /var/lib/vcloud-host/kubeadm-patches/etcd+strategic.yaml
```

Expected: all three Argo Applications Synced/Healthy before maintenance.

```bash
kubectl -n twinfra-platform-services get applications -o custom-columns=NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status,REVISION:.status.sync.revision
```

Expected: healthy etcd endpoint, success exit; the explicit paths below must
match the inspected manifest. A non-default certificate path is a stop for review.

```bash
kubectl -n kube-system exec etcd-twinfra-dev-cairo-1 -- etcdctl --endpoints=https://127.0.0.1:2379 --cacert=/etc/kubernetes/pki/etcd/ca.crt --cert=/etc/kubernetes/pki/etcd/healthcheck-client.crt --key=/etc/kubernetes/pki/etcd/healthcheck-client.key endpoint health
```

Expected: etcdutl 3.6.8; if the existing image lacks this binary, stop. Do not
download an unreviewed tool to work around a missing snapshot verifier.

```bash
kubectl -n kube-system exec etcd-twinfra-dev-cairo-1 -- etcdutl version
```

## 2. Backups outside Git, verified snapshot and laptop copy

Expected: all four static Pod manifests, original bootstrap config and patches
saved privately under MAINT. No PKI private keys are copied by this command.

```bash
sudo tar -C / -cf - etc/kubernetes/manifests/kube-apiserver.yaml etc/kubernetes/manifests/kube-controller-manager.yaml etc/kubernetes/manifests/kube-scheduler.yaml etc/kubernetes/manifests/etcd.yaml var/lib/vcloud-host/kubeadm.yaml var/lib/vcloud-host/kubeadm-patches > "$MAINT/manifests-and-config.tar"
```

Expected: a full saved kubeadm-config ConfigMap (including resourceVersion),
not a newly generated replacement.

```bash
kubectl -n kube-system get configmap kubeadm-config -o json > "$MAINT/kubeadm-config.before.json"
```

Expected: original CoreDNS Deployment and Corefile saved for comparison/rollback.

```bash
kubectl -n kube-system get deployment/coredns configmap/coredns -o json > "$MAINT/dns.before.json"
```

Expected: snapshot saved inside the existing data-volume mount. The filename
must not already exist; etcdctl refuses overwriting it. Only this snapshot is
created; the service remains running.

```bash
kubectl -n kube-system exec etcd-twinfra-dev-cairo-1 -- etcdctl --endpoints=https://127.0.0.1:2379 --cacert=/etc/kubernetes/pki/etcd/ca.crt --cert=/etc/kubernetes/pki/etcd/healthcheck-client.crt --key=/etc/kubernetes/pki/etcd/healthcheck-client.key snapshot save /var/lib/etcd/wo40c-before.db
```

Expected: nonzero revision, total keys/size and a snapshot hash; exit 0.
Record the output privately. Failure blocks every mutation below.

```bash
kubectl -n kube-system exec etcd-twinfra-dev-cairo-1 -- etcdutl snapshot status /var/lib/etcd/wo40c-before.db -w json > "$MAINT/snapshot-status.json"
```

Expected: the verified snapshot copied from the data volume into MAINT, owned
by the operator with mode 0600; the original remains on the Dell data volume.

```bash
sudo install -m 600 -o twinfra-operator -g twinfra-operator /var/lib/etcd/wo40c-before.db "$MAINT/etcd-before.db"
```

Expected: SHA256SUMS for all four backup artifacts, including the snapshot.

```bash
sha256sum "$MAINT/manifests-and-config.tar" "$MAINT/kubeadm-config.before.json" "$MAINT/dns.before.json" "$MAINT/etcd-before.db" > "$MAINT/SHA256SUMS"
```

Back on the laptop, in a **second** PowerShell window. Expected: a fresh private
backup directory outside Git; retain the Dell SSH shell. Restrict its Windows
ACL to the owner before downloading (the commands below disable inheritance).

```powershell
New-Item -ItemType Directory -Path E:/twinfra-backups/wo40c-2026-10-17
```

Expected: owner-only ACL; review the resulting ACL if the laptop uses a managed
account. Do not proceed if another principal retains access.

```powershell
icacls E:/twinfra-backups/wo40c-2026-10-17 /inheritance:r /grant:r "${env:USERNAME}:(OI)(CI)F"
```

Expected: backups and SHA256SUMS copied; no private backup files enter Git.

```powershell
scp -o BatchMode=yes -o StrictHostKeyChecking=yes twinfra-operator@192.168.1.3:/home/twinfra-operator/wo40c-2026-10-17/manifests-and-config.tar twinfra-operator@192.168.1.3:/home/twinfra-operator/wo40c-2026-10-17/kubeadm-config.before.json twinfra-operator@192.168.1.3:/home/twinfra-operator/wo40c-2026-10-17/dns.before.json twinfra-operator@192.168.1.3:/home/twinfra-operator/wo40c-2026-10-17/etcd-before.db twinfra-operator@192.168.1.3:/home/twinfra-operator/wo40c-2026-10-17/snapshot-status.json twinfra-operator@192.168.1.3:/home/twinfra-operator/wo40c-2026-10-17/SHA256SUMS E:/twinfra-backups/wo40c-2026-10-17/
```

Expected: four matching hashes. Any mismatch throws and stops maintenance.

```powershell
Get-Content E:/twinfra-backups/wo40c-2026-10-17/SHA256SUMS | ForEach-Object { $hash,$remote = $_ -split '\s+',2; $local = Join-Path E:/twinfra-backups/wo40c-2026-10-17 (Split-Path $remote -Leaf); if ((Get-FileHash -Algorithm SHA256 $local).Hash.ToLowerInvariant() -ne $hash) { throw "Backup hash mismatch: $local" }; Write-Output "Verified: $local" }
```

## 3. Stage the reviewed bootstrap lock, check before and after

Return to the original Dell shell. Expected initially: exactly the two missing
promoted images; if this reports other mismatches, stop for review. This explicit
conditional permits only inspection of the expected pre-staging failure.

```bash
if sudo python3 "$MAINT/stage-images.py" --lock "$MAINT/bootstrap-images.lock.json" --check > "$MAINT/staging.before.json"; then cat "$MAINT/staging.before.json"; else cat "$MAINT/staging.before.json"; fi
```

Expected: `status: passed`, `images: 11`, `problems: []` with no problems; this imports/tag-pins images only,
and does not restart pods or reconfigure kubeadm.

```bash
sudo python3 "$MAINT/stage-images.py" --lock "$MAINT/bootstrap-images.lock.json"
```

Expected: `status: passed`, `images: 11`, `problems: []`, exit 0. A failed check blocks all component changes.

```bash
sudo python3 "$MAINT/stage-images.py" --lock "$MAINT/bootstrap-images.lock.json" --check
```

## 4. Strict base-configuration comparison and candidate

Expected: the original three bootstrap documents exported as JSON; this does
not source the host shell configuration or rerun any provisioner.

```bash
sudo yq eval-all -o=json -I=0 '[.]' /var/lib/vcloud-host/kubeadm.yaml > "$MAINT/base.json"
```

Expected: the ClusterConfiguration parsed from the exact saved ConfigMap.

```bash
jq -r '.data.ClusterConfiguration' "$MAINT/kubeadm-config.before.json" | yq -o=json '.' > "$MAINT/stored.json"
```

Expected: diff showing **only** `dns.imageTag` and `etcd.local.imageTag`, or no
diff for tags already present in the host file. Both the base/stored comparison
and candidate validation run before output creation. Every other difference
fails, including explicit-vs-omitted default fields: **do not auto-normalize,
merge, remove fields or overwrite the host file to bypass this stop**. The live
equivalence of the two configurations is unverified; report any refusal to the
architect. Output is private, new-only and contains no cluster writes. Inputs and output
are confined to the copied helper's maintenance directory; path traversal or
symlink files are refused.

```bash
python3 "$MAINT/control_plane_candidate.py" --lock "$MAINT/bootstrap-images.lock.json" generate --base "$MAINT/base.json" --stored "$MAINT/stored.json" --configmap "$MAINT/kubeadm-config.before.json" --out "$MAINT/candidate"
```

Expected: kubeadm validates the candidate. Warnings for local component config
are reviewed; an error stops the window. No UpgradeConfiguration is generated.

```bash
sudo kubeadm config validate --config "$MAINT/candidate/candidate.yaml"
```

## 5. Dry-run previews and acceptance diffs

Expected: separate private preview directories (no prior output overwritten).

```bash
mkdir -m 700 "$MAINT/etcd-preview" "$MAINT/dns-preview"
```

Expected: only etcd.yaml written **under MAINT**, not the live manifest directory.
Patches come from the candidate's unchanged InitConfiguration. Capture logs
privately; the guard below compares actual files, not optimistic log messages.

```bash
sudo env KUBEADM_INIT_DRYRUN_DIR="$MAINT/etcd-preview" kubeadm init phase etcd local --config "$MAINT/candidate/candidate.yaml" --dry-run > "$MAINT/etcd-preview.log"
```

Expected: current disk manifest exported, not a mirror Pod containing API defaults.

```bash
sudo yq -o=json '.' /etc/kubernetes/manifests/etcd.yaml > "$MAINT/etcd.live.json"
```

Expected: etcd preview exported without relaxing any manifest field.

```bash
sudo yq -o=json '.' "$MAINT/etcd-preview/etcd.yaml" > "$MAINT/etcd.preview.json"
```

Expected: **PASS: etcd preview is image-only**; flags, mounts, resources, data
directory, node identity and every other field remain exactly equal. On any
failure **stop and report; etcd has no fallback**. Do not modify patches to force
a pass. CI proves this property for the renderer, not for the uninspected Dell.

```bash
python3 "$MAINT/control_plane_candidate.py" --lock "$MAINT/bootstrap-images.lock.json" verify-etcd --live "$MAINT/etcd.live.json" --preview "$MAINT/etcd.preview.json"
```

Expected: a private copy of admin.conf solely to allow the dry-run fake client
to read the existing cluster. It remains root-only and is never logged/copied to Git.

```bash
sudo install -m 600 /etc/kubernetes/admin.conf "$MAINT/dns-preview/admin.conf"
```

Expected: CoreDNS dry-run actions printed, no API mutations. Inspect every
proposed ConfigMap/Deployment and supporting resource write in this private log.
An unreadable kubeconfig/API failure is a stop, not proof of image-only behavior.

```bash
sudo env KUBEADM_INIT_DRYRUN_DIR="$MAINT/dns-preview" kubeadm init phase addon coredns --config "$MAINT/candidate/candidate.yaml" --dry-run > "$MAINT/dns-preview.log"
```

Expected: deterministic desired addon YAML, including its Corefile. This second
preview is template output with default replicas, **not** a live-merge simulator.

```bash
sudo kubeadm init phase addon coredns --config "$MAINT/candidate/candidate.yaml" --dry-run --print-manifest > "$MAINT/dns-template.yaml"
```

Expected: two review files: the live and proposed Deployment **specs** (image
will differ). Compare all defaulted fields, labels and annotations separately;
do not ignore admission mutations. A non-image difference selects the fallback.

```bash
jq -S '.items[] | select(.kind=="Deployment") | .spec' "$MAINT/dns.before.json" > "$MAINT/dns-live-spec.json"
```

Expected: the proposed Deployment spec for the same comparison.

```bash
yq eval-all -o=json 'select(.kind == "Deployment") | .spec' "$MAINT/dns-template.yaml" | jq -S . > "$MAINT/dns-proposed-spec.json"
```

Expected: image-only diff, otherwise use fallback. `diff` returns 1 for expected
differences; review it, rather than treating its exit code as an apply gate.

```bash
diff -u "$MAINT/dns-live-spec.json" "$MAINT/dns-proposed-spec.json"
```

Expected: equality of live and proposed Corefile for phase eligibility. A
different/default/migrated Corefile, any supporting-resource change, uncertainty
or an inconclusive dry run selects the pre-approved **CoreDNS-only fallback**.
The source proves the phase does not unconditionally retain an existing Corefile.

```bash
diff -u <(jq -r '.items[] | select(.kind=="ConfigMap") | .data.Corefile' "$MAINT/dns.before.json") <(yq eval-all -r 'select(.kind=="ConfigMap") | .data.Corefile' "$MAINT/dns-template.yaml")
```

Architect reviews these outputs **before proceeding**. There is no automatic
claim that the phase is safe just because the preview command returned zero.
The fallback is the default choice whenever complete image-only behavior is not
demonstrated; it changes no Corefile, RBAC, Service or ServiceAccount.

## 6. Apply etcd only, verify, then record its tag

Expected immediately before apply: no intervening change to the live etcd
manifest since the accepted preview. Any difference stops for a new review.

```bash
diff -u "$MAINT/etcd.live.json" <(sudo yq -o=json '.' /etc/kubernetes/manifests/etcd.yaml)
```

Expected: only etcd.yaml regenerated in `/etc/kubernetes/manifests`; kubelet
restarts that static Pod. This is the sole etcd mutation command, not full init.

```bash
sudo kubeadm init phase etcd local --config "$MAINT/candidate/candidate.yaml"
```

Expected within 180 seconds: the replacement etcd Pod Ready. Stop on failure;
consult rollback, and do not continue with CoreDNS or the ConfigMap tag.

```bash
kubectl -n kube-system wait --for=condition=Ready pod/etcd-twinfra-dev-cairo-1 --timeout=180s
```

Expected: healthy endpoint after restart.

```bash
kubectl -n kube-system exec etcd-twinfra-dev-cairo-1 -- etcdctl --endpoints=https://127.0.0.1:2379 --cacert=/etc/kubernetes/pki/etcd/ca.crt --cert=/etc/kubernetes/pki/etcd/healthcheck-client.crt --key=/etc/kubernetes/pki/etcd/healthcheck-client.key endpoint health
```

Expected: `ok` and node Ready.

```bash
kubectl get --raw=/readyz
```

Expected: Ready, InternalIP 192.168.1.3.

```bash
kubectl get node twinfra-dev-cairo-1 -o wide
```

Expected: desired etcd image from the unchanged lock. This and the runtime
check below are both required; Pod Ready alone may still describe the old Pod.

```bash
kubectl -n kube-system get pod etcd-twinfra-dev-cairo-1 -o json > "$MAINT/etcd.after.json"
```

Expected: true; actual etcd Pod image equals the approved canonical tag.

```bash
jq -e --slurpfile lock "$MAINT/bootstrap-images.lock.json" '.spec.containers[] | select(.name=="etcd") | .image==$lock[0].images.etcd.canonical' "$MAINT/etcd.after.json"
```

Expected: running container identity resolves to the lock's index, amd64
manifest or config digest. If the CRI reports a different format, stop and
inspect `crictl inspecti`; do not relax the digest assertion.

```bash
jq -e --slurpfile lock "$MAINT/bootstrap-images.lock.json" '.status.containerStatuses[] | select(.name=="etcd") | .imageID | split("@")[-1] as $id | [$lock[0].images.etcd | .digest,.amd64Digest,.configDigest] | index($id)!=null' "$MAINT/etcd.after.json"
```

Expected: etcd histogram samples available. Use the existing monitoring view
if available to verify WAL fsync p99 **<= 4 ms**, matching the last owner baseline;
otherwise review cumulative histogram buckets below (first bucket reaching
99% of count must be <= 0.004 seconds). Insufficient fresh samples or an unclear
histogram is **unverified**, not a pass: pause for the architect. Do not deploy
monitoring as part of this maintenance.

```bash
curl --fail --silent --show-error http://127.0.0.1:2381/metrics | grep -E '^etcd_disk_wal_fsync_duration_seconds_(bucket|count)'
```

Expected: `status: passed`, `images: 11`, `problems: []` again. Owner supplies all preceding evidence for the
architect's etcd approval before the following ConfigMap command.

```bash
sudo python3 "$MAINT/stage-images.py" --lock "$MAINT/bootstrap-images.lock.json" --check
```

Expected: only `etcd.local.imageTag` changes in the stored ClusterConfiguration.
The JSON Patch tests the exact original value first and refuses concurrent
changes. It does not replace other ConfigMap keys or the host bootstrap file.

```bash
kubectl -n kube-system patch configmap kubeadm-config --type=json --patch-file "$MAINT/candidate/etcd-configmap.patch.json"
```

## 7. CoreDNS only, verify, then record its tag

Use **one** of the following two mutation commands, never both. The phase is
eligible only after the architect accepts all preview diffs as image-only and
confirms Corefile/supporting resources are unchanged. Otherwise use the already
approved `set image` fallback. Do not use addon/all or kube-proxy.

Expected for the fully accepted phase path: only the CoreDNS image changes;
verify Corefile equality immediately afterwards.

```bash
sudo kubeadm init phase addon coredns --config "$MAINT/candidate/candidate.yaml"
```

Expected for the fallback path: only the named container image is patched,
using the exact canonical repository and locked digest (not a floating tag).

```bash
kubectl -n kube-system set image deployment/coredns "coredns=$(python3 "$MAINT/control_plane_candidate.py" --lock "$MAINT/bootstrap-images.lock.json" image coredns --digest)"
```

Expected: successfully rolled out within 180 seconds.

```bash
kubectl -n kube-system rollout status deployment/coredns --timeout=180s
```

Expected: no Corefile change. Any change triggers the CoreDNS rollback section
and architect review; do not update the stored DNS tag.

```bash
diff -u <(jq -r '.items[] | select(.kind=="ConfigMap") | .data.Corefile' "$MAINT/dns.before.json") <(kubectl -n kube-system get configmap coredns -o json | jq -r '.data.Corefile')
```

Expected: all Ready DNS pods use the lock's tag (phase path) or repo@digest
(fallback), and runtime imageIDs match the locked identity set as for etcd above.

```bash
kubectl -n kube-system get pods -l k8s-app=kube-dns -o json > "$MAINT/dns.after.json"
```

Expected: true for every CoreDNS container, at least one pod, and no old image.

```bash
jq -e --slurpfile lock "$MAINT/bootstrap-images.lock.json" '.items | length>0 and all(.[]; all(.spec.containers[]; .image==$lock[0].images.coredns.canonical or .image==($lock[0].images.coredns.canonical | sub(":[^/:]+$"; ""))+"@"+$lock[0].images.coredns.digest))' "$MAINT/dns.after.json"
```

Expected: true for every running DNS container ID (locked index/amd64/config).

```bash
jq -e --slurpfile lock "$MAINT/bootstrap-images.lock.json" '.items | all(.[]; all(.status.containerStatuses[]; .imageID | split("@")[-1] as $id | [$lock[0].images.coredns | .digest,.amd64Digest,.configDigest] | index($id)!=null))' "$MAINT/dns.after.json"
```

Expected: DNS resolution from the existing console workload. Its rendered
Cilium policy explicitly permits DNS to kube-dns on port 53, and its admitted
Python runtime already provides `socket`; no new pod, image or tool is installed.
Live workload readiness remains an owner preflight check.

```bash
kubectl -n twinfra-platform-services exec deployment/twinfra-console -c console -- python -c 'import socket; print(socket.gethostbyname("kubernetes.default.svc.cluster.local"))'
```

Expected: existing Cilium policies still present, with default-deny and explicit
DNS permission; the successful workload query is positive evidence, not a new
negative isolation test or proof of every Cilium policy.

```bash
kubectl get ciliumnetworkpolicies -A
```

Expected: Cilium reports healthy, all three Argo Applications Synced/Healthy;
if either fails, stop before recording the DNS tag.

```bash
cilium status --wait
```

Expected: all three Synced/Healthy at the reviewed revision.

```bash
kubectl -n twinfra-platform-services get applications -o custom-columns=NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status,REVISION:.status.sync.revision
```

Expected: only `dns.imageTag` now changes; the CAS test requires the exact
post-etcd ClusterConfiguration. Architect reviews the CoreDNS evidence first.

```bash
kubectl -n kube-system patch configmap kubeadm-config --type=json --patch-file "$MAINT/candidate/dns-configmap.patch.json"
```

Expected: `status: passed`, `images: 11`, `problems: []`, then the owner reruns the unchanged baseline through
the existing [release acceptance runbook](../runbooks/release-acceptance.md).
No receipt is signed until that complete acceptance run passes.

```bash
sudo python3 "$MAINT/stage-images.py" --lock "$MAINT/bootstrap-images.lock.json" --check
```

## 8. Per-component rollback (owner, on failure)

Stop before touching the next component. If a ConfigMap CAS failed, investigate
the concurrent state; never blindly apply a reverse patch. Old images must remain
cached until maintenance is accepted. No image deletion/pruning is authorized.

**etcd:** expected: saved original manifest extracted into a private recovery
directory, never directly into the live manifest directory.

```bash
mkdir -m 700 "$MAINT/rollback"
```

Expected: only the original etcd manifest extracted from the backup.

```bash
tar -xf "$MAINT/manifests-and-config.tar" -C "$MAINT/rollback" etc/kubernetes/manifests/etcd.yaml
```

Expected: original manifest restored atomically using a temporary file **outside**
the kubelet manifest directory, on the same filesystem. Kubelet restarts etcd
using the saved flags, mount and old cached image. No snapshot restore occurs.

```bash
sudo install -m 600 "$MAINT/rollback/etc/kubernetes/manifests/etcd.yaml" /etc/kubernetes/wo40c-etcd.rollback
```

Expected: atomic replacement, only etcd affected.

```bash
sudo mv /etc/kubernetes/wo40c-etcd.rollback /etc/kubernetes/manifests/etcd.yaml
```

Repeat etcd endpoint health, API readiness, Ready node and old image verification
from section 6. If etcd verification failed before tag recording, **leave the
ConfigMap unchanged**. If the etcd tag had already been recorded and DNS had not,
or after the DNS rollback below, restore only its previous stored value:

```bash
kubectl -n kube-system patch configmap kubeadm-config --type=json --patch-file "$MAINT/candidate/rollback-etcd-configmap.patch.json"
```

**CoreDNS:** expected: restore only the saved Deployment image, leaving the
Corefile alone. Confirm the saved Deployment has exactly one `coredns` container.

```bash
kubectl -n kube-system set image deployment/coredns "coredns=$(jq -r '.items[] | select(.kind=="Deployment") | .spec.template.spec.containers[] | select(.name=="coredns") | .image' "$MAINT/dns.before.json")"
```

Expected: old image rollout completes; repeat Corefile equality, permitted
workload DNS, Cilium and GitOps verification. If the phase unexpectedly changed
the Corefile, stop and have the architect review the saved ConfigMap before
restoring it; no blind whole-ConfigMap apply is prescribed.

```bash
kubectl -n kube-system rollout status deployment/coredns --timeout=180s
```

If DNS failed before tag recording, **leave the stored DNS tag unchanged**. Only
if its tag was recorded, restore the previous DNS value after old-image health:

```bash
kubectl -n kube-system patch configmap kubeadm-config --type=json --patch-file "$MAINT/candidate/rollback-dns-configmap.patch.json"
```

An etcd snapshot restore is a **last resort requiring a separate reviewed owner
decision**, not another command in this runbook. Preserve the verified snapshot,
original manifests and PKI; do not reset/init or overwrite a live data directory.

## Source verification and limits

All upstream links below are pinned to **v1.36.5**, not a moving documentation
branch. Source review and the isolated CI preview are static evidence only.

- [etcd phase flags and execution](https://github.com/kubernetes/kubernetes/blob/v1.36.5/cmd/kubeadm/app/cmd/phases/init/etcd.go):
  `getEtcdPhaseFlags` includes config, dry-run and patches; only the local etcd
  manifest is generated. The non-dry-run path also ensures its existing data
  directory exists. It does not initialize/reset the existing etcd database.
- [addon flags and init data](https://github.com/kubernetes/kubernetes/blob/v1.36.5/cmd/kubeadm/app/cmd/phases/init/addons.go):
  CoreDNS accepts config/dry-run/print-manifest. It has no inherited `--patches`
  flag; it still receives `data.PatchesDir()` from InitConfiguration.
- [init configuration, patches and dry-run client](https://github.com/kubernetes/kubernetes/blob/v1.36.5/cmd/kubeadm/app/cmd/init.go):
  `PatchesDir()` reads `cfg.Patches.Directory` when using `--config`; the
  general accessor also supports a flag, but mixed config/patches flags are
  rejected by command validation (the runbook never combines them);
  `ManifestDir()` uses the dry-run directory; `KubeConfigPath()` uses admin.conf
  inside that directory in dry-run. Fake-client writes are printed, not applied;
  reads can use the supplied existing cluster credentials.
- [etcd rendering and patch application](https://github.com/kubernetes/kubernetes/blob/v1.36.5/cmd/kubeadm/app/phases/etcd/local.go):
  patches are applied before writing/printing. The strict file comparison is
  required because an identical config alone cannot prove an unchanged live Pod.
- [CoreDNS existing ConfigMap behavior](https://github.com/kubernetes/kubernetes/blob/v1.36.5/cmd/kubeadm/app/phases/addons/dns/dns.go):
  an empty/default Corefile is replaced with the current default; a custom one
  may be migrated, otherwise retained. The phase also creates/updates RBAC,
  ServiceAccount and Deployment. It is not a guaranteed image-only updater.
- Repository [bootstrap](../../00-setup-ubuntu-host.sh), `load_config`,
  `render_kubeadm`, `bootstrap_kubernetes`, and `render_etcd_patch`:
  state is `/var/lib/vcloud-host`, with `kubeadm.yaml` and
  `kubeadm-patches/etcd+strategic.yaml`. The host-admin staging directory
  `/var/lib/twinfra/host-bootstrap` contains the provisioner inputs, **not** the
  authoritative rendered kubeadm configuration. This runbook never reruns it.

Open live questions: do the host/stored configurations agree strictly (including
materialized defaults), does the actual etcd preview pass image-only comparison,
is the existing console ready for its permitted DNS query, and are fresh WAL
samples sufficient? Each is a stop/checkpoint, never a presumed successful result.
