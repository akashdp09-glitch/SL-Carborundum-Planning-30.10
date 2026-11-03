SL PPC Daily Planner V1.9.0

Controlled additions:
- PLAN ACCURACY / VALIDATION tab:
  due-date visibility, daily capacity compliance, process sequence, work-balance/pull visibility,
  exact Daily Planner vs uploaded Firing Planner WO/date/qty comparison, long-term chain presence.
- Selected-WO Gantt:
  complete planned process sequence, due date, current process marker, current status, finished qty,
  future plan, delivery risk/expected delivery milestone.
- Operational MRP:
  Recommended PO Initiation Date, Expected Receipt Date, Need Date, and risk if PO is initiated today.
- WEEKLY REPORT renamed DEMAND–CAPACITY–RISK VISIBILITY for weekly/monthly/custom management review.
- Long-term backorder:
  order-by-order age, current stage, projected finish, additional lateness, recovery risk/action,
  plus quantity-vs-age severity graph.
- Packaging Plan:
  exact Product Code first; D/T/H sizewise fallback only when exact code is unavailable and always marked VERIFY.
  Supplied packaging control/final report is shown for overdue/requirement/reservation evidence.
- Tooling / Diamond:
  supplied historical consumption + current stock; months cover and replenishment status.
- Project / WO costing:
  BOM-based requirement; user-controlled cost rates only. No rates are invented.
- TV Dashboard:
  compact management risk visibility for open qty, projected late WOs, capacity overloads and firing mismatches.

Speed principle:
heavy packaging/tooling/costing calculations are tab-local and do not alter the core daily scheduling algorithm.
