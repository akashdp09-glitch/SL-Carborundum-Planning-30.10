F12B controlled fixes
1. Selected Planning Start is the global cutover date. The fast allocator starts evaluating that exact date (or next working day only if selected date is a holiday).
2. Previous issued firing plan may block a kiln across cutover; upstream/readiness/capacity may also make the first feasible firing load later. The planner must not invent a load on the selected date when infeasible. Plan Control sheet records selected start and first feasible firing load.
3. Operator Print rows are sorted by Loading Date, Kiln, Load ID, Floor in incremental chronological order.
4. Operator-facing Excel headings, Status and Reason labels are bilingual English/Thai.
5. Plan2026 remains authoritative for current qty, WIP/status and closure. Previous issued firing plan is continuity/cycle evidence only.
