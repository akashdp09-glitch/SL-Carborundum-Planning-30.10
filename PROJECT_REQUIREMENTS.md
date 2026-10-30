# SL Carborundum Software - Master Requirements

Source: owner's "UPDATED MASTER REQUIREMENTS" message of 2026-10-04. These clarify the scope of the
current project. Wording is kept close to the original; requirement IDs (`R<section>.<n>`) were added
so that `DEVELOPMENT_STATUS.md` can trace implementation and verification. Do not weaken a requirement
without the owner's written approval.

Standing rules: inspect existing features first; preserve working functions and production data;
never invent data, rules or missing source content; never claim "feasible", "production ready" or
"zero errors" without evidence.

## 1. Desktop and mobile scope

**Desktop** provides all functions: daily planning, firing planning, MPS, MRP, backorders, capacity,
stock, forecast, KPI, open/closed analysis, new-project planning, QR generation, WIP tracking, audit
review, knowledge, imports, exports and administration.

**Mobile** provides only the operator workflows:
- R1.1 Scan QR or search for a part / work order.
- R1.2 View part status, quantity, location, photos and history.
- R1.3 Record a physical WIP audit or status update.
- R1.4 Capture / upload photographs.
- R1.5 Record identified or unidentified parts.
- R1.6 Review submission success and pending submissions.

- R1.7 Do not load full planning dashboards, Excel processing or firing planners on mobile. A compact read-only WIP summary/analysis is allowed when it uses the same active Production WIP source files as desktop and clearly separates those figures from mobile audit/order-balance records.
- R1.8 Large buttons, minimal typing, fast workflow.
- R1.9 Desktop and mobile share the same underlying records.
- R1.10 Permissions are enforced by the server, not by screen size.

## 2. Mobile audit with a work order or QR

Flow: scan/search -> confirm part -> enter status and quantity -> confirm location -> take photo if required -> submit.

- R2.1 After scanning, show the matching work order and part details for confirmation. Never silently select an ambiguous match.
- R2.2 Support live camera QR scanning.
- R2.3 Support manual work-order / part search if scanning is unavailable.
- R2.4 Support photo upload as an additional fallback.
- R2.5 Support several observations for one work order (parts split across locations, batches or processes).
- R2.6 Auto-fill known information from the shared source; do not repeatedly ask for existing details.

## 3. Parts without a work order or QR

- R3.1 Allow submission when no work order or QR exists, via an "Unidentified / No work order" option.
- R3.2 Generate a unique temporary tracking ID automatically.
- R3.3 Capture: photograph; description and visible markings if known; quantity and unit, or an explicit "quantity unknown"; physical location; current process/status including "unknown"; operator, timestamp, notes.
- R3.4 Do not invent a work-order number. Do not treat unknown quantity as zero.
- R3.5 An authorized desktop user can later identify the part and link it to a real part / work order. Preserve the temporary ID, original evidence and complete reconciliation history.
- R3.6 Prevent double counting after linking.
- R3.7 A QR label can be generated for the temporary ID.

## 4. Shared part register and detail format

- R4.1 Same records on desktop and mobile.
- R4.2 Register fields: Tracking ID | WO if known | Part code/specification | Description | Process/section | Status | Quantity | Unit | Location | Photo thumbnail | Last observed time | Submitted by | Identification/verification state.
- R4.3 Filters: work order, part, customer where known, section, status, location, date, unidentified parts.
- R4.4 Opening a record shows photographs, observations, movements, corrections and source evidence.
- R4.5 Desktop: full filterable table with Excel/CSV export. Mobile: readable cards and a compact detail page.
- R4.6 Physical audit observations stay distinct from production transactions. Repeated observations must not add stock or count production twice.
- R4.7 Show conflicting observations for review; never silently overwrite.

## 5. Locations, photographs and traceability

