SL Carborundum Smart Factory Center V16.8

Fixes and changes:
1. Removed all undefined kpis() calls that caused WIP/MPS NameError.
2. Home Page now contains the phone connection QR, current mobile address/status, direct central-source uploads, Production WIP upload, and a compact today summary.
3. Home upload controls use the same central target filenames/locations as the Source Files page; no duplicate source system was created.
4. Home Page still does NOT contain WO part-tracking input.
5. New Requirement Plan now accepts multiple Work Orders/requests in one editable table.
6. Multi-WO output first sheet uses the active Plan-2026 header/column structure and one suggested row per new WO. Historical Plan-2026 rows are used for technical/master suggestions; execution/closure fields are cleared. PLANNING_BASIS records assumptions and similarity basis.
7. Original Plan-2026 is never overwritten by this feature.
