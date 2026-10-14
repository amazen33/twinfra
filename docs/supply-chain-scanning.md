# Supply-chain image-reference validation

[WO-31 Amendments 13–13b](work-orders/WO-31-bare-metal-cairo-1.md) govern the
[image-reference guard](../tools/platform_image_references.py). It renders
locally with the existing Bash, Helm and Kustomize tools; it never provisions,
pulls, stages, applies or connects to the dev host.

| Scope | Lock and rule | Result |
| --- | --- | --- |
| A: dev platform/services workloads in every rendered region | `deploy/common/images.lock.json`; canonical repository plus the locked digest, optionally retaining a tag | Blocking |
| B: dev bootstrap/system images | `deploy/common/bootstrap-images.lock.json`; digest references, with the closed kubeadm/containerd tag allowance below | Blocking |
| C: production cloud-init/profile renders | The same resolution rules; print dated production debt and preserve existing production references | Report-only warning |

The guard checks container, init and ephemeral images, CR image fields
including Cluster/ImageCatalog/ClusterImageCatalog/Pooler, and literal env
values whose names contain `IMAGE`. Missing or indirect IMAGE env values cannot
prove lock resolution and fail in dev. CRD schema declarations are field
definitions; the instances that use those fields are checked. Kustomize builds
every existing dev platform/services overlay; cairo-2 currently has only a seed.
The real CI kubeadm dry-run also checks its four actual generated static Pods.

CNPG's operator setting takes version `1.30.1` from the checksum-verified vendor
manifest and the repository/digest from `images.lock.json`. Its generated init
containers therefore use the existing pinned CRI digest record. The vendor,
image locks and image content are unchanged. The owner-only stuck initdb Job
recovery is documented in the [dev runbook](dev-environment.md).

## Closed bootstrap tag allowance

`BOOTSTRAP_TAG_ALLOWLIST` is a constant with exactly these renderer/object/ref
bindings. Each reference must also equal a canonical name in the bootstrap lock,
which the existing staging step stages and digest-verifies before kubeadm init.
An ADR or work-order amendment is required to add a binding. A Helm-installed
image cannot use this allowance, even if its tag appears in an image lock.

| Renderer and object | Approved canonical tag |
| --- | --- |
| kubeadm Pod/kube-apiserver | `registry.twinfra.example.com/registry.k8s.io/kube-apiserver:v1.36.5` |
| kubeadm Pod/kube-controller-manager | `registry.twinfra.example.com/registry.k8s.io/kube-controller-manager:v1.36.5` |
| kubeadm Pod/kube-scheduler | `registry.twinfra.example.com/registry.k8s.io/kube-scheduler:v1.36.5` |
| kubeadm Pod/etcd | `registry.twinfra.example.com/registry.k8s.io/etcd:3.6.8-0` |
| kubeadm Deployment/coredns | `registry.twinfra.example.com/registry.k8s.io/coredns:v1.14.2` |
| containerd sandbox_image (1.x) / pinned_images.sandbox (2.x) | `registry.twinfra.example.com/registry.k8s.io/pause:3.10.1` |
| kubeadm pause image | `registry.twinfra.example.com/registry.k8s.io/pause:3.10.2` |

The guard checks both dev regions, both containerd config generations, and the
checksum-verified kubeadm version constants. Cilium remains digest-pinned.
The unused `DaemonSet/nvidia-device-plugin-mps-control-daemon` is removed just
as Module -1's existing filter removes it; the production device-plugin
DaemonSet is still reported. No unused runtime object gets a blanket waiver.

## Production follow-up

Scope C remains debt for a separate work order: Stage C registry names under
ADR-0036, an NVIDIA digest lock or an approved `operator-pulled` record under
ADR-0044, and the production smoke image references. No production references,
locks or digests change in this PR. The snapshot below comes from the offline
production renderer, including conditional NVIDIA and CPU smoke templates;
it is not a live production inventory. Both production cloud-init files and
the shared bootstrap remain byte-identical. There is no production CNPG
Deployment in the current profile to patch.

