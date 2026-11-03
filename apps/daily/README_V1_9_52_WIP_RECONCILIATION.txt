SL PLANNING DAILY PLANNER V1.9.52 — WIP RECONCILIATION AND MEETING REPORTS

INSTALL: Extract this ZIP to one folder on D: (no nested development folder). Back up your previous working version. Run START_DAILY_PLANNER.bat.

Reporting: Production WIP loads bundled September section summaries by default. Replace them individually when newer files arrive. Review/edit source records in Production WIP; corrected gross kg recalculates tonnes. Section/category comparison matches current Plan2026 stage-ready pcs multiplied by Plan2026 net g/pc. These are different weight bases; a variance is a prompt to investigate, not automatically a planning error. Compare only at a common confirmed snapshot date. A missing Plan2026 weight remains missing, not zero.

The former separate blank 42-row manual Production table has been removed from Reporting. The dashboard uses reviewed Production session data when available. Daily Open/Closed shows category stacks and totals. The Open/Closed-by-type date control filters the WO encoded date COHORT with current closure status; actual historical closures must come from the monthly job register. Monthly Open Job is JOB, Close Job is ITEM until Production confirms matching units.

Bottleneck DATA/STATUS CHECK means a required due date, route, process actual, physical readiness, closure, quantity or evidence is missing/inconsistent; it is NOT a confirmed production bottleneck or proven late delivery.

Management PowerPoint exports: Reporting > Download meeting PowerPoint. Four period types: Weekly, Monthly, Mid-year, Yearly. Requires python-pptx on the target PC; if unavailable use included templates. Period decks use current loaded data, not complete historical trends unless loaded. Missing evidence is explicitly labeled. Never present bundled September data as current without confirmation.

Outstanding limitations: WO-level Production sheets have varying layouts and have NOT been fully reconciled automatically with Plan2026; section-category summaries are the verified comparison level. Reviewer notes are editable in session and exportable as CSV. To preserve edits across restarts, export reviewed CSV; this version does not silently overwrite the original workbooks. Full Streamlit Windows runtime and live factory schema validation still required.
