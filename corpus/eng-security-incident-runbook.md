---
doc_id: eng-security-incident-runbook
title: Security Incident Runbook
doc_kind: standalone
version: null
effective_date: 2026-05-18
status: current
superseded_by: null
applies_if: []
conflicts_with: []
sensitivity: confidential
department_scope: [Engineering]
owner: Engineering - Security Operations
---

# Security Incident Runbook

**Classification: Confidential. Engineering only.**

This runbook tells engineers what to do when they suspect a security
incident: unauthorised access, leaked credentials, malware, data leaving the
company when it should not, or an attack on a production service. It sits
alongside the On-Call Handbook. Reliability incidents use the SEV levels in
that handbook; security incidents use the SEC levels below, and an event can
have both.

## Step 1: Recognise it

Treat any of these as a possible security incident until Security Operations
says otherwise:

- a secret, token or private key found in a repository, log, ticket or chat;
- alerts from the endpoint protection agent or the cloud threat detector;
- logins from unexpected countries or at impossible travel speeds;
- a customer or researcher reporting a vulnerability or a data exposure;
- unexplained changes to IAM roles, firewall rules or production data.

Do not investigate on your own first. Speed matters more than certainty.

## Step 2: Report it

Page the Security Operations on-call through the pager rotation named
**secops-primary**. If there is no acknowledgement within 10 minutes, page
**secops-secondary**, then the Head of Security directly. Do not post
details in #incidents or any public channel. Security Operations opens a
private channel named `#sec-inc-<yyyymmdd>-<codename>` and invites the people
who need to be there.

Codenames are taken in order from the list of Indian rivers kept by Security
Operations, so the incident name never describes the incident.

## Step 3: Classify it

| Level | Meaning | Response target |
|---|---|---|
| SEC-1 | Confirmed breach of customer or employee personal data, or an attacker active in production | Security lead engaged within 15 minutes, 24x7 |
| SEC-2 | Likely compromise of an internal system or credential with access to production | Within 1 hour, 24x7 |
| SEC-3 | Contained issue with no evidence of data access, such as a leaked test credential | Within 4 business hours |
| SEC-4 | Policy violation or suspicious activity with no clear impact | Next business day |

The Security Operations lead sets the level and may raise or lower it as
facts come in. Any SEC-1 is also treated as a SEV1 for reliability
purposes.

## Step 4: Contain it

The goal is to stop the damage without destroying evidence.

1. **Credentials first.** Revoke and rotate any exposed secret straight
   away, following the emergency path in the Key Rotation Runbook. Do not
   wait for confirmation that it was used.
2. **Isolate, do not wipe.** Move affected hosts into the quarantine
   security group `sg-quarantine-forensic`. Never terminate an instance,
   reimage a laptop or delete a container that may be involved.
3. **Snapshot.** Take disk and memory snapshots of affected hosts before
   any change. Snapshots go to the forensic account, which only Security
   Operations can read.
4. **Block.** Add attacker IP ranges and domains to the edge block list.
   Changes to the block list during an incident skip the normal change
   approval.

For a SEC-1, the Head of Security may take any production service offline
without waiting for the CTO. The CTO is informed immediately afterwards.

## Step 5: Preserve evidence

- Keep a timeline in the incident channel, in UTC, from the first sign of
  the problem. Every action gets a line: who did what, and when.
- Export the relevant cloud audit logs and identity-provider sign-in logs to
  the forensic account in the first hour.
- Evidence from a security incident is kept for 400 days, or longer if Legal
  places a hold on it.

## Step 6: Bring in the right people

| Who | When |
|---|---|
| Head of Security | Every SEC-1 and SEC-2 |
| Legal - Privacy | Any incident that may involve personal data |
| Communications | Any incident that may become public or reach customers |
| External forensics retainer | SEC-1, or any SEC-2 the Head of Security asks for |
| Chief Executive | Every SEC-1, within 2 hours of classification |

The company has a forensics retainer with Northgate Forensics that covers
80 hours of investigation each year and a guaranteed response within 4 hours
of a call. Only the Head of Security or a deputy may activate it, using the
retainer reference NGF-RET-2291.

## Step 7: Regulatory and customer notification

Legal owns every external notification. Engineers must not contact
customers, regulators or researchers about an incident themselves.

- **CERT-In:** reportable cyber incidents must be reported within 6 hours of
  being noticed. Security Operations prepares the report and Legal files it.
- **Personal data breaches:** Legal - Privacy decides whether the Data
  Protection Board and affected individuals must be told, and prepares the
  notice.
- **Enterprise customers:** most enterprise contracts require notice of a
  confirmed security incident affecting their data within 48 hours of
  confirmation. Legal checks each affected contract.

## Step 8: Recover

Services come back only when Security Operations confirms the attacker's
access has been removed. Rebuild affected hosts from known-good images
instead of cleaning them. Watch for the same indicators for at least 30
days after recovery, with detection rules added for anything seen in the
incident.

## Step 9: Review

Every SEC-1 and SEC-2 gets a blameless post-incident review within 10
business days. The review is confidential and is stored in the Security
Operations space, not in the general postmortem folder. Actions from the
review are tracked with the label `sec-followup` and reported monthly to the
CTO until closed.

## Practice

Security Operations runs a tabletop exercise every quarter. Every engineer
on the production on-call rota must take part in at least one exercise a
year.
