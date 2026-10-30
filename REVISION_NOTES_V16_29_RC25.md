# V16.29-rc25 candidate — access, audit and navigation fixes

## Login correction in RC25

The October-2026 dialog decorator had been attached to the password verifier, so clicking LOGIN opened a dialog with that title and interrupted authentication. The decorator was removed from the verifier; a regression check now asserts the verifier has no Streamlit dialog decorator. Use this corrected RC25 ZIP.

## User-facing changes

- The Home page now has visible shortcuts to the Daily Plan, its Excel download, Daily Open / Closed, WIP, Monthly Planning KPI, and Mobile / Desktop Audit.
- The left menu has free-text function search with English and Thai aliases.
- Daily Plan download now builds an Excel workbook when its page is selected. The old button depended on a workbook created only from a different Evidence page, so it could show that no export was available.
- Due-today and due-tomorrow rows show weekday, day, month and year. Planning customer names on the Home dashboard use the original Plan-2026 source text.
- Hub login gets a signed, password-free browser ticket for 8 hours. Internal hub page links preserve it, and the embedded Daily Planner uses it. The token is a bearer ticket: do not share the signed-in URL. The mobile audit service retains its own 30-day login cookie.
- Production roles and production department views no longer expose customer names in hub tables, Daily Planner outputs without a planning/management ticket, mobile scan results, part register, and mobile work-order displays/exports.
- Desktop audit saves now use a stable submission ID, so a retry of the same unchanged audit is de-duplicated. Quantity defaults to “unknown” rather than copying the ordered quantity as an audited count. A new-observation control starts a separate audit record.
- The phone scan page explains the HTTP/HTTPS camera requirement and links directly to HTTPS camera scanning and the one-time TLS certificate download.
- Default active data storage is on the host PC's D: drive under `D:\SL_Carborundum_Planning_V16.29-rc14\CENTRAL_DATA`; database, active sources, section-status events, audit photos, QR photos, TLS files and reports now share that root. Phones access the host app over Wi-Fi; they do not access D: directly.

## Exact record paths

| Record type | Host PC path |
|---|---|
| Planning / audit / KPI database | `D:\SL_Carborundum_Planning_V16.29-rc14\CENTRAL_DATA\DATABASE\sl_planning.db` |
| Imported source workbooks | `D:\SL_Carborundum_Planning_V16.29-rc14\CENTRAL_DATA\COMPANY_DATA` |
| Daily Status by section | `D:\SL_Carborundum_Planning_V16.29-rc14\CENTRAL_DATA\DAILY_STATUS` |
| Manual WO-section status event ledger | `D:\SL_Carborundum_Planning_V16.29-rc14\CENTRAL_DATA\COMPANY_DATA\daily_status_entries.sqlite3` |
| Mobile audit photos | `D:\SL_Carborundum_Planning_V16.29-rc14\CENTRAL_DATA\PHOTOS\MOBILE_AUDITS` |
| QR scan photos | `D:\SL_Carborundum_Planning_V16.29-rc14\CENTRAL_DATA\PHOTOS\QR_SCANS` |
| Reports / exports | `D:\SL_Carborundum_Planning_V16.29-rc14\CENTRAL_DATA\REPORTS` |
| HTTPS certificate / key | `D:\SL_Carborundum_Planning_V16.29-rc14\CENTRAL_DATA\TLS` |

## Daily Plan Excel output

The Download Plan module calls `apps/daily/daily_plan_export.py` against the current calculation and includes Daily Plan, Capacity vs Plan, Planning WIP Snapshot, Delivery Risk, Issues, controlled master evidence, and section plans available for that calculation. It does not reread or modify source workbooks.

## Access controls and traceability

- Customer access is limited to administrator/planning/management roles. Production department selection masks customer fields in the hub, and an operator/supervisor mobile response does not send the customer field.
- Desktop audit writes a unique client submission ID and Bangkok timestamp. Unknown quantity remains `NULL` with an explicit flag; work-order quantity is not assumed to be a physical count.
- A physical section status event remains separate from mobile audits and from the whole-order closure rule.
- Signed hub tickets expire after 8 hours; mobile sessions expire after 30 days.

## Verification and limits

- `py_compile` passed for changed Python files.
- Focused checks passed for the signed session ticket, ticket expiry/tamper rejection, and workbook sheet generation for Daily Plan downloads.
- Mobile API tests were added for customer masking. Pytest is not installed in this cloud workspace, so the full mobile test suite was not run here.
- No factory Windows PC, actual phone, camera, Wi-Fi, firewall, TLS trust, concurrent operator group, or company-source dataset was available for this test. The program remains a release candidate pending those checks.
- Python 3.14 is not supported by the current pinned CPython wheels. Use 64-bit Python 3.12.15 (or supported 3.11/3.13); the installer refuses unsupported Python before pip.
