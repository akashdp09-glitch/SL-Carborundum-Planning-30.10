SL CARBORUNDUM SMART FACTORY CENTER V14

DESIGN PRINCIPLE
ONE upload location: Home -> Active Files / Upload.
All planners read the same central copies. Do not upload Plan-2026 or Firing Plan again inside Daily/Firing/Capacity.

INITIAL USERS (created by Mobile service on a fresh database)
admin / admin123
planning / planning123
supervisor / supervisor123
operator / operator123
management / management123
Change passwords after first controlled deployment.

TEST / NEW REQUEST REFERENCE STUDIED
File studied: สรุปทบทวน38A400P4VB04 80X25X7 Q26-009 - ผลิตทดแทน - ครั้งที่2.xlsx
First sheet Q26-009 contains a design/review request rather than a normal Plan-2026 row.
Important evidence found:
- Customer: Nordencent (America)
- Document: Q26-009; Test no. 2
- Reference WO: P005-110826
- Request: 38A400P7VB0400, 80X25X7 mm, 300 pcs
- Material signal: WA400 / Bond B04
- Pressing machine: H10
- Firing: dry 4 days; Program 2
- Finishing: cutting to required size
- Packing instructions and packaging-material codes are included.
V14 New Request Plan therefore accepts incomplete requests, reads the first sheet as evidence, marks missing values TO CONFIRM, and creates a provisional planning record instead of failing.

PACKAGING
Packaging std_akash.xlsx was studied as HISTORICAL/REFERENCE FORMAT only.
It includes customer/product/item based packaging planning and historical usage-style information.
It is NOT the current packaging master.
Authoritative source in V14:
Packaging Standard — CURRENT monthly file (1.มาตรฐานการบรรจุ-1.xlsx)
Upload the newest monthly file once in Active Files / Upload. It remains active until replaced.
Same-size packaging substitution remains available for unmatched items, with manual Include/Exclude control.

QR
The uploaded ALL_WORK_ORDER_QR_20260928_003556.xlsx contained 3,428 existing Work Orders.
Those WO numbers are seeded into V14's QR registry.
Generate QR creates labels ONLY for new WO numbers not already in the registry.
One WO = one persistent QR identity.

AUDIT / PHYSICAL VERIFICATION
Plan-2026 and Physical Audit are kept as two separate truths.
The Audit page compares Plan-2026 vs latest physical audit.
It can create/edit/download Daily Status from the comparison.
It can create a NEW Plan-2026 reconciliation copy for download.
The original uploaded Plan-2026 is never edited.

DATE/TIME
V14 displays the computer/server local date and time. It is not hard-coded.
This avoids false history dates. Old bundled activity database was removed from this package.

IMPORTANT
A web browser does not provide the original Windows folder path of an uploaded file.
V14 records original filename, Excel document modified time when available, upload page, user, registration time and the central stored location.

FIRING
Firing Planner automatically reads central Plan-2026 and central latest issued Firing Plan.
There is no duplicate Firing upload control inside Firing or Capacity.
The first firing plan can be created without rollover history; after it is created, it becomes the shared latest Firing Plan automatically.

MOBILE
Mobile is intentionally smaller: operator scan/status/problem/audit focus.
MPS/MRP links are removed.
English / Thai / Burmese remain available.
