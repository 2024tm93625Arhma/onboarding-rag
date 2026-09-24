---
doc_id: it-escalation-matrix
title: IT Incident Escalation Matrix
doc_kind: standalone
version: null
effective_date: 2026-03-02
status: current
superseded_by: null
applies_if: []
conflicts_with: []
sensitivity: internal
department_scope: [all]
owner: IT - Service Desk
---

# IT Incident Escalation Matrix

This matrix explains how IT problems are prioritised, who works on them at
each stage and when a ticket is escalated. It is for all employees, and
especially for managers and team leads who need to know when to push a problem
further. It covers incidents (something is broken) rather than requests
(something new is needed). Service requests such as new software, new laptops
or equipment returns follow the timelines in their own policies, which are
listed at the end of this page.

## Priority levels

Every incident is given a priority when it is logged. The service desk sets the
priority from two things: how many people are affected and how badly their
work is stopped.

| Priority | Description | Examples |
|---|---|---|
| P1 - Critical | A core service is down for a whole office, department or the company, or there is an active security incident. | Email down for everyone; office network outage; ransomware alert; confirmed account compromise. |
| P2 - High | A core service is down for a team, or one person cannot work at all and there is no workaround. | A team cannot reach the finance system; a laptop will not start on the day of a client presentation. |
| P3 - Medium | One person's work is disrupted but a workaround exists. | A printer queue is stuck; one application crashes but the web version works. |
| P4 - Low | A minor issue, question or cosmetic problem. | A display setting; a request for advice on an application feature. |

If you believe the priority on your ticket is wrong, reply on the ticket and
explain the business impact. The service desk will review it. Do not raise a
second ticket for the same problem.

## Support tiers

**Tier 1 - IT service desk.** Receives every ticket, call and chat. Resolves
account unlocks, multi-factor resets, application questions, basic device
faults and anything covered by a published how-to guide. Tier 1 logs the
incident, sets the priority and either resolves it or passes it to Tier 2.

**Tier 2 - Specialist teams.** End User Services handles laptop hardware,
device management and the software catalogue. Identity and Access handles
accounts, groups, single sign-on and privileged access. Network Security
handles the VPN, office Wi-Fi and firewalls. Collaboration Services handles
email, calendar, chat and meeting rooms.

**Tier 3 - Platform engineers and vendors.** Senior engineers who own a
platform, and external vendors under support contracts. Tier 3 is engaged by
Tier 2, never directly by employees.

## Escalation path

| Priority | Who is engaged first | Escalated to | Management escalation |
|---|---|---|---|
| P1 | Service desk team lead and the on-call Tier 2 engineer, immediately | Tier 3 and vendor, as soon as the cause is outside Tier 2 | IT Operations Manager is informed at once; Head of IT is informed if the outage continues past the first hour |
| P2 | Tier 1, then the relevant Tier 2 team the same working day | Tier 3 if Tier 2 cannot find the cause | IT Operations Manager if the incident is not resolved within one working day |
| P3 | Tier 1 | Tier 2 if Tier 1 cannot resolve | Service desk team lead if the ticket has had no update for three working days |
| P4 | Tier 1 | Tier 2 only if needed | Not normally escalated |

## Security incidents

Security incidents always start at P1, whatever their apparent size, until IT
Security has assessed them. They include:

- a lost or stolen laptop, phone or security key,
- a multi-factor prompt that you approved but did not start,
- an email you clicked on and then realised was phishing,
- signs that someone else has used your account.

Report these by phone to the IT service desk, not by ticket or chat, so that
the desk can act straight away. The desk will bring in IT Security. Do not try
to investigate or clean up the problem yourself, and do not turn off an
affected laptop unless IT Security asks you to.

## When and how to escalate yourself

Most tickets do not need escalating; the service desk tracks them against the
targets above. Escalate yourself only if:

- the impact has become worse since you raised the ticket,
- a deadline makes the problem more urgent than it first looked, or
- the ticket has had no update for longer than the table allows.

To escalate, reply on the ticket with the word **ESCALATE** in the first line
and explain the reason. This notifies the service desk team lead. If you get
no response within half a working day, your manager can contact the IT
Operations Manager directly, quoting the ticket number.

## Major incident communication

For a P1 incident, IT posts a notice on the status page of the intranet and in
the #it-status chat channel. The notice is updated at least every hour until
the service is restored. You do not need to raise a ticket for a problem that
is already on the status page; add a comment to the incident instead if you
have new information.

After every P1 incident, IT writes a short review covering the cause, the fix
and what will be done to prevent a repeat. Reviews are published on the IT
intranet page.

## Out of hours

The service desk phone line is staffed around the clock for P1 and security
incidents. Other tickets raised outside office hours are picked up on the next
working day.

## Service requests are different

This matrix does not set timelines for service requests. For those, see the
relevant policy:

- new or replacement laptops and the refresh schedule: Laptop Request and
  Refresh Policy,
- software that is not in the catalogue: Software Installation Policy,
- returning equipment when you leave or receive a replacement: IT Asset Return
  Policy,
- VPN session rules: VPN Access Policy,
- password requirements: Password Rules.

## Contacts

| Role | How to reach |
|---|---|
| IT service desk | IT service portal, phone, #it-help chat |
| Service desk team lead | Reply *ESCALATE* on your ticket |
| IT Operations Manager | Through your manager, quoting the ticket number |
| IT Security | Through the IT service desk phone line |
