---
doc_id: it-remote-desktop-gateway-howto
title: Working Remotely with the Remote Desktop Gateway
doc_kind: standalone
version: null
effective_date: 2019-09-16
status: current
superseded_by: null
applies_if: []
conflicts_with: []
sensitivity: internal
department_scope: [all]
owner: IT - Infrastructure
---

# Working Remotely with the Remote Desktop Gateway

When you are away from the office, you work by connecting to your office
desktop PC through the Remote Desktop Gateway. Your files, applications and
network drives stay on the office PC; your home computer only shows its
screen.

## Before you can connect
1. Your manager approves remote access in a HelpLine ticket.
2. IT issues you an RSA hardware token. Collect it from the IT room on the
   4th floor and sign the token register.
3. Leave your office desktop switched on and logged out. Do not shut it down
   when you leave, or you will not be able to reach it.

## Connecting
1. On your home computer, open *Remote Desktop Connection*.
2. Click *Show Options* and enter your desktop's computer name. It is on the
   asset sticker on the front of the PC, for example `BLR-DT-0217`.
3. On the *Advanced* tab, click *Settings* and enter the gateway address
   `rdgw.corp.local`.
4. Click *Connect*. When asked, enter your Windows username and password,
   followed by the six-digit code shown on your RSA token.

## Tips
- Use a wired connection if you can; Wi-Fi makes the screen slow to update.
- Printing from home is not supported. Save the file and print it in the
  office.
- Do not copy company files to your home computer.

## If something goes wrong
- **"Remote computer cannot be found":** your desktop is switched off. Ask a
  colleague in the office to turn it on, or call the IT room.
- **Token code rejected:** wait for the next code and try again. If it still
  fails, the token may be out of sync; call IT.
- **Lost token:** report it to IT immediately so it can be disabled.
