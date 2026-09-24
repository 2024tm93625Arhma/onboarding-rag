---
doc_id: eng-code-review-process
title: Code Review Process
doc_kind: standalone
version: null
effective_date: 2026-03-02
status: current
superseded_by: null
applies_if: []
conflicts_with: []
sensitivity: internal
department_scope: [Engineering]
owner: Engineering - Developer Experience
---

# Code Review Process

Every change to a shared repository goes through a pull request (PR) and at
least one review before it is merged. This page covers what authors and
reviewers are expected to do.

## Before you open a PR
- Keep the change small and focused on one thing. Split large work into a
  series of PRs that can each be reviewed on their own.
- Make sure the CI pipeline passes on your branch.
- Write a description that says what changed, why, and how you tested it.
  Link the ticket.
- Mark the PR as a draft if you want early feedback but it is not ready to
  merge.

## Who reviews
- The repository's `CODEOWNERS` file adds reviewers automatically. At least
  one code owner must approve.
- Changes to infrastructure, authentication or payment code need a second
  approval from the owning team.
- You cannot approve your own PR, and an approval from someone who pushed
  commits to the branch does not count.

## Response times
Reviewers aim to give a first response within one working day. If a PR is
urgent, say so in the team channel rather than tagging many people.

## How to give feedback
- Comment on the code, not the person.
- Prefix optional suggestions with `nit:` so the author knows they are not
  blocking.
- Use **Request changes** only for problems that must be fixed before merge,
  such as bugs, missing tests or security issues.
- If a discussion goes past a few rounds of comments, talk it through on a
  call and record the outcome in the PR.

## Merging
The author merges once the PR is approved and CI is green. Use squash merge
unless the repository's README says otherwise. Delete the branch after
merging.
