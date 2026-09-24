---
doc_id: eng-on-call-handbook
title: On-Call Handbook
doc_kind: standalone
version: null
effective_date: 2026-04-20
status: current
superseded_by: null
applies_if: []
conflicts_with: []
sensitivity: internal
department_scope: [Engineering]
owner: Engineering - Site Reliability
---

# On-Call Handbook

This handbook explains how on-call works for teams that run production
services. The current schedule is published in each team's on-call rota.

## How the rota works
- Each team has a primary and a secondary on call. Shifts start and end on
  Monday mornings.
- New engineers shadow a shift before they join the rota as secondary.
- You are not put on call during approved leave. Mark your leave in the HR
  portal and tell your rota owner.

## When you are on call
- Keep your laptop and phone with you, and stay somewhere with a reliable
  internet connection.
- Make sure the paging app on your phone can make sound when your phone is
  on silent.
- Acknowledge a page promptly. If you do not, the page goes to the secondary,
  then to the engineering manager.

## Handling a page
1. Acknowledge the page.
2. Open the alert's linked runbook and follow it.
3. If users are affected, open an incident in #incidents and set the
   severity.
4. If you are not making progress, escalate to the secondary. Asking for help
   early is expected, not a sign of failure.
5. When the problem is resolved, close the incident and note what you did.

## Severity levels
| Severity | Meaning |
|---|---|
| SEV1 | A core product is down, or data is at risk. |
| SEV2 | A major feature is broken for many users. |
| SEV3 | A minor feature is degraded, or there is a workaround. |

SEV1 and SEV2 incidents need a blameless postmortem.

## Handover
At the end of your shift, post a short handover in the team channel: open
incidents, noisy alerts, and anything the next person should watch.

## Compensation
On-call allowances and time off in lieu are set by HR. Ask your manager or
the HR helpdesk for the current rules.