- R5.1 Structured locations: factory/building -> section -> machine/rack/bin or other configured location, plus optional notes.
- R5.2 Offer GPS capture with permission; do not rely on GPS for indoor racks; record unavailable/denied GPS honestly; allow manual selection.
- R5.3 Link every photograph to its audit/event and tracking ID.
- R5.4 Keep original submission time and server receipt time. Display factory dates/times in Asia/Bangkok.
- R5.5 Files & Traceability page showing the actual configured storage locations for: operational database; audit and status records; part photographs and retained scan images; QR labels and encoded content; original imported files and archived revisions; reports, exports and backups.
- R5.6 For source imports retain filename, hash, import time, uploader, source revision, sheet and row/cell references.
- R5.7 Do not claim to know the uploader's original computer folder when the browser does not provide it.
- R5.8 Distinguish browser-downloaded files from server-saved files.

## 6. QR generation and scanning

- R6.1 Easy-to-find desktop QR generator for: one WO, selected WOs, bulk WOs, temporary tracking IDs.
- R6.2 Printable labels include the human-readable ID and useful part information.
- R6.3 Stable identities; never hard-code a changing IP address. Explain and configure two cases: (a) identity QR read inside the operator application; (b) stable HTTPS-link QR opened by a normal phone scanner.
- R6.4 A normal phone camera opening the website does not prove the in-app Scan button works. Test both separately.
- R6.5 Clear camera-permission and connection errors. Stop the camera when leaving the scanner.
- R6.6 Prevent duplicate submissions from repeated scans, double taps and network retries.

## 7. Speed, reliability and navigation

Speed is the first priority; operators handle thousands of work orders per day.

- R7.1 Render only the selected desktop page and necessary data. Simple grouped navigation, expandable sections, dialogs where helpful. Preserve planning drafts when navigating.
- R7.2 Avoid repeated workbook parsing, duplicate database imports, full-table mobile downloads and unnecessary photo loading. Use indexed lookups, pagination and thumbnails.
- R7.3 Show success only after the server has durably saved the record. Preserve entered information if submission fails. Show pending/failed submissions clearly with safe retry. Never silently lose photos or quantities.
- R7.4 Measure lookup, page-load and submission timings with representative volumes and concurrent users. State test conditions. Do not claim zero errors or production readiness without evidence.

## 8. One shared source manager

- R8.1 Upload a source once; reuse it in Main page, Daily Planner, Firing Planner, QR, audit and reports.
- R8.2 KPI uses TWO distinct workbooks: (a) section performance / plan versus actual; (b) delivery / warehouse performance.
- R8.3 Daily Status uses a separate workbook for EACH SECTION. Do not replace with one generic file.
- R8.4 Show active source filename, revision, import time and health.
- R8.5 Re-importing an unchanged file must not duplicate records. New revisions refresh dependent results consistently.

## 9. Consistent analysis and closure rules

- R9.1 All backorder entry points use the same calculation, source revision, date basis and filters.
- R9.2 Section completion (including Preparation closure) must not mark the entire work order closed.
- R9.3 Distinguish planned closure dates from confirmed actual closure. Flag inconsistent or future actual dates.
- R9.4 Support the September open/closed workbook and analysis. Keep distinct: sales requests; work orders issued; reported unissued items; production item closures.
- R9.5 Verify totals from the actual workbook; earlier chat totals are not evidence.
- R9.6 Category filters, daily charts and source references.

## 10. Intelligent new-part and project planning

- R10.1 Use today's date in Asia/Bangkok. Do not copy old scheduled dates from a previous work order.
- R10.2 Historical parts may suggest technical information; new dates come from: approved process route and dependencies; material availability and reservations; machine/section capacity and bookings; staffing, shifts, holidays, calendars; setup, production, drying, firing and cooling constraints; quantities, units and confirmed delivery dates.
- R10.3 Purchase lead time is not production duration. No double counting of stock, confirmed receipts or demand. Forecast is distinct from firm orders.
- R10.4 With limited information: produce an explicitly provisional plan, list assumptions, show missing constraints, ask only necessary questions. Never label an unverified schedule "feasible".
- R10.5 Compare with the owner's approved manual plans when supplied. Explain bottlenecks, shortages, lateness and alternatives.
- R10.6 Save scenarios; provide traceable schedule/Gantt exports.

