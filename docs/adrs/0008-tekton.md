# ADR-0008: Tekton for CI and artifact provenance

**Status:** Proposed  
**Date:** 2026-10-05  
**Deciders:** vCloud platform owner and Principal Architect  
**Selection:** Tekton is required by Module 1.  
**Scope:** [SSoT and shared implementation contract](README.md).

## Context

vCloud needs reproducible builds, manifest checks and a traceable handoff to GitOps.
Tekton supplies Kubernetes pipeline execution; its
[Chains component](https://tekton.dev/docs/chains/) can produce signed provenance.
Installing Tekton alone does not make builds secure or establish a SLSA certification.

## Decision

- Place controllers in the supported infrastructure placement and scoped build tasks
  in `workload-apps`, separated from serving pods by identities, policies and quotas.
  Use the reviewed release's stable `tekton.dev/v1` Pipeline/Task APIs.
- The pipeline checks out an exact commit, tests the application, locks dependencies,
  builds an OCI artifact, scans it, produces an SBOM and signs image/provenance before
  publishing by digest to `registry.vcloud.example.com`. Pin every Task step, resolver
  bundle, sidecar and helper image as well as the application image.
- Generate manifests from the candidate digest and run strict kubeconform with all
  required CRD schemas, then the applicable SSoT/security checks. Propose the verified
  digest to `amazen33/vCloud` through a reviewed pull request. Argo CD performs deployment.
- Select a reviewed non-root image build profile. If the chosen builder cannot satisfy
  restricted Pod Security, run it on an isolated ephemeral build VM under a separate
  reviewed profile. No Docker socket, hostPath mount, privileged build pod or blanket
  seccomp exemption is granted by this ADR.
- Use short-lived, task-scoped OpenBao credentials. Untrusted pull-request pipelines
  cannot obtain signing/publishing/Git-write credentials. Restrict and authenticate
  trigger endpoints; do not interpolate untrusted parameters into shell code.

## Options considered

| Option | Benefits | Costs and limits |
| --- | --- | --- |
| Tekton plus Chains and artifact verification | Kubernetes-native pipeline intent and provenance | Builder/security profile and signing trust need implementation |
| External hosted CI | Smaller in-cluster CI footprint | Different execution/identity model from the requested platform |
| Privileged Docker-in-Docker tasks | Familiar build workflow | Violates current privilege and host-access constraints; rejected |

## Trade-off analysis

CI is responsible for artifact quality and provenance, while CD reconciles reviewed
intent. Splitting those writers avoids giving build code production deployment authority.

## Consequences

Signing is useful only when admission/deployment verifies the expected signer and
provenance. Admission verification is an additional implementation dependency, with
its own release/security decision. Task execution images must satisfy the
[Tekton container contract](https://tekton.dev/docs/pipelines/container-contract/).

## Action items and acceptance

- [ ] Pin Pipelines/Chains, task bundles, builder, scanners and verification schemas.
- [ ] Prove an untrusted PR cannot publish, sign, access production secrets or deploy.
- [ ] Reject an unsigned/wrong-signer artifact and a manifest with a missing schema.
- [ ] Rebuild a known commit and verify SBOM/provenance link source, digest and task identity.
