# Releasing

Twinfra is a **product** repository with three release streams: **Dev → Candidate → Stable**.

## Streams

| Stream | Where it comes from | Version | Where it runs |
| --- | --- | --- | --- |
| **Dev** | Every merge to `main` | No tag | The dev environment `cairo-1`, which tracks `main` |
| **Candidate** | Alphas and betas on `main`. From the first `-rc.1`: the branch `release/X.Y` | `vX.Y.Z-alpha.N`, `-beta.N`, `-rc.N`, published as GitHub **pre-releases** | An acceptance window on `cairo-1` (below) |
| **Stable** | The same commit as the accepted candidate. The release workflow creates a **draft**, and the owner publishes it | `vX.Y.Z` | Production profiles, once they exist |

Twinfra stays at **0.x** until a production profile with multi-node high availability exists. The first candidate, `v0.1.0-rc.1`, follows the owner's acceptance of the `cairo-1` dev environment.

## Version source

`VERSION` holds the **next release's base version** (`0.1.0`). `compatibility.yaml` states what a release requires (Kubernetes, Cilium) and provides (the AWS-compatible API).

## What a release contains

Each release attaches:
- `platform-images.lock.json` and `console-image.lock.json`: every image, pinned by digest;
- `licence-register.json`;
- `compatibility.yaml`;
- `SHA256SUMS`.

The SBOM and scan reports from the supply-chain gate will be attached in a later change.

## Cutting a release

1. **Prepare.** Open a PR titled `release: X.Y.Z-rc.N` or `release: X.Y.Z-alpha.N`. In `CHANGELOG.md`, move `## [Unreleased]` into `## [X.Y.Z-alpha.N]` (for an alpha) or `## [X.Y.Z]`. Merge it.
2. **Branch.** For the first rc, create `release/X.Y` from that commit.
3. **Candidate.** Tag and push. The `release` workflow:
   - checks the tag against `VERSION` and the changelog;
   - checks the branch: alphas and betas on `main` or `release/X.Y`; rcs only on `release/X.Y`;
   - creates a pre-release with the records attached.
4. **Acceptance window (owner, live).**
   - Pin the platform's Argo CD Application `targetRevision` to the candidate tag on `cairo-1`.
   - Run the acceptance receipt, then set it back to `main`.
   - When a separate staging environment exists, candidates go there instead.
5. **Stable.** Tag the **same commit** `vX.Y.Z`. The owner publishes the draft.
6. **Fixes.** Fix on `main` first, then `git cherry-pick -x` onto `release/X.Y`, then cut a new rc.
7. **Next.** After a stable release, open a PR that bumps `VERSION`.

## Rules

- **Tags are immutable.**
- **Every change goes through a PR.**
  - `main` requires the `vCloud PR gate` (licence, supply chain, historical baselines) and `release-checks`.
  - `release/*` requires `release-checks`. The PR gate will cover `release/**` before the first release branch is cut.
- **Every PR updates `CHANGELOG.md` under `[Unreleased]`**, or carries the label `changelog:skip` with a reason.

The rulesets are in `.github/rulesets/`. The existing `vcloud-main-governance` ruleset stays until WO-35 renames it.
