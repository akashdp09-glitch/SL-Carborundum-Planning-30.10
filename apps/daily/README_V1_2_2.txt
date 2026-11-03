SL PPC DAILY PLANNER V1.2.2 - ACCURACY + CAPACITY CONTROL

Preserved: current fast scheduling architecture and Capacity Database auto-load.
Changes:
- HOLD manager counts unique Work Orders, not raw rows.
- Forming HOLD split into NO MACHINE/SIZE MATCH versus CAPACITY/TIME INSUFFICIENT.
- Planning-layer fields can be corrected without overwriting Plan 2026.
- Optional verified Forming Machine + pcs/day override is available for real shop-floor exceptions.
- Capacity vs Plan remains non-stacked and explicitly distinguishes rated/matched capacity from executable scheduled quantity.
- Never invents capacity to clear a HOLD.
