---
doc_id: eng-rollback-runbook
title: Production Rollback Runbook
doc_kind: standalone
version: null
effective_date: 2026-06-01
status: current
superseded_by: null
applies_if: []
conflicts_with: []
sensitivity: internal
department_scope: [Engineering]
owner: Engineering - Platform
---

# Production Rollback Runbook

Use this runbook when a production deployment has caused a problem and you
need to return the service to its previous working version. It covers
services deployed with the shared deployment pipeline on the company
Kubernetes platform.

## The golden rule
If users are affected and you suspect the latest deployment, roll back
first and investigate afterwards. A rollback is a normal, safe operation.
Nobody will ask why you rolled back; they may ask why you did not.

## Decide whether to roll back
Roll back when:

- Error rates or latency got worse soon after the deployment.
- A feature changed in the deployment is broken for users.
- The canary checks passed but you see new errors in the logs that were not
  there before.

Consider other options first when:

- The broken code is behind a feature flag. Turning the flag off is faster
  and keeps the rest of the release.
- The problem is in a dependency, not in your service. Rolling back your
  service will not help; escalate to the owning team instead.
- The deployment included a database migration that is not backwards
  compatible. See the section on migrations below before you do anything.

## Rolling back during the canary stage
If the new version is still in its canary stage, select **Abort** in the
deployment pipeline. All traffic goes back to the stable version straight
away. The canary pods are removed. No further action is needed apart from
telling your team.

## Rolling back after full rollout
1. Open the deployment pipeline for your service.
2. Open the **History** tab and find the last release that was healthy. This
   is usually the one immediately before the current release.
3. Select **Redeploy** on that release. The pipeline skips the canary stage
   for a rollback and moves traffic to the previous version in one step.
4. Watch the service dashboards until error rate and latency return to
   normal.
5. Post in your team channel and in the incident channel, if there is one,
   that you have rolled back and to which version.

The pipeline does not run database migrations in reverse during a rollback.
It only changes which version of the service code is running.

## Deployments with database migrations
Our migration rules require every migration to be backwards compatible, so
the previous version of the service can run against the migrated database.
If that rule was followed, a normal rollback is safe.

If you think a migration was not backwards compatible:

1. Do not redeploy the old version yet. It may fail against the new schema
   or corrupt data.
2. Open a SEV1 or SEV2 incident in #incidents, depending on user impact.
3. Page the Platform on-call primary and the database owner for your
   service.
4. Decide together whether to roll forward with a fix or to write a
   reverse migration.

## Rolling back configuration changes
Configuration and feature flag changes are versioned separately from code.
To undo one, open the configuration service, find the change in the
service's history and select **Revert**. The change takes effect without a
deployment.

## After the rollback
- Keep the incident open until the service is stable.
- Revert the faulty commit on `main`, or mark the pull request so the change
  is not released again by accident. The next deployment from `main` would
  otherwise include the same change.
- Write down what you saw and what you did while it is fresh. If the problem
  affected users, the incident needs a blameless postmortem.
- Fix the problem, add a test that would have caught it, and deploy again
  following the deployment runbook.

## When the pipeline itself is broken
If the deployment pipeline is unavailable and you must roll back urgently,
page the Platform on-call primary. Platform engineers can roll back a
service directly on the cluster. Do not try to change production resources
by hand yourself, even if you have the access to do so; manual changes are
overwritten by the next deployment and are hard to audit.

## Quick reference
| Situation | Action |
|---|---|
| Problem during canary | **Abort** in the pipeline |
| Problem after full rollout | **Redeploy** the last healthy release |
| Broken feature behind a flag | Turn the flag off |
| Bad configuration change | **Revert** in the configuration service |
| Migration not backwards compatible | Open an incident and page Platform |
| Pipeline unavailable | Page the Platform on-call primary |
