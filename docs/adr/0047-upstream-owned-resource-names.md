# ADR-0047: Upstream-owned resource names keep their upstream names (amends ADR-0038)

**Status:** Accepted (owner delegated to the architect, 2026-10-10, after Codex's stop on Argo CD names). Review by the owner at merge.
**Author:** Claude (platform architecture). **Decider:** Ahmed Mazen, Owner and Product Owner.

## Context

ADR-0038 says every resource is named `twinfra-<component>`. Some pinned upstream software looks up fixed names directly. Argo CD 3.5.3 reads
`argocd-cm`, `argocd-cmd-params-cm`, `argocd-rbac-cm` and `argocd-secret` by name, and its components find each other through fixed Service and
Deployment names. Renaming them breaks configuration loading. The same applies to other upstream projects (for example Cilium's `cilium-config`).

## Decision

1. **Two owners, two rules.**
   - **Twinfra-owned resources** are everything Twinfra creates or generates. They keep ADR-0038 and ADR-0046: `twinfra-<component>`, and no `lab`, `wsl` or `vcloud` in any name.
   - **Upstream-owned resources** are objects defined by a pinned upstream manifest or chart that the upstream software refers to by name. They keep their upstream
     names exactly as shipped. Twinfra does not rename them, and it does not patch the vendored files to do so.
2. **Environment and region still show.** Upstream-owned objects receive the Twinfra labels (`twinfra.io/environment`, `twinfra.io/region`,
   `twinfra.io/component`) through kustomize or Helm label transformers. Labels never change selectors (`includeSelectors: false`).
3. **Names Twinfra chooses inside upstream software are Twinfra-owned.** Examples: Argo CD Application and AppProject names, Keycloak realm and client IDs,
   Secrets that Twinfra creates and mounts, ConfigMaps Twinfra adds, and Namespaces from the SSoT.
4. **Register and enforcement.** `deploy/upstream-names.json` lists each upstream project, its pinned version, the source (vendored manifest or chart) and the names
   that are upstream-owned. A CI check renders every environment and fails if any resource whose name does not start with `twinfra-` is absent from that file, or if a
   listed name no longer exists in the pinned source. An upstream version bump updates the file in the same PR.
5. **What does not change.** The ban on `lab`, `wsl` and `vcloud` in Twinfra-owned names, the ADR-0038 labels, and the digest pinning rule.

## Consequences

Upstream software keeps working unmodified and upgrades stay cheap. Reviewers can see in one file which names are not ours and why, and nothing
unlisted can slip in.
