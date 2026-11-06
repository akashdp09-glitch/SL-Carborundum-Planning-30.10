# RC29.57 — current review

See [RC29.57 notes](docs/RC29_57_REVIEW_NOTES.md) and the RC57 test logs. Revised transition loads now feed main operational output; exact older factory-file acceptance remains outstanding. Existing shared data is preserved.

# Remaining limitations (concise)

## RC29.54 current review limits — 5 November 2026

See `RC29_54_SCANNER_AND_PLANNING.md` for changes and exact evidence. B2D21 support is tested as USB keyboard text, not on the physical device. Firing still has three inherited integrity failures (`sl_daily_engine_v3_22_from_v17.py`, `fast_stage4_v15.py`, `firing_engine_desktop_v2.py`). Daily hash/syntax checks pass with pending code reviews. Fourteen broader inherited tests fail on both this version and unchanged RC29.53; they were not hidden. The cloud validation script is absent from the supplied tree.

Drying day basis is not explicit in the workbook; the existing working-day interpretation remains provisional except for the sourced exact-WO calendar exception. No rated drier capacity/staffing is supplied. Actual drying confirmations are invalidated for planning after a revised WO import and retained in history. Complete geometric kiln/furniture validation, on-site scanner/printing, real phone camera/GPS, factory Wi-Fi and Windows startup remain unverified. Component lookup/capacity timings are not an end-to-end firing benchmark.

**RC29.53 (4 November 2026):** Department KPI persistence and the new English
production-analysis page supersede the RC29.52 manual-only workflow. Read
`RC29_53_PRODUCTION_ANALYSIS.md` and the current `RC53_*_TESTS.txt` first. Private
evidence data remains separate from the code ZIP; inherited engine acceptance
failures and on-device checks below remain unresolved.

**Current RC29.52 review candidate:** see `RC29_52_REVIEW_NOTES.md` first.
The uploaded engine integrity checks currently fail; historical pass statements
below describe older builds. This candidate is not ready for factory deployment.

## Not verified (needs the factory)
* Real phone camera scanning, photo capture and gallery, HEIC from iPhones, GPS indoors, factory Wi-Fi behaviour: see `docs/ON_PHONE_CHECKLIST.md`.
* Windows installation and `.bat` start-up, shared-folder permissions, and an update on the live installation. The ZIP has not been installed on Windows.
* Several real operators at once (only simulated threads were tested).
* The software is **not** declared production ready, and no schedule is labelled confirmed feasible.

## Knowledge database
* `knowledge/knowledge_base.sqlite` is not in the package. **Restore it from the existing installation** (a rebuild from the supplied Excel files is only partial). See `docs/KNOWLEDGE_DATABASE.md`.
* PDF/PowerPoint knowledge lives in `knowledge/DOCUMENT_EXTRACTION.json`. OCR pages below 70 mean confidence or with fewer than 6 words are flagged (30 of 72 grinding pages, 41 of 138 slide units). Extraction is not understanding; diagrams are not interpreted beyond matched call-outs.
* `ตัวอย่างการกรอกข้อมูล.xlsx` (referred to by the work-order-reading deck) was not supplied.
* `decode_spec` understands only 150 of 3,509 SPEC strings; 337 of 3,509 plan WO codes do not follow the deck's factory-number format. These are reported, not guessed.

## Capacity and planning
* Source units are kept (tonnes, pieces, mill counts, persons, days). Gaps still open: mixing cycle time and batches per mill per day; cooling/unloading time and per-kiln loading limits; shifts for sections other than Forming; drier capacities; the working calendar and holidays; part weights per stage for most parts.
* Conflicts in the approved sources, shown with cells (`suite/capacity.py`): mixing tonnes/month versus mills/day x kg/day; Forming Cap./Hr. versus the 3-hour column on rows 28, 33, 38, 40, 41, 42, 43; Resin-row firing lead times for group T (C7) and M (G7). Rounding-level differences are listed but not blocking.
* "Tonne" is read as the metric tonne (1 t = 1,000 kg) pending owner confirmation.
* Forecast demand is netted against firm orders of the same product and month; this is an assumption awaiting confirmation.
* No approved manual plan was supplied, so the planner has no acceptance example. The Daily Planner's own capacity engine is unchanged.
* New-part plans are PROVISIONAL or BLOCKED whenever any input is missing; they are scenarios, not commitments.

## Mobile and permissions
* Permission matrix is proposed in `docs/PERMISSION_MATRIX.md`; Every signed-in role may record, correct and link. The anonymous hub default stays read-only. Edits keep old and new values with user, time and reason.
* Photos upload at original size (no client-side resize). File names carry work order (or temporary ID), location and date-time.
* Audit observations are never added into stock or production totals.
* Locations (buildings/racks/bins) must be entered by an administrator; none were invented.

## Release process
* 10 earlier controlled changes (7 daily, 3 firing) are hash-pinned but their reasons are not documented in the supplied files; they show as PENDING REVIEW. The four files that failed the checks are resolved and documented (`docs/RELEASE_INTEGRITY.md`).
* Register filter cost grows with total audit rows (about 85 ms at 20,000 rows); larger volumes are untested.
