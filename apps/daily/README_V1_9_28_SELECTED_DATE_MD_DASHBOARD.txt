V1.9.28 — selected-date MD dashboard + Daily Status graph correction
17-Sep-2026

Controlled changes from V1.9.27 F12R-compatible base:
1. WO closure: CLOSED when either Plan2026 Packing Status EU OR Overall WO Closed FC is closed.
2. Planner-facing Grinding and Cutting remain separate routes; no combined WO-count/risk process display.
3. Daily Status: one clear category-stacked Production Plan vs controlled Capacity chart. Only stack TOTAL is labelled; category values are hover detail. Separate simple grouped total Plan vs Actual by process.
4. Daily Status factory-English normalization no longer displays REVIEW TRANSLATION text; original Thai remains available in source columns.
5. Demand and available capacity are plotted in the SAME graph.
6. Pareto is sorted by affected/risk quantity maximum to minimum before cumulative percentage.
7. Dashboard delivery-risk visibility includes ALL applicable processes x P/R/S/T/M/PB, with one total above each process stack.
8. Selected Dashboard Date is passed to the HD dashboard and download filename (not Planning Start Date).
9. Dashboard due/tomorrow delivery and open/closed views use Plan2026 master, so management visibility is not limited only to rows generated on Planning Start.
10. F12R bilingual firing input compatibility retained.

Important: legacy internal Plan2026 EJ/EK/EL source field names may still contain the historical shared phrase. User-facing process output resolves each WO route to Grinding OR Cutting.
