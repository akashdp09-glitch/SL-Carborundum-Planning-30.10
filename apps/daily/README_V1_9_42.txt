V1.9.42 — Distinct Stack Colors + Reference MPS/MRP/Backorder

TV Dashboard
- Orange/gray/white remains the shell/theme only.
- Product-category stacks use distinct analytical colors: P blue, R green, S red, T purple, M cyan, PB yellow.
- Delivery-risk slide shows up to 12 major risk WOs per product category with Customer, Bottleneck Process and Qty.
- Final slide uses a wider right panel.
- Backorder TV graph = monthwise OPEN/CLOSED buckets, each stacked by product category with total above each stack.
- Current WIP graph enlarged; backorder bottleneck graph enlarged.

Long-Term Plans
- Backorder analysis follows the supplied historical planning reference: Month x OPEN/CLOSED x Product Category.
- Separate QTY (pcs), TON and JOB/WO stacked views with whole-stack totals.
- OPEN backorder bottleneck-process analysis added from delivery-risk evidence.
- Existing detailed backorder recovery, Gantt and risk evidence retained.
- MPS/MRP sections retain current controlled engine and now explicitly follow the supplied reference flow:
  monthly finished-product demand -> MPS/capacity -> BOM/material gross requirement -> stock -> net need -> purchase timing.

Validation
- All Python files compile successfully.
- Factory/runtime validation still required with current Plan2026, Firing Plan, Capacity, Stock and Sales Forecast files.
