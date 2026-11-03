# Closure and backorder rules (CLOSE-1, CLOSE-2) and what they change

Code: `suite/closure_rules.py` (single definition used by the hub, shared analytics, planners and the September analysis). Tests: `suite/test_closure_rules.py`. Rule text: `knowledge/approved_rules.json` (CLOSE-1, CLOSE-2).

## Rules
* **CLOSE-1 - whole order closed** = Packing Status (column EU) is closed **or** Overall WO closure "ปิดของผลิต" (column FC) is closed / cancelled.
* **CLOSE-2 - section closures are informational.** Preparation, Mixing, Forming, Firing and Grinding/Cutting closures say a section finished; they never close the order.
* **Backorder** = whole order open **and** remaining quantity > 0 **and** due date before today (Asia/Bangkok, read when the report runs, never stored).
* "ยังไม่ปิด" = open. "ปิด", "ปิดใบสั่ง", "ยกเลิก", "closed", "cancel" = closed. Blank or `#N/A` = not recorded (not closed).

## Measured effect on the supplied Plan workbook
Source: `Plan 2026-2-Update-01100926.xlsx` (dated operational evidence; workbook modified 2026-10-01), 3,509 order rows, evaluated with today = 2026-10-05.

| Measure | Count |
|---|---|
| Orders in the plan sheet | 3,509 |
| Whole-order CLOSED (EU or FC) | 2,537 |
| - of which FC closed | 1,866 |
| - of which Packing (EU) closed but FC not closed | 671 |
| Whole-order OPEN | 972 |
| - open with FC blank / `#N/A` (closure not recorded) | 345 |
| - open although an earlier section is closed | 617 |
| Backorder on 2026-10-05 | 307 |

Comparison that motivated CLOSE-2: the Preparation section is closed on 3,104 orders. **616 of them are not closed at order level** (no EU, no FC). Treating Preparation as order closure would count 3,153 orders as closed instead of 2,537 and hide those 616 orders (and their backorders). Reproduce with `suite.closure_rules.classify(load_plan(...), today)`.

The 671 packing-only closures are shown with their own state label ("CLOSED (Packing EU closed; FC not closed)") so a reviewer can see that FC has not confirmed them.

## September analysis
`suite/sept_analysis.py` reads `apps/daily/JOB_REGISTER_REFERENCE_SEP2026.xlsx` and keeps four measures separate, each traceable to sheet and cell: sales requests 59, work orders issued 41, items not yet issued 18, production item closures 66. They are never netted into one number (`suite/test_sept_analysis.py`).
