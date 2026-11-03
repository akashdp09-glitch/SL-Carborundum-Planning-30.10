# RC29.51 - 2026-10-30
Reported: start date 30 Oct selected, firing report starts 31 Oct.
Finding: ppc_fast_core_v4_6._reschedule_to_upstream_release moves any load containing newly-made pieces (MAKE pcs > 0)
to the WO's "Earliest Release Date" from the shared-capacity upstream plan (Forming must finish 1 working day before firing).
That is a rule, not a crash. It could NOT be reproduced with synthetic data (first load stayed on 30 Oct), so the cause in
the real data is not yet proven.
Added: "Day-1 explanation" table + "Firing on the selected start date" check (apps/firing/plan_integrity.py, shown in the
Plan integrity panel). It lists every load moved off the start date, its WOs, and the planner's recorded reason.
Not changed: the upstream release rule itself (physically meaningful). Needs real Plan-2026 + Daily Status to decide
whether the Earliest Release Date for those WOs is correct.
