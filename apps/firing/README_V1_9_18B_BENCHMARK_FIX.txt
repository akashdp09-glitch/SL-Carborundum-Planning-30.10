V1.9.18B — BENCHMARK-CONTROLLED FIX

BASE:
SL_PPC_FIRING_PLANNER_V1_9_18_TOP_LEVEL_BILINGUAL_A4

Only two controlled changes were made:

1. Waiting/remaining-to-occupancy table synchronization
   - Any load below the user-selected occupancy target now appears in the waiting table,
     even when its Release Gate is not HOLD.
   - This fixes cases such as P6 Load 005 and P3 Load 060 appearing in the utilization
     graph but not in the waiting table.
   - The table now shows Release Gate and Occupancy Gap %.

2. P6 right-size check for T0
   - T0 already supports P6 in the benchmark kiln database.
   - Benchmark code previously imposed a strong -20000 score penalty on T0 unless the
     WO was urgent/test/sample.
   - Now P6 may prefer T0 when:
       a) the part physically fits T0,
       b) same-program P6 demand can reach the selected T0 occupancy target, and
       c) that demand is still insufficient to reach the target of a normal vitrified kiln.
   - T0 is not made the default P6 kiln.
   - Exact furniture/pattern and hard weight checks remain unchanged and authoritative.

No other V1.9.18 planning, operator, bilingual A4, physical packing, due-date, or release logic was intentionally changed.
