SL CARBORUNDUM INTEGRATED PLANNING CENTER V9 — ONE WINDOW

WHAT CHANGED
1. One visible browser window. Daily Planner, Firing Planner and Operator QR are embedded inside the main Planning Center navigation.
2. Hidden local services still run in the background because the validated legacy engines use different frameworks, but operators/planners no longer need separate browser windows.
3. Shared WIP / Backorder / MPS / Material MRP remain native pages in the same main window.
4. Material MRP Plan-2026 mapping corrected to material1..material5 with g/g.1/g.2/g.3/g.4.
5. Existing Daily WIP pcs scalar/fillna crash correction retained.
6. Main shop-floor sections retained as Preparation, Mixing, Forming, Firing, Grinding, Cutting, Packing. Waiting/Curing remains a Firing-WIP location.

IMPORTANT
This release improves the combined user experience and source consistency. The legacy Daily and Firing calculation engines still execute as background services; they have not been falsely represented as one rewritten calculation engine. The next architectural step for true server multi-user deployment is a central database service used by all modules.
