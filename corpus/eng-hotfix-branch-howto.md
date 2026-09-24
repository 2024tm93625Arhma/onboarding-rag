---
doc_id: eng-hotfix-branch-howto
title: How to Create a Hotfix Branch
doc_kind: standalone
version: null
effective_date: 2026-04-06
status: current
superseded_by: null
applies_if: []
conflicts_with: []
sensitivity: internal
department_scope: [Engineering]
owner: Engineering - Developer Experience
---

# How to Create a Hotfix Branch

Use a hotfix branch only for an urgent fix to what is running in production.

1. Branch from the latest release tag, not from `main`:
   `git switch -c hotfix/<ticket-id> v<release>`.
2. Make the smallest change that fixes the problem, with a test.
3. Open a pull request against the release tag's branch and label it
   `hotfix`. One approving review is enough.
4. After it is deployed, open a second pull request to bring the same fix
   into `main`.

Do not mix refactoring or unrelated changes into a hotfix.
