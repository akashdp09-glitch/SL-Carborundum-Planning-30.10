SL PPC DAILY PLANNER V1.4.0 — GLOBAL START + FULL WIP + MPS/MRP DASHBOARDS

Critical correction:
- User-selected Planning Start applies to ALL existing Plan2026 WIP queues: Preparation, Mixing, Forming, Firing-ready, Grinding/Cutting, Packing.
- Existing executable WIP can be scheduled on the selected start date subject to its own resource capacity.
- New output from one process becomes available to the next process on the NEXT WORKING DAY.
- Firing remains controlled by the uploaded Firing Planner; the Daily Planner checks whether enough firing-ready WIP exists on the firing date.
- New firing output: completion -> one QC working day -> next working day post-firing route.
- Existing post-firing WIP does not wait for new firing output.

Visibility:
- WIP graphs for ALL processes, pcs and tons.
- WO-level WIP drill-down by process.
- MPS monthly graph.
- MRP gross material requirement graph.
- WHAT / WHEN / HOW MUCH purchase action table + graph.
- Capacity outlook graph.

Speed:
- Uses stage-buffer/day scheduling with cached resource matches. No exhaustive combinatorial search added.
