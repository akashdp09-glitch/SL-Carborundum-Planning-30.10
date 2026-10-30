# RC29.39 — Backorder consistency, uploads, and WO status lookup

- HTML dashboard open-backorder card now uses the same overdue month/category roll-up as the Backorder Analysis tab.
- HTML dashboard combines delivery-risk bars, bottleneck-process share, and major delivery-risk work orders on one slide.
- Home adds a source-type selector for all non-knowledge Source Manager inputs, batch upload for per-section Daily Status files, and batch upload for Production WIP snapshots.
- Daily Planner includes a compact link to open the Home source uploader.
- Daily Planner adds on-demand WO lookup showing Plan-2026 order details and prior/future process schedule plus the newest saved physical audit and photo when present. Lookup reads the shared audit database only after the user submits a WO.
- Mobile WO details and desktop audit continue to use the existing shared part status/audit data paths. Existing QR identities are not changed.
- Validation: Python compilation passed for Hub, Daily Planner, and mobile app. Five focused backorder-definition unit tests passed. Full Streamlit/Plotly HTML rendering and target Windows/mobile testing were unavailable here.
- Package base: locally available RC29.38 package plus the changes above.
