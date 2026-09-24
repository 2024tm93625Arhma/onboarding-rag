---
doc_id: eng-deployment-runbook
title: Production Deployment Runbook
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

# Production Deployment Runbook

This runbook describes how to deploy a service to production using the
shared deployment pipeline. It applies to every service that runs on the
company Kubernetes platform. Services with their own runbook may add steps,
but should not skip any of the checks below.

## Who can deploy
Any engineer who is a member of the service's owning team in GitHub can
start a deployment. New engineers should do their first production
deployment with their onboarding buddy watching. Deployments of shared
platform components (ingress, service mesh, logging) can only be started by
the Platform team.

## When to deploy
- Deploy during working hours, Monday to Thursday, when the owning team is
  online to watch the release.
- Avoid deploying on Fridays, on the day before a public holiday, or during
  a declared change freeze. Change freezes are announced in
  #eng-announcements.
- Do not deploy while there is an open SEV1 or SEV2 incident affecting your
  service or its dependencies, unless the deployment is the fix.

## Before you start
1. Check that the change is merged into `main` and that the CI pipeline for
   that commit passed.
2. Check that the change has been running in staging and that the staging
   dashboards look normal: error rate, latency and saturation.
3. If the change includes a database migration, confirm that it is backwards
   compatible. The old version of the service must keep working after the
   migration has run, because it will still be serving traffic during the
   rollout.
4. If the change is risky, put it behind a feature flag so you can turn it
   off without a rollback.
5. Post in your team channel that you are about to deploy, with a link to
   the pull request.

## Starting the deployment
1. Open the deployment pipeline for your service and choose the commit from
   `main` that you want to release.
2. Select **Deploy to production**. The pipeline tags the commit with the
   next version number and builds the release notes from the merged pull
   requests.
3. The pipeline runs any database migrations first, as a separate job. If
   the migration job fails, the deployment stops and nothing else changes.

## Canary stage
The new version is first sent a small share of production traffic. During
this stage:

- Watch the canary dashboard for your service. It compares the canary with
  the stable version side by side.
- The pipeline checks error rate and latency automatically. If either is
  clearly worse than the stable version, the pipeline stops the rollout and
  sends traffic back to the stable version.
- Look at the logs for new errors or warnings, even if the automatic checks
  pass. Automatic checks do not catch every problem.

If you are unsure whether the canary is healthy, do not promote it. Ask in
#platform-help or roll back.

## Full rollout
When you are satisfied with the canary, select **Promote**. The pipeline
moves the rest of the traffic to the new version in steps and waits between
each step. You can pause the rollout at any point.

After the rollout finishes:

- Keep watching the service dashboards and alerts for a while before you
  move on to other work.
- Check any user journeys the change affects, for example by using the
  feature yourself in production if it is safe to do so.
- Post in your team channel that the deployment is complete, with the new
  version number.

## If something goes wrong
- If users are affected, roll back first and investigate afterwards. Follow
  the rollback runbook.
- If the problem is contained to a feature behind a flag, turning the flag
  off is usually faster than a rollback.
- If you roll back, or if the problem affected users, open an incident in
  #incidents so the response is tracked and a postmortem can be written if
  needed.

## Deployment checklist
- [ ] Change is merged into `main` and CI passed.
- [ ] Change has run in staging and dashboards look normal.
- [ ] Database migrations are backwards compatible.
- [ ] Team channel told before and after the deployment.
- [ ] Canary watched and healthy before promotion.
- [ ] Dashboards watched after full rollout.

## Getting help
For problems with the deployment pipeline itself, ask the Platform team in
#platform-help. Outside working hours, page the Platform on-call primary
through the paging tool.
