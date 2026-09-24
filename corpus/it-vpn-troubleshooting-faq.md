---
doc_id: it-vpn-troubleshooting-faq
title: VPN Troubleshooting FAQ
doc_kind: standalone
version: null
effective_date: 2025-07-14
status: current
superseded_by: null
applies_if: []
conflicts_with: []
sensitivity: internal
department_scope: [all]
owner: IT - Network Security
---

# VPN Troubleshooting FAQ

This page answers common questions about problems with the VPN client. The
rules for VPN use, including how long a session can stay open, are in the
VPN Access Policy. This page does not repeat them.

### The VPN client says "Unable to reach gateway". What should I do?
Check that you can open a public website. If you can, switch the client to a
different gateway or to *Automatic*. Hotel and airport networks sometimes block
VPN traffic; try a mobile hotspot instead.

### I was disconnected without doing anything. Is something wrong?
Probably not. Sessions end automatically after a period of inactivity, and
after a maximum duration, as described in the VPN Access Policy. Sign in again
to reconnect.

### My VPN keeps dropping when I sign in on another device.
The VPN Access Policy limits how many sessions you can have open at once, so
signing in on a second device can end the first. Disconnect on the device you
are not using.

### I do not receive the multi-factor prompt.
Open the authenticator app and pull down to refresh. Check that your phone has
a data connection and the correct time. If you have a new phone, follow the
How to Reset Multi-Factor Authentication guide.

### The VPN connects but internal websites do not load.
Restart your browser. If that does not help, disconnect, clear the browser
cache and connect again. If only one internal site fails, the problem is
probably with that site; raise a ticket naming it.

### Video calls are poor while I am on the VPN.
How meeting traffic is routed while you are connected is described in the
VPN Access Policy. Use the approved meeting platform for work calls, and close
other video tools while you are on the VPN.

### Can I use the VPN on my personal laptop?
Which devices may use the VPN is set in the VPN Access Policy.

### I am travelling abroad. Will the VPN work?
It depends on the country. Read the travel section of the VPN Access Policy
and contact the IT service desk before you go.

### Nothing here has helped.
Raise a ticket in the IT service portal. Include the gateway name, the time of
the failure and a screenshot of the error.
