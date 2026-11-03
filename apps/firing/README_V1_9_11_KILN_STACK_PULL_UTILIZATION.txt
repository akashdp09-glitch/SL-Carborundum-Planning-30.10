SL PPC FIRING PLANNER V1.9.11

Controlled changes from V1.9.10:
- Replaced normal-vitrified-only manpower graph with ALL planned kiln loads by day.
- Daily stacked graph shows every released kiln; kiln by color, firing program by pattern/hover.
- Added Volume vs Height vs Weight utilization comparison for every released load.
- Hover explains Load ID, qty, kiln, program, limiting constraint and release reason.
- Height utilization is NOT fabricated. If fast planning has no exact pattern height, it stays blank and is marked for exact pattern validation.
- Added Kilns Waiting for Parts / Upstream Pull table and graph for HOLD/COMBINE loads.
- Waiting table shows kiln, program, current qty/volume, target volume, same-mix estimated extra qty, upstream WIP/process signal and candidate WOs.
- Qty needed to target is explicitly an upstream pull estimate only; exact operator release still requires pattern/furniture/weight validation.
- Due-date-first, max normal vitrified starts, T0 separate, resin separate, kiln cycles and physical release logic preserved.
