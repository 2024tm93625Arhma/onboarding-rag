---
doc_id: it-floor-printer-setup
title: Adding the Floor Printers
doc_kind: standalone
version: null
effective_date: 2019-11-04
status: current
superseded_by: null
applies_if: []
conflicts_with: []
sensitivity: internal
department_scope: [all]
owner: IT - Infrastructure
---

# Adding the Floor Printers

The office has two network printers on the 4th floor. Each printer must be
added to your desktop once before you can print to it.

## The printers
| Printer name | Location | Type |
|---|---|---|
| `PRN-4F-EAST` | Near the Banyan meeting room | Black and white, double-sided |
| `PRN-4F-WEST` | Next to the pantry | Colour, A4 and A3 |

Use `PRN-4F-EAST` for everyday printing. Colour printing on
`PRN-4F-WEST` is for client documents only.

## Adding a printer (Windows)
1. Open *Control Panel* and choose *Devices and Printers*.
2. Click *Add a printer*, then *The printer that I want isn't listed*.
3. Choose *Add a printer using a TCP/IP address or hostname*.
4. Enter the address from the table below and click *Next*.
5. When asked for a driver, choose *Have Disk* and browse to
   `\\teamvault\public\drivers\printers`.
6. Print a test page to check it works.

| Printer | IP address |
|---|---|
| `PRN-4F-EAST` | 10.10.4.21 |
| `PRN-4F-WEST` | 10.10.4.22 |

## Printing confidential documents
Printed pages come out straight away, so collect them at once. For
confidential documents, stand at the printer while the job prints.

## Paper, toner and jams
Paper is in the cupboard under each printer. For toner or a jam you cannot
clear, raise a HelpLine ticket with the printer name.
