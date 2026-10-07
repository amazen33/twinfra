# vCloud milestones

## Milestone: Zero-Trust Streaming & GitOps Core

- [x] FIX: Enforce air-gapped imagePullPolicy: IfNotPresent and containerd path-rewrite rules (Issue #412).
- [ ] QA: Validate offline cluster bootstrap from cold CRI cache without internet egress.

The completed item tracks repository implementation and automated checks. It does
not close live mirror DNS/TLS, authenticated pull, controller ownership or rollout
acceptance. Cold-cache QA requires vetted offline image imports or a reachable
internal mirror; no external runtime fallback is enabled.
