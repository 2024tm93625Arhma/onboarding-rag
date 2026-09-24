---
doc_id: it-vpn-access-v2
title: VPN Access Policy
version: 2
effective_date: 2025-06-01
status: current
superseded_by: null
applies_if: []
conflicts_with: []
sensitivity: internal
department_scope: [all]
owner: IT - Network Security
---

# VPN Access Policy (v2)

## Purpose
This policy describes how employees connect to company systems from outside
the office using the virtual private network (VPN), and the security controls
that apply to VPN sessions.
It replaces v1 for all employees.

## Who needs the VPN
The VPN is required to reach internal systems such as the intranet, internal
code repositories, finance systems and the HR system when working from outside
a company office. Cloud applications that use single sign-on, such as email and
chat, do not need the VPN.

## Getting access
VPN access is enabled automatically for all employees when their account is
created. The VPN client is pre-installed on company laptops. Access from
personal devices is not permitted.

## Connecting
1. Open the VPN client from the system tray or menu bar.
2. Select the nearest gateway, or leave the client on "Automatic".
3. Sign in with your company credentials.
4. Approve the multi-factor authentication prompt on your phone.

## Session rules
- A VPN session that has no network activity for **30 minutes** is
  disconnected automatically and the employee must sign in again.
- Every session, active or not, is ended after 12 hours and requires a fresh
  sign-in with multi-factor authentication.
- Only one VPN session per user may be open at any time. Signing in on a
  second device ends the first session.

## Split tunnelling
Split tunnelling is disabled. While connected, all internet traffic from the
laptop is routed through the company network and subject to the same web
filtering as in the office. Video calls on the approved meeting platform are
excluded from this routing to preserve call quality.

## Acceptable use
The VPN is for company work only. Streaming, torrenting or other heavy personal
use over the VPN is not permitted. Network traffic over the VPN is logged and
may be reviewed by IT Security.

## Travelling abroad
Employees who need to connect from outside India must inform the IT service
desk at least one week before travel. Some countries restrict VPN use, and IT
will advise on what is allowed. Connecting from a country on the company's
restricted list is blocked.

## Troubleshooting
If the VPN will not connect:
- check that the laptop has a working internet connection,
- restart the VPN client and try a different gateway,
- confirm that your password has not expired,
- make sure the date and time on the laptop are correct.

If the problem persists, raise a ticket in the IT service portal or call the IT
service desk. Include the gateway name and a screenshot of any error message.

## Security incidents
If you suspect that someone else has used your VPN account, or you approve a
multi-factor prompt that you did not start, contact IT Security immediately and
change your password.

## Applicability
This policy applies to all employees. It replaces v1 in full.

## Contact
Raise VPN questions through the IT service portal or the IT service desk.
