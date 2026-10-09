# ADR-0042: Build-time tools and reference-only artifacts (amends ADR-0030)

Amended by [ADR-0043](0043-module-5a-runtime-exceptions.md).

Amended by [ADR-0044](0044-licence-gate-scope-and-classes.md).

**Status:** Accepted (owner, 2026-10-09).
**Author:** Claude (platform architecture). **Decider:** Ahmed Mazen, Owner and Product Owner.
**Amends:** ADR-0030 rules 2 to 4. ADR-0030 stays in force for everything not changed here.

## Context

WO-02 could not produce a green licence gate under ADR-0030 as written. Codex stopped, correctly. Findings from `origin/main`:

- **ShellCheck 0.11.0 (GPL-3.0)** runs in CI (`tools/ci/run_checks.py`, `toolchain.lock.json`). It is a separate process whose output is never distributed.
- **26 npm packages in `console/package-lock.json` are outside the allowed list.** All are `devDependencies` (build-time only), and none is in production dependencies. The production dependencies are `react` and `react-dom`.
  - 24 are **MPL-2.0**: `lightningcss` and its platform binaries (Tailwind build).
  - 1 is **BlueOak-1.0.0**: `lru-cache`. 1 is **CC0-1.0**: `mdn-data`.
- **Spinifex (AGPL-3.0)** appears in `module-5b/artifacts.lock.json` and as the vendored file `module-5b/vendor/spinifex.toml.gz`, a template taken from the Spinifex repository. Module 5b is a disabled reference design, and ADR-0018 is superseded.

## Decision

1. **Allow BlueOak-1.0.0 and CC0-1.0** in the permitted list. BlueOak is a permissive licence in the MIT family, and CC0 is a public-domain dedication.
2. **New class `build-tool`.** A component qualifies only when all of these hold:
   - it runs only in CI or on developer machines, as a separate process or a build-time (dev) dependency;
   - it is never copied into a Twinfra artifact (container image, chart, release archive, deployed manifest) and never linked into shipped code;
   - it is used unmodified.

   Permitted licences for `build-tool`: the permitted list plus **MPL-2.0, LGPL and GPL**. **AGPL, SSPL, BUSL, Elastic-2.0 and account-gated tools stay blocked in every class.**
   Reason: copyleft obligations attach to distributing or linking the covered work. A tool whose output we do not distribute does not make Twinfra's code subject to its licence. This is an engineering position, not legal advice. The owner's legal reviewer confirms it before commercial release (ADR-0030).
3. **How the gate verifies `build-tool`.**
   - npm: the lock entry has `dev: true` and the package is not reachable from the production dependency tree.
   - Binaries: the component appears only in `tools/ci/toolchain.lock.json`.
   - If a build-tool component later appears in a shipped artifact, the gate fails.
4. **Deployed components** keep ADR-0030's rule: the permitted list only, with OpenBao (MPL-2.0) as the single recorded exception.
5. **Class `reference-only`** covers a blocked-licence artifact kept only as documentation or a disabled reference. It is allowed only:
   - under the paths listed in `referenceOnlyPaths` in `security/licence-policy.json` (initially `module-5b/`);
   - with an `expires` date of 60 days or less, and a work order that removes it;
   - when no deployable manifest, lock file, image list or GitOps source references it.

   The gate fails if a `reference-only` artifact is found outside those paths or is referenced by a deployable file. Names in prose, profiles or disabled switches (for example the word "spinifex" in a disabled console entry) are not components and are not registered.
6. **Spinifex.** `module-5b/vendor/spinifex.toml.gz` and its lock entry are registered as `reference-only`, expiring 60 days from the date WO-02 merges. A follow-up work order removes the file and the Spinifex pin from Module 5b. Until then it is not deployed.

## Consequences

The gate can go green without inventing per-package exceptions. ShellCheck stays, because it has no permissive equivalent of comparable quality. Policy exposure is limited to build-time tools and is auditable from lock files. The register records a class for every component, so the permissive-only promise for what we ship is unchanged.
