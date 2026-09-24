---
doc_id: eng-branching-strategy
title: Branching Strategy
doc_kind: standalone
version: null
effective_date: 2026-03-16
status: current
superseded_by: null
applies_if: []
conflicts_with: []
sensitivity: internal
department_scope: [Engineering]
owner: Engineering - Developer Experience
---

# Branching Strategy

We use trunk-based development. `main` is always releasable, and all work is
merged into it through short-lived branches.

## Branch types

| Branch | Created from | Merges into | Purpose |
|---|---|---|---|
| `main` | n/a | n/a | The trunk. Protected; no direct pushes. |
| `feature/<ticket-id>-<summary>` | `main` | `main` | New work and fixes. |
| `hotfix/<ticket-id>` | release tag | release, then `main` | Urgent production fixes. |
| `release/<version>` | `main` | none | Only for services that ship on a fixed schedule. |

## Rules for feature branches
- Keep branches short-lived. Aim to merge within a couple of working days.
  Long-running branches become hard to review and hard to merge.
- Rebase on `main` instead of merging `main` into your branch. This keeps
  history linear.
- Hide unfinished work behind a feature flag rather than keeping it on a
  branch.
- Name the branch after the ticket so it links automatically.

## Protected branch settings
`main` requires a pull request, a passing CI pipeline and at least one
approving review. Force pushes and deletion are blocked. Only the Developer
Experience team can change these settings.

## Tags and releases
Every production deployment is tagged `v<major>.<minor>.<patch>` by the
deployment pipeline. Do not create release tags by hand.

## Hotfixes
For an urgent fix to production, follow the hotfix branch how-to. The fix
must also be merged into `main` so it is not lost in the next release.
