# WO-34 P2a: Argo CD 3.5.5 data-only assessment

Date: 2026-10-14. Static only, no deployment or lock update. Target release [3.5.5](https://github.com/argoproj/argo-cd/releases/tag/v3.5.5), published 2026-10-12T10:59:41Z, age eligible 2026-10-26.

## GO-2026-6612 remains: source reachability decision pending

[All-binary run 38601213896](https://github.com/amazen33/twinfra/actions/runs/38601213896) read every Go ELF in `quay.io/argoproj/argocd@sha256:13db7b10db23283b1b36f855046602e18539a8a8204c9f6f039e8896c8897518` as data. Image code never executed. The exact scanner SHA256 is recorded in the P1 receipt/toolchain. Affected symbols are present; binary mode provides no source call stack.

| Binary | Affected module/version | Fix | Affected symbols |
| --- | --- | --- | ---: |
| `/usr/bin/pebble` | `golang.org/x/net v0.40.0` | `v0.60.0` | 80 |
| `/usr/bin/pebble` | `stdlib v1.26.2` | `v1.26.9` | 217 |
| `/usr/local/bin/argocd` | `golang.org/x/net v0.59.0` | `v0.60.0` | 54 |
| `/usr/local/bin/git-lfs` | `golang.org/x/net v0.38.0` | `v0.60.0` | 80 |
| `/usr/local/bin/git-lfs` | `stdlib v1.25.3` | `v1.26.9` | 217 |
| `/usr/local/bin/helm` | `golang.org/x/net v0.55.0` | `v0.60.0` | 80 |
| `/usr/local/bin/helm` | `stdlib v1.26.4` | `v1.26.9` | 217 |
| `/usr/local/bin/kustomize` | `stdlib v1.24.0` | `v1.26.9` | 217 |

The main binary's stdlib update does not fix its x/net v0.59.0, and the bundled tools retain older Go libraries. Under Amendment 2, promotion on or after October 26 needs no new Critical/High findings, the static checks and source evidence. A reachable source call path stops promotion for an owner decision. No later clearing 3.5 patch or eligibility date is verified. No 3.6 upgrade or expedite is authorized. Existing Argo exceptions remain unchanged until their original expiry.

## Static compatibility and repository trust boundaries

Concrete checked-in Applications, AppProjects and Kustomizations were searched; CRD schema declarations and unrendered Helm templates are not treated as active configuration. Fourteen Application declarations and eight AppProjects were found:

| AppProject | sourceRepos | Declaration |
| --- | --- | --- |
| `vcloud-console` | `https://github.com/amazen33/twinfra.git` | `deploy/console/argocd.yaml` |
| `twinfra-dev` | `https://github.com/amazen33/twinfra.git` | `deploy/environments/dev/cairo-1/root.yaml` |
| `vcloud-wsl-console` | `https://github.com/amazen33/twinfra.git` | `lab/wsl/console/reference/argocd.yaml` |
| `vcloud-wsl-endpoints` | `https://github.com/amazen33/twinfra.git` | `lab/wsl/endpoints/argocd.yaml` |
| `vcloud` | `https://git.vcloud.example.com/amazen33/twinfra.git` | `module-2/manifests/gitops-root.yaml` |
| `vcloud-delivery` | `https://github.com/amazen33/twinfra.git` | `module-3/argocd/application.yaml` |
| `vcloud-ci` | `https://github.com/amazen33/twinfra.git` | `module-3/argocd/application.yaml` |
| `vcloud-hpc` | `https://github.com/amazen33/twinfra.git` | `module-5b/argocd/application.yaml` |

All eight declared projects restrict sources to owner repositories; one production reference uses the owner's internal Git mirror. No sourceRepos wildcard was found. This is a static inventory, not a live-cluster assertion about Argo's implicit default project.

- No Application uses Jsonnet, and no tracked `.jsonnet`/`.libsonnet` source was found.
- No Kustomization remote base/resource/component was found.
- No `helmGlobals.configHome` setting was found in deployable configuration.
- No Application has an OCI repository source. Therefore no Argo source OCI manifest over 4 MiB is configured; Git YAML bundles are not OCI source manifests.
- Reviewed [3.5.4 notes](https://github.com/argoproj/argo-cd/releases/tag/v3.5.4) and [3.5.5 notes](https://github.com/argoproj/argo-cd/releases/tag/v3.5.5) do not document a change to `ServerSideDiff` or `IncludeMutationWebhook`. The three generated dev Applications retain both compare options for each region; existing tests verify all six instances. This is static compatibility evidence, not live behavioral acceptance.

Owner interim controls from Amendment 1 remain: add no third-party repo/Application, protect the synced branch, and expose Argo only through the tunnel until a clearing release is live. Live acceptance stays Pending; no promotion occurs before age eligibility or without the amended gates.
