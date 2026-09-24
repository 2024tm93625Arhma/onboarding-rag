---
doc_id: eng-key-rotation-runbook
title: Key and Secret Rotation Runbook
doc_kind: standalone
version: null
effective_date: 2026-06-01
status: current
superseded_by: null
applies_if: []
conflicts_with: []
sensitivity: restricted
department_scope: [Engineering]
owner: Engineering - Platform
---

# Key and Secret Rotation Runbook

**Classification: Restricted. Engineering only. Contains secret store paths
and approval rules.**

This runbook covers scheduled and emergency rotation of production
encryption keys and service secrets. All production secrets live in the
central secrets store under the path `kv/prod/<service>/<secret-name>`.
Nobody may keep a production secret anywhere else, including in CI
variables, except the short-lived tokens that the store issues itself.

## Rotation schedule

| Secret type | Rotation interval | How |
|---|---|---|
| Cloud KMS customer-managed keys | Every 365 days | Automatic; old key versions kept for decryption |
| Database service-account credentials | Every 90 days | Scheduled job `rotate-db-creds`, dual-running for 24 hours |
| Third-party API keys | Every 180 days | Manual, by the owning team |
| Internal service-to-service tokens | Every 7 hours | Automatic, issued by the secrets store |
| TLS certificates | 90-day certificates renewed automatically 20 days before expiry | ACME client |
| SSH certificate authority signing key | Every 2 years | Manual, Platform only |
| Payment gateway signing keys | Every 12 months, in the first week of March | Manual, with the gateway provider |

The Platform team publishes the rotation calendar in the #platform-rotations
channel each month.

## Dual control

Rotation of the KMS root keys, the SSH certificate authority key and the
payment gateway keys needs two people from the Platform Security group:
one to perform the change and one to approve it in the change record. The
same person cannot do both. The approver must be at G5 or above.

## Scheduled rotation steps

1. Create the new secret version in the store. Do not delete the old one.
2. Roll out services so they read the new version. Check that the error
   rate on the service dashboard does not rise.
3. After 24 hours with no errors, disable the old version.
4. After a further 7 days, destroy the old version, except for KMS keys,
   whose old versions are kept until all data encrypted with them has
   expired under the Records Retention Schedule.

## Emergency rotation

If a secret may have been exposed, rotate it immediately and open a
security incident as described in the Security Incident Runbook. Emergency
rotation must be complete within 4 hours of the exposure being reported,
and the old version is disabled straight away, without the 24-hour overlap.
Accept the risk of a short outage rather than keep a leaked secret alive.

## Break-glass access

The break-glass credentials for the secrets store are split into three
shares held by the CTO, the Head of Security and the Head of Platform. Any
two shares open the store. Every use is reviewed by the Head of Security
within one business day.
