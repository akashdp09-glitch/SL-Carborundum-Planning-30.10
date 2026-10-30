# Factory approval record

**Recorded:** 2026-10-04 (Asia/Bangkok) from the owner's instruction in the development conversation (PR #1).

> "I approve the supplied technical documents, capacity standards, process instructions and my explicit requirements as factory rules."

## Scope
* The documents and workbooks supplied in this repository (capacity workbook, Plan workbook, KPI/Daily Status/stock/WIP files, the grinding / kiln / raw-material PDFs, the work-order-reading PowerPoint, `PROJECT_REQUIREMENTS.md`) are approved sources.
* The rules are applied in **planning, validation, analysis and bilingual help**. The machine-readable list is `knowledge/approved_rules.json`; every rule names the code that implements it and the test that checks it.
* **Dated stock, WIP, production plans and forecasts are dated operational evidence**, not permanent constants. They are always shown with an as-of date and their source file/revision, and never reused as if still current.

## What this approval does not do
* It does not make any schedule "confirmed feasible" or the software "production ready". Those claims need the missing information listed in `DEVELOPMENT_STATUS.md` and a trial on the live factory data.
* It does not resolve conflicts *inside* the approved sources. Where two approved entries disagree the software shows the exact entries (file, sheet, cell) and asks one specific question (see "Decisions needed" in `DEVELOPMENT_STATUS.md`). It never picks a side silently.

## Conflict handling (CONFLICT-1)
`suite/capacity.py` lists conflicts with the cells involved (for example mixing tonnes/month versus mills/day x kg/day, and Forming Cap./Hr. versus the 8 h / 3 h columns). The Source Manager reports the same for overlapping data sources.
