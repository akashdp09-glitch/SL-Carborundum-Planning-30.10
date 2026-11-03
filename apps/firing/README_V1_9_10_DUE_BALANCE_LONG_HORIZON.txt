SL PPC FIRING PLANNER V1.9.10 — DUE-DATE FIRST + BALANCE-PULL + LONGER HORIZON

BASELINE
- Based only on V1.9.9 Controlled Release.
- No V1.10.x experimental branch logic was imported.

PLANNING THUMB RULE
1. Protect due date first.
2. Respect physical kiln/furniture/program/weight/volume feasibility.
3. T1-T12/T14: max 2 normal vitrified starts/day.
4. T0 remains the existing small auxiliary vitrified kiln and does not consume those two normal slots.
5. R4/R5/R6 remain separate resin resources.
6. After earlier-due feasible work has been considered, use otherwise-idle feasible capacity by pulling compatible lower-priority / farther-due work.
7. Never move far-due work ahead of an executable earlier-due load merely to improve utilization.

HORIZON
- Default = 30 days.
- User selectable = 1–365 days.
- Pull horizon follows the selected planning horizon.

TRACEABILITY
- Released load records include Planning Priority Class and Planning Policy so management can distinguish due-date work from balance-pull work.
