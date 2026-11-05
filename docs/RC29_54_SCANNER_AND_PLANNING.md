# RC29.54 — scanner, visible functions and drying handoff review

5 November 2026 (Asia/Bangkok). This is a **review candidate**, not a claim that the entire legacy application is factory-validated.

## What changed

- A bilingual, searchable **All functions** directory makes the desktop destinations visible: Daily, Firing, MPS, MRP, capacity, stock, packaging, WIP, audits/register, QR labels, recovery, KPI/production analysis, sources, history, accounts and drying confirmation. Only the chosen destination renders its application. The desktop section-entry page no longer requests full shared-plan analysis before displaying its entry controls.
- One **USB / Scan** screen supports exact work-order lookup, section OPEN/CLOSED, physical audit, part history and an expandable production-event panel. `/operator` now redirects to that screen instead of presenting another competing form. Camera/photo/search/unidentified workflows remain available.
- Owner's scanner: **B2D21, wired USB**. Implemented and browser-tested as keyboard/HID text input with Enter or Find. No unverified manufacturer setup barcode, driver or physical-device certification is supplied. A scanner that is not configured as a keyboard must be configured using its own verified manual.
- Stable `SLWO:` codes, plain WOs and historical URL labels resolve through bounded indexed exact database lookups. The old scan endpoint fetched every WO and could reopen the Plan workbook for each scan. Partial/ambiguous identities no longer silently select a first suggestion. A `WO-...` identity is preserved rather than stripped as a display prefix.
- Section saves and production-event saves retain submission IDs. Lost acknowledgements retry the same committed entry. Conflicting reuse is rejected. Browser drafts and pending requests are kept per signed-in username; validation errors allow correction. Success is shown only after commit. Source/user/time/event ID remain inspectable; section closures, audits and final packed quantities remain separate.
- Production events validate the station, actual completion quantity, hold/rework reason and actor; event and audit-log writes commit together. A forming/mixing/etc. COMPLETE does not become packed output or whole-order completion. Partial production does not mark a route step fully complete. Existing source-based department KPI actual output still uses `Pack จ่าย` only; scanner events are not added to that workbook KPI.
- Added missing `production` and section logins: preparation, mixing, forming, firing, grinding, cutting, packing, qc, warehouse, dispatch. Defaults follow `username123`; the existing five accounts remain. Desktop/mobile share the same users table. Changed/inactive existing accounts are not reset. Account defaults and details are in `user details.txt`; the app account register does not reveal hashes/passwords. Section accounts preselect a section, not an undocumented prohibition on cross-section work.

## Planning and drying

The previous Firing handoff used a generic next-day forming release. The current handoff reads the active capacity workbook's `Lead Time` sheet and retains source cells and SHA-256. Daily now also attaches the active workbook's lead-time profiles to each WO instead of relying solely on a fixed transcription. Unknown product groups on active orders block the detailed build rather than silently applying group P. Closed historical rows remain retained and cannot block the active plan for missing category metadata.

The existing conservative working-day route interpretation (Mon–Sat) is explicit: ordinary group P uses Forming 2 + Oven 3 source days. The workbook does **not** resolve calendar versus working-day semantics. This remains a stated provisional interpretation. The exact-WO `P005-110826 / Q26-009` exception retains four calendar drying days plus two calendar pre-firing-check days; it is not generalized to other WOs. Sunday arrivals roll to the next scheduled working day in Daily. PB's oven bypass comes from the source.

Formed WIP/`เข้าเผา` is **not** proof that drying is complete. **Confirm drying readiness** stores actual completion, ready pieces, source, reason, actor and time. Both planners read the same evidence. It is a quantity snapshot, not additive production. A new imported WO revision invalidates the previous confirmation for planning, while retaining it in history. Confirmations never infer drying completion from kiln loading or a planned date.

