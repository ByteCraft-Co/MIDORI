# Branching And Release Hygiene

This repository follows a lightweight release-flow model to keep production releases stable while allowing active feature work.

## Long-Lived Branches

- `main`: stable integration branch; release tags are cut from here.
- `develop`: optional staging branch for grouped integration before landing on `main`.

## Short-Lived Branches

- `feature/<scope>`: user-visible features.
- `fix/<scope>`: production fixes.
- `chore/<scope>`: tooling, CI, docs, and cleanup.

Short-lived branches should be rebased/merged frequently and deleted after merge.

## Release Branches

- `release/x.y.z`: stabilization only (bug fixes, docs, packaging metadata).
- no new feature work once release branch is cut.

When release validation passes:

1. Merge release branch into `main`.
2. Tag `vX.Y.Z` on `main`.
3. Merge back into `develop` if used.

## Protection Recommendations

- Require CI to pass before merge into `main`/`release/*`.
- Require at least one review for `main` and `release/*`.
- Use signed tags for production releases.
- Force-push only for tag correction, never for shared long-lived branches.
