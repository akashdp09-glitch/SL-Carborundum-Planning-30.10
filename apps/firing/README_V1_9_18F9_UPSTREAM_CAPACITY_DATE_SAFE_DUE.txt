SL PPC FIRING PLANNER V1.9.18F9 — UPSTREAM CAPACITY DATE + SAFE REVISED DUE

Core correction:
- A future kiln load is not allowed to stay on a date merely because its missing quantity is theoretically producible by a later candidate date.
- Proposed kiln schedule is first created by due date / compatibility / physical utilization.
- Shared Preparation -> Mixing -> Forming schedules are then generated with actual capacity logic.
- Each kiln load is shifted to the latest earliest-release date of its WOs when upstream cannot supply the proposed date.
- After shifts, kiln cycle and max 2 normal vitrified starts/day (T0 excluded; resin independent) are re-applied.
- Upstream schedule is regenerated against final firing dates and capacity gate is checked again.
- Excel/UI show Original Proposed Load Date, capacity-confirmed Load Date, actual required upstream dates, Suggested Safe Revised Due Date, Due Date Protection and Capacity Date Validation.
- Suggested Safe Revised Due Date uses firing completion plus conservative downstream lead-time allowance from the Capacity Master by category. It is a planning suggestion; Daily Planner downstream shared-capacity confirmation remains the final delivery commitment.

Positive planning rule:
Ready + capacity-achievable MAKE stays planned, but the firing date must be late enough for the shared upstream capacity plan to actually supply it.
