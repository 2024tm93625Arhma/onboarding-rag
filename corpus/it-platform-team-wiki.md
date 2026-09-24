---
doc_id: it-platform-team-wiki
title: Platform Team Wiki - Remote Access Notes
doc_kind: standalone
version: null
effective_date: 2024-05-01
status: current
superseded_by: null
applies_if: []
conflicts_with: [it-vpn-access-v2]
sensitivity: internal
department_scope: [Engineering]
owner: IT - Network Security
---

# Platform Team Wiki - Remote Access Notes

This page collects what the platform team needs to know about working on
internal systems from outside the office. Edit it if something is out of
date.

## Getting connected
Install the VPN client from the software catalogue and sign in with your
work account. You will get a multi-factor prompt on your phone the first
time you connect each day.

## Which gateway to use
Pick the gateway closest to you. The *eng* gateway gives access to the build
servers and staging clusters; the *corp* gateway is enough for email, chat
and the intranet. Only use the *eng* gateway when you need it.

## Idle disconnects
The VPN drops your session after 60 minutes with no network activity. If you
leave a long-running SSH session open, run it inside `tmux` or `screen` so it
survives the disconnect, and reconnect when you are back.

## Split tunnelling
Split tunnelling is off. All traffic goes through the VPN while you are
connected, so large personal downloads will be slow and may be blocked.

## Known issues
- Hotel and airport Wi-Fi sometimes blocks the VPN port. Use your phone's
  hotspot instead.
- If the client hangs on *Connecting*, quit it fully and start it again
  before raising a ticket.

## Contacts
Post in the platform team channel first. If the VPN is down for more than
one person, raise a priority ticket with Network Security.
