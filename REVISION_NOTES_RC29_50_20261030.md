# RC29.50 - 2026-10-30

## Fixed
1. **Crash** `NameError: name 'target_env' is not defined` (apps/firing/fast_stage4_v15.py line 340) -> `targetenv`.
   Occurred only when >160 open WOs shared one firing program. Reproduced on RC29.49, gone in RC29.50.
2. **hub.py**: `uuid` was used but never imported (would crash on submit). Import added.
3. **Selected start date is always day 1** (even Sunday/holiday). Removed forced shift to next working day in:
   fast_stage4_v15.py, firing_engine_desktop_v2.py, firing_tomorrow_fast.py (cutover), ppc_fast_core_v4_6.py
   (_reschedule_to_upstream_release), sl_daily_engine_v3_22_from_v17.py, daily_linear_engine_v1_1.py.
   Tested (firing): Sunday 2026-11-01 -> first load 2026-11-01 (was 2026-11-02). Daily-engine edits NOT run-tested.
4. **Speed**: choose_kiln computed the same-program pool once per kiln; now once per call. Same output, ~20% faster
   on a 220-WO synthetic test (152 s -> 121 s). Further speed work still open (is_rectangular_order, same_program_rectangular_*, exact packing).

## Added
- apps/firing/plan_integrity.py + "Plan integrity check" panel in Firing Planner: start date, overweight, overvolume,
  underfilled kilns, kiln double-booking, starts/day, due-date risk (PASS/WARN/FAIL).
- Errors now show a short message and save full details to `logs/firing_error_<time>.txt`.

## Known / not done
- Tested only with synthetic data and Streamlit stubbed; Streamlit screens not run. Real Plan-2026 test pending.
- Dead duplicate `build_daily` (first definition, daily_linear_engine_v1_1.py) left in place; the second definition is the one used.
- Push-pull / upstream-downstream balance not yet re-audited. Beginner manual not yet written.
