# AGENTS.md - SL Carborundum Planning

Full requirements: `PROJECT_REQUIREMENTS.md` (IDs R1-R12). Progress and evidence: `DEVELOPMENT_STATUS.md`. Read both before changing features.
Factory approval (2026-10-04): the owner approved the supplied technical documents, capacity standards, process instructions and explicit requirements as factory rules (`FACTORY_APPROVAL.md`, `knowledge/approved_rules.json`). Apply them in planning, validation, analysis and bilingual help. Stock, WIP, plans and forecasts are dated evidence, never constants. If approved sources conflict, show the exact entries and ask only the decision needed; never choose silently.

## Non-negotiables
- Preserve working functions and production data. Migrations must be additive, idempotent and have rollback notes. Never delete or overwrite `CENTRAL_DATA` / `SL_SHARED_ROOT` data.
- Never invent data, rules, BOMs, locations, stock or knowledge content. `knowledge/knowledge_base.sqlite` was deliberately excluded; report what is missing instead of fabricating it. Cloud tests use only clearly labelled `SYNTHETIC` records in `.cloud-test-data/`.
- Never call a schedule "feasible", or the system "production ready", without evidence. State test conditions for any timing or load claim.
- Cloud tests do not verify a real phone camera, GPS, factory Wi-Fi or Windows `.bat` startup; list them as on-device tests.

## Product scope
- Desktop (Streamlit hub, `apps/daily`, `apps/firing`, `suite/`): all planning, analysis, QR generation, audit review, knowledge, imports, exports, admin.
- Mobile (`apps/mobile`, FastAPI): operator workflows - scan/search, part status, physical audit, photos, identified/unidentified parts and submission review. It may also show compact read-only WIP summary graphs from active Production WIP sources plus separately labelled work-order/audit database indicators. No planning engines or workbook editing on mobile.
- Desktop and mobile share one record store. The server enforces permissions by role, never by screen size.

## Rules for audit / tracking code
- Physical audit observations are separate from production `events`; repeated observations never add stock or production.
- Unknown quantity is `NULL` with an explicit flag, never 0. Never invent a WO number; unidentified parts get a generated temporary ID that is preserved after linking.
- A save is successful only after the DB commit (and photo file) succeeded. Writes carry a client submission id so retries are idempotent.
- Ambiguous scans/searches must be confirmed by the operator. Keep original submission time and server receipt time; show Asia/Bangkok.

## Sources and planning rules
- KPI = two separate workbooks (section plan-vs-actual; delivery/warehouse). Daily Status = one workbook per section. Re-importing an unchanged file must not duplicate records.
- Section closure never closes the whole WO. Planned vs confirmed actual dates are distinct. One shared backorder calculation for every entry point.
- New-part plans start from today (Asia/Bangkok), never inherit old dates, and are labelled provisional until constraints are verified.
- Approved factory rules are separate from external guidance and from dated stock/forecast/production data.

## Capacity and planning modules (approved rules CAP-1..6)
- `suite/capacity.py`: every capacity value keeps its source unit, time basis and sheet/cell. Never add tonnes, pieces, mill counts or persons. A mill count is not batches per day. Tonne->kg only by the documented conversion; pieces->kg only with a part weight at the matching stage. Missing inputs go to `gaps`, plans are PROVISIONAL/BLOCKED, never "confirmed feasible".
- `suite/closure_rules.py`: whole order closed = EU or FC; section closure is informational; backorder = open, remaining > 0, due before today (Bangkok).
- `suite/source_manager.py`: import once, sha256 dedupe, append-only revisions, two Production KPI sources plus a separate owner-approved Planning KPI reference, and one Daily Status per section; sheet roles are found by header.
- Knowledge: PDF/PPTX extraction register `knowledge/DOCUMENT_EXTRACTION.json` (OCR flagged UNVERIFIED); `knowledge_base.sqlite` is restored from the existing installation, not invented.

## Environment and checks
- Cloud setup: `.cursor/environment.json`, `scripts/cloud/` (see its README). Run `bash scripts/cloud/validate.sh` and `pytest apps/mobile/tests` before committing.
- Release checks (`VERIFY_RELEASE.py`) must pass; change a pinned file only through `scripts/release/controlled_change.py` with a reason and an evidence test, never by editing a checksum (`docs/RELEASE_INTEGRITY.md`). Open items are listed in `DEVELOPMENT_STATUS.md` and `docs/LIMITATIONS.md`; do not hide them.
- Build the Windows ZIP with `python scripts/release/build_release.py --verify` on a clean committed tree; never include live data or secrets.
- Work on the current working branch; commit one reviewable change per stage step; update `DEVELOPMENT_STATUS.md` with every change.
