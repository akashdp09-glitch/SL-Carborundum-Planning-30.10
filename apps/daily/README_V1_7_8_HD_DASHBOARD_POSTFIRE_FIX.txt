SL PPC DAILY PLANNER V1.7.8 — HD DASHBOARD + POST-FIRING FIX

Controlled corrections:
1. Fixed integration-layer bug that merged Grinding and Cutting after the core scheduler.
   Grinding and Cutting remain separate from core schedule through UI, capacity summary and export.
2. Runtime tested existing post-firing WIP:
   - Grinding route schedules Grinding then Packing.
   - Cutting route schedules Cutting then Packing.
3. Runtime tested linked firing output:
   Firing -> one-working-day QC gate -> correct Grinding/Cutting route -> Packing.
4. Due-date-first + pull planning logic remains unchanged.
5. WIP stacked chart:
   - no labels on individual category segments;
   - one TOTAL label above each process stack;
   - hover keeps category, pcs, ton, WO details.
6. Backorder:
   - monthwise OPEN vs CLOSED pcs and WO count by due month;
   - open recovery demand remains separately visible.
7. HD JPEG management dashboard:
   - exact 2560x1440;
   - Today delivery / packing;
   - Tomorrow delivery / packing;
   - WIP totals by process;
   - today plan-vs-capacity utilization;
   - delivery risk / bottleneck;
   - monthwise open vs closed;
   - stock in hand;
   - all-process Today execution targets.
8. PCS values use whole-number presentation where appropriate.

Validation:
- All Python source files syntax-compiled successfully.
- Core post-firing route tests passed for Grinding and Cutting.
- Firing-linked post-firing flow test passed.
- HD JPEG generation test passed at 2560x1440.
- Monthwise OPEN/CLOSED backlog aggregation test passed.
