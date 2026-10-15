# ADR-0052: Evidence first — the evidence model and the Foundation 1.0 gate

**Status:** Accepted (owner, 2026-10-16, decisions 1-4; decision 3 confirmed "3 yes").
**Author:** Claude (platform architecture). **Decider:** Ahmed Mazen, Owner and Product Owner.

## Context

Two external reviews (2026-10-16) found that Twinfra's design discipline is strong, but that much of it is approved design rather than evidence. Checking the ADR index on `main` confirmed this:
- every "Accepted (lab)" ADR cites WSL receipts from 2026-10-07, and that environment is retired (ADR-0045);
- eleven ADRs are still "Proposed";
- the README still presents the WSL lab as live.

`cairo-1` (the bare-metal Dell, ADR-0048) is now the only real environment.

## Decisions

1. **Evidence first.** No new product features until **Foundation 1.0** is accepted. Design work continues, for example the tenancy ADR-0053 and the WO-22 preparation.
   EdgePulse may still follow WO-08 as a dev workload, with no production claims.
2. **The evidence model.** Every ADR carries exactly one of these statuses, and the ADR index shows its evidence:
   - **Proposed:** a design, not yet decided.
   - **Accepted (design):** the owner decided it; there is no live evidence yet.
   - **Dev-verified:** live on `cairo-1`, with a receipt whose tester sign-off is Accepted.
   - **Production-accepted:** live on a production profile, with a receipt. None exists today.
   - **Deferred (reference design):** kept for reference and off the roadmap.
   - **Superseded:** replaced by a named ADR.

   Evidence from a retired environment (WSL) is labelled **Historical** and does not count. A claim in the README or the docs may not be stronger than the status of the ADR behind it.
3. **Foundation 1.0 gate.** Accepted when every row below is Dev-verified on `cairo-1` with the tester's sign-off. It is then released on the Stable stream (REL-01).

   | Area | Required evidence | Work |
   | --- | --- | --- |
   | Host and network | Static node address; staging safety; a router power cycle survived | WO-36, WO-36a |
   | Data | Backups and a point-in-time restore drill | WO-09 |
   | Availability | Multi-node readiness at size 1; performance baseline and load soak. HA is **not** claimed until there are three nodes | WO-33 |
   | Secrets | OpenBao initialised and unsealed (owner ceremony), External Secrets, cert-manager | WO-08 |
   | Identity | Console roles, forgery protection, audit; a decision on ADR-0022 | WO-11 |
   | Observability | Durable metrics, logs and traces with retention; one alert delivered to a person; dashboards (Perses) | WO-10 |
   | Policy | Admission policies in audit, then enforcement | WO-05 |
   | Supply chain | Vulnerability gate (done); signed provenance **verified at deploy** | New WO (see decision 5) |
   | Evidence | Every former "Accepted (lab)" ADR re-verified on `cairo-1`, or downgraded | New WO |

4. **Deferred (reference design):** ADR-0014 (Kafka), ADR-0015 (Strimzi), ADR-0016 (vLLM), ADR-0017 (LangChain RAG) and ADR-0023 (DeepSeek planning).
   Modules 5a and 5b stay disabled. Any of these returns only by a new owner decision.
5. **Accepted (owner, 2026-10-16):** supersede ADR-0008 (Tekton) and ADR-0020 (delivery) with GitHub Actions, GHCR images built and pushed by CI using `GITHUB_TOKEN`, signed provenance attestations, and verification of the expected signer and provenance before deployment.
6. **Not claimed until evidenced:** high availability, multi-tenancy (until ADR-0053 is implemented and its cross-account denial tests pass), any compliance (PCI DSS, HIPAA, PDPL) without scoped controls and an independent assessment, and production readiness.

## Consequences

Product features (WO-22 and Wave 2) wait for Foundation 1.0. The README and the ADR index become an honest, checkable statement of what works. The next weeks are spent turning design into evidence on `cairo-1`.
