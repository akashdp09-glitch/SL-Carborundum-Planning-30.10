# RC29.32 Backorder presentation correction
- Current OPEN and CLOSED bars are now adjacent within each due month, with product-category stacks, for HTML and Long-Term Plan JOB/PCS/TON views.
- Explicitly labels three-month OPEN metrics as a *limited due-month snapshot*, not total open WOs/backorders.
- Does not overwrite database or Excel sources; no changes to strict overdue calculation.
- Tests: 7 existing backorder tests passed; Python syntax checked.
- IMPORTANT: The reported 33 vs ~400 discrepancy has NOT been reconciled against a live dashboard export. The chart's last-three-month filter is a possible explanation, not a verified cause. Production workbook and Plan2026 require source-by-source reconciliation before changing strict overdue business logic.
- OPEN/CLOSED chart is current status by due month, NOT historical monthly created/closed event counts. Those require timestamped snapshots/events.
