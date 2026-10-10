# ADR-0046: Professional naming: environments and regions, no "lab" (amends ADR-0038, ADR-0032 and ADR-0040)

**Status:** Accepted (owner, 2026-10-10: "remove the word lab from Twinfra; keep identity and names more professional").
**Author:** Claude (platform architecture). **Decider:** Ahmed Mazen, Owner and Product Owner.

## Decision

1. **Two separate ideas, two separate names.**
   - **Environment** says what a deployment is for: `dev`, `staging`, `production`.
   - **Region** says where it runs, as in AWS: `cairo-1`, `cairo-2`, later `riyadh-1`. A region keeps its name across environments.
2. **The first deployment** is the **dev environment in region `cairo-1`**. It runs on the owner's Hyper-V host. Its disaster-recovery partner
   (ADR-0040) is `cairo-2`. A region is a logical site, so the name stays valid when the environment later moves to production hardware.
3. **Names.** VM `twinfra-<env>-<region>` (for example `twinfra-dev-cairo-1`); cluster context the same; Hyper-V switch `twinfra-nat`.
   Resource names keep ADR-0038's `twinfra-<component>` form. Labels: `twinfra.io/environment=dev`, `twinfra.io/region=cairo-1`,
   availability-zone labels `cairo-1a`.
4. **The word "lab" does not appear** in resource, VM, namespace, secret, image, region or environment names; in label values; in domains;
   in UI text and public documents; or in new file, directory and branch names. Use "dev environment" in prose.
5. **Existing identifiers are renamed where they are rebuilt:**
   - `lab/` directories move: new Hyper-V code goes to `deploy/hyperv/`, and the WSL files go in WO-28;
   - the smoke-test Pods `vcloud-lab-allowed`, `vcloud-lab-denied`, `vcloud-lab-dns` and `vcloud-lab-server` become
     `twinfra-conformance-allowed`, `twinfra-conformance-denied`, `twinfra-conformance-dns` and `twinfra-conformance-server`;
   - everything else follows ADR-0038 and the Stage C identifiers of ADR-0036.
6. **History is unchanged.** ADRs, receipts and the WSL material keep their text until WO-28 removes the WSL files. This ADR changes no
   historical record.
7. **Rehearsal.** A second region on the same host (`twinfra-dev-cairo-2`) is a rehearsal of the DR procedure only (ADR-0040).

## Consequences

Environment and region combine without collisions: `staging` and `production` can each use `cairo-1`. The first cluster is already named like the
production pair, so nothing is renamed again later. Public text says "development environment" for what runs today, which is accurate and professional.