Daily holds the unconfirmed portion of initial firing WIP; confirmed quantities may support the selected-day anchor. Future forming output reaches firing only after the source-backed gate. Firing retains the selected planning start and exposes missing readiness as HOLD/review; the source date is not silently rewritten. A proposed load with insufficient evidence is not execution-approved. The workbook's lack of rated drier capacity/staffing is shown as **NOT VERIFIED**. Lead time is not capacity verification.

Firing exports now include **Drying Readiness** and **Release Summary**, with a visible downloadable review CSV. Top/front views and the existing geometric packing algorithm remain available; this revision does not establish complete physical accuracy or validate every kiln/furniture configuration.

Repeated capacity reads within the Firing pipeline share a content-addressed cache; each caller gets independent copies, and changed bytes invalidate the cache. A process-local lock serializes the legacy Firing calculations because they use global settings/furniture: concurrent sessions must not overwrite one another mid-run. This does not provide a multi-server planning reservation system.

## Data and rollback

All migrations are additive: missing user rows; `drying_confirmations` and `production_submissions` tables; a WO/status index. Existing observations, events, files, source revisions and password hashes are preserved. Private `CENTRAL_DATA`, operational workbooks, SQLite databases, photos and server logs are excluded from the downloadable software ZIP. The evidence imported in RC29.53 remains in this environment's shared database; transferring to another PC requires securely carrying the existing shared data or importing the original files once.

Back up the shared root while services are stopped. Extract code to a separate folder and configure the same shared root. Never replace an existing `CENTRAL_DATA` folder with a blank one. To roll back code, stop services and select the earlier code folder while retaining the databases/backups. Earlier code ignores the new drying guards, so it must not be used to approve these revised plans.

## Verification and limits

See `RC54_*` logs for focused, mobile, browser, broader-suite, baseline-comparison, timing and engine-integrity results. The 14 failing legacy tests were reproduced on unmodified RC29.53 commit `8ac9005` in a separate checkout: retired combined-file imports, literal prior UI assertions, 8-hour versus current 30-day ticket expectation, and Windows virtual-environment path expectations. They are reported, not removed or weakened to make a green suite. The `_business_days` anchor test was corrected to the helper's documented **count** return contract and now also verifies inclusive start and Sunday exclusion.

Component timing conditions: synthetic 10,000-WO SQLite database, local warm filesystem, one process, no network/scanner hardware. Indexed exact lookup median 0.029 ms (p95 0.039 ms, 100 requests), compared with 37.031 ms for the previous full-table Python lookup (20 requests). Supplied bundled capacity workbook first parse 3.0776 s; cached-copy median 0.0022 s (10 repeats). These are component results, not end-to-end firing-plan speed or factory performance guarantees.

A real Chromium run verifies Enter lookup, durable status save/history, a deliberately lost response followed by duplicate-free retry, draft reload, mobile layout/audit destination, and the full directory/drying page. Screenshots in `docs/images/rc54` contain only synthetic examples. The Word guide includes these screenshots, bilingual instructions, account defaults, examples, storage/rollback and an on-site checklist.

Unfinished acceptance remains explicit: inherited unreviewed/mismatched engine files, the broader legacy test failures, complete physical kiln-layout acceptance, real B2D21 hardware/printing, phone camera/GPS, factory Wi-Fi and Windows startup. Do not treat this ZIP as a fully approved production release.

## Design references

Applied simple task grouping, large labelled targets, visible keyboard focus and server-confirmed status feedback. External guidance is interface guidance, not a factory rule:

- W3C, [Understanding Target Size (Minimum)](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html), public source retrieved 5 November 2026: <https://github.com/w3c/wcag/blob/main/understanding/22/target-size-minimum.html>.
- W3C, [Understanding Status Messages](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html), public source retrieved 5 November 2026: <https://github.com/w3c/wcag/blob/main/understanding/21/status-messages.html>.
- Jeff Patton's *User Story Mapping*, cited in the user's conversation, informs the workflow order (identify → confirm → record → review receipt). The book was not supplied/read here; no claim of reproducing its contents is made.