## Run the static guard

```bash
python tools/platform_image_references.py --bash bash --helm helm --kustomize kustomize \
  --nvidia-chart .build/ci-tools/nvidia-device-plugin-0.20.1.tgz --out .build/image-references
python -m unittest discover -s tests -p test_image_references.py -v
```

The existing licensed CI tools must already be staged. The required PR gate
records JSON and dated text/Markdown under `image-references/`, alongside the
real kubeadm preview and its production debt report. Historical revisions
without this guard keep their original tests; candidate controls enforce the
actual dev kubeadm preview on all seven matrix jobs. New incomplete guard
bundles fail instead of silently disappearing from the matrix.

<!-- BEGIN GENERATED PRODUCTION IMAGE DEBT -->
## Production image-reference debt

Snapshot: 2026-10-14. Report-only scope C; no production references changed.

Input sources: `production`, `user-data-remote.yaml`, `user-data.yaml`.

| Consumers | Reference | Finding |
| --- | --- | --- |
| Job/allowed, Job/denied, Pod/server | registry.vcloud.example.com/docker.io/library/busybox:1.37.0 | Missing/invalid digest or tag-only reference outside the closed bootstrap allowance |
| Job/hugepages | registry.vcloud.example.com/docker.io/library/python:3.12.12-slim | Missing/invalid digest or tag-only reference outside the closed bootstrap allowance |
| DaemonSet/nvidia-device-plugin | registry.vcloud.example.com/nvcr.io/nvidia/k8s-device-plugin:v0.20.1 | Missing/invalid digest or tag-only reference outside the closed bootstrap allowance |
| DaemonSet/cilium-envoy | registry.vcloud.example.com/quay.io/cilium/cilium-envoy:v1.37.6-1789133542-cbec91f666af0bf742da986d43832932dbb26b82@sha256:af7382699576b9e65e9184efa52eeca0b58aea70ad6e511bf260c91d9f740463 | Repository/digest does not resolve to this scope lock |
| DaemonSet/cilium | registry.vcloud.example.com/quay.io/cilium/cilium:v1.20.2@sha256:2939231d0d3e3ebddcd80fffa168b7ddcc78fdf0dc864d1c8c126ff523c54f01 | Repository/digest does not resolve to this scope lock |
| Deployment/cilium-operator | registry.vcloud.example.com/quay.io/cilium/operator-generic:v1.20.2@sha256:64d8798350e8569b8e7622563fed6e44dce2625f311e4651b774816516c744fc | Repository/digest does not resolve to this scope lock |
| Deployment/coredns | registry.vcloud.example.com/registry.k8s.io/coredns:v1.14.2 | Missing/invalid digest or tag-only reference outside the closed bootstrap allowance |
| Pod/etcd | registry.vcloud.example.com/registry.k8s.io/etcd:3.6.8-0 | Missing/invalid digest or tag-only reference outside the closed bootstrap allowance |
| Pod/kube-apiserver | registry.vcloud.example.com/registry.k8s.io/kube-apiserver:v1.36.5 | Missing/invalid digest or tag-only reference outside the closed bootstrap allowance |
| Pod/kube-controller-manager | registry.vcloud.example.com/registry.k8s.io/kube-controller-manager:v1.36.5 | Missing/invalid digest or tag-only reference outside the closed bootstrap allowance |
| Pod/kube-scheduler | registry.vcloud.example.com/registry.k8s.io/kube-scheduler:v1.36.5 | Missing/invalid digest or tag-only reference outside the closed bootstrap allowance |
| ContainerRuntimeConfiguration/containerd | registry.vcloud.example.com/registry.k8s.io/pause:3.10.1 | Missing/invalid digest or tag-only reference outside the closed bootstrap allowance |
| RuntimeImage/pause | registry.vcloud.example.com/registry.k8s.io/pause:3.10.2 | Missing/invalid digest or tag-only reference outside the closed bootstrap allowance |

<!-- END GENERATED PRODUCTION IMAGE DEBT -->