## 11. Bilingual knowledge and F1 help

- R11.1 Searchable Thai and English knowledge/help, via F1 on desktop and a visible Help button.
- R11.2 Retain knowledge from supplied manuals, presentations, workbooks and approved instructions.
- R11.3 Cover part/code interpretation, materials, processes, defects, packaging, capacity, planning rules, QR, audit and software use.
- R11.4 Show source document, page/sheet and revision where available. Thai selection must never produce empty help.
- R11.5 Approved rules are used consistently in calculations; a help article alone is not implementation.
- R11.6 External internet guidance stays distinguishable from approved factory rules and is never turned into policy without review.
- R11.7 The large knowledge database was excluded from the upload: report missing evidence, request sources, never invent contents.

## 12. Delivery and acceptance

Stages: **A** desktop/mobile scope and shared audit record model; **B** mobile identified/unidentified capture and QR workflow; **C** shared sources, consistent reports, speed; **D** planning accuracy and bilingual knowledge.

For each stage: record changed files and DB migrations; preserve existing data and give rollback instructions; run meaningful tests and show results; provide a preview if available; update requirements/progress documents; commit a reviewable change on the working branch.

Acceptance examples:
1. Scan an existing WO and submit quantity/location/photo.
2. Submit a photographed part with no WO or QR.
3. Find the same record on desktop and mobile.
4. Link an unidentified part later without losing history.
5. Retry a submission without duplicate events or quantity.
6. Verify two KPI sources and section-specific Daily Status.
7. Obtain matching backorder results across entry points.
8. Produce a new plan without inherited historical dates.
9. Retrieve useful equivalent Thai and English help.

Cloud layout tests do not verify a real phone camera, GPS, factory Wi-Fi or Windows startup. The remaining on-device tests must be identified clearly (see `DEVELOPMENT_STATUS.md`).


## 13. Factory approval and delivery requirements (owner message of 2026-10-04, turn 4)

Summarised; the full approval record is `FACTORY_APPROVAL.md` and the machine-readable rules are `knowledge/approved_rules.json`.

- R13.1 The supplied technical documents, capacity standards, process instructions and the owner's explicit requirements are approved factory rules. Stock, WIP, plans and forecasts are dated evidence, not constants. Conflicts between approved sources are shown with exact entries and one decision question.
- R13.2 Capacity: keep each resource's source unit and time basis; never add tonnes, pieces and mill counts; a mill count is not batches per day; convert tonnes to kg and pieces to weight only with documented conversions; cite file, sheet/cell, unit, period and assumptions; apply constraints across the whole route; report gaps and give provisional scenarios, never "confirmed feasible".
- R13.3 Shared Source Manager: import once, reuse everywhere, two KPI sources, Daily Status per section, no duplicates, originals and revisions kept, active source/timestamp/affected modules shown, Plan sheet roles determined.
- R13.4 Reporting and planning: one closure/backorder rule; keep sales requests, issued WOs and production closures separate; MPS/MRP/new-part planning from today's Bangkok date with reservations, bookings, firm vs forecast demand, drafts/scenarios and traceable exports.
- R13.5 Knowledge: OCR image-only PDF pages and PowerPoint call-outs with page/slide references and review flags; bilingual F1 help; approved rules implemented in calculations; missing sources recorded, not invented.
- R13.6 Permissions: no unexplained role restriction; documented final matrix.
- R13.7 Release: investigate and resolve the failing release checks through the controlled-change process; reproducible cloud environment.
- R13.8 Verify and deliver: stage regression tests, concurrency/retry/quantity/upload/shared-source tests, real QR images, on-phone checklist, user-facing performance; versioned Windows ZIP without live data/secrets, install/update/storage/migration/backup/rollback docs, exact dependency versions, test results, limitations, version manifest with the exact commit; state whether the knowledge database is restored or rebuilt (restored). Do not merge or replace the live installation.
