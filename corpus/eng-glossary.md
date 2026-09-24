---
doc_id: eng-glossary
title: Engineering Glossary
doc_kind: standalone
version: null
effective_date: 2026-02-23
status: current
superseded_by: null
applies_if: []
conflicts_with: []
sensitivity: internal
department_scope: [Engineering]
owner: Engineering - Developer Experience
---

# Engineering Glossary

Short definitions of terms you will hear in engineering meetings, tickets and
runbooks.

**Blameless postmortem.** A written review after an incident that looks at
what happened and how to prevent it, without blaming individuals.

**Canary release.** Sending a new version to a small share of traffic first,
and widening it only if error rates stay normal.

**CODEOWNERS.** A file in each repository that lists which team owns which
paths. It decides who is asked to review a pull request.

**Feature flag.** A setting that turns a piece of code on or off without a new
deployment.

**Flaky test.** A test that sometimes passes and sometimes fails on the same
code.

**Incident commander.** The person who coordinates the response to a major
incident. It is usually the on-call primary until someone else takes over.

**Pull request (PR).** A request to merge changes from a branch into another
branch, where the changes are reviewed.

**Rollback.** Returning a service to its previous working version.

**Runbook.** Step-by-step instructions for operating a service or handling a
known problem.

**SLO (service level objective).** A target for how reliable a service should
be, such as the share of requests that succeed.

**Staging.** An environment that mirrors production, used for final checks
before a release.

**Trunk.** The main branch (`main`) that all work merges into.
