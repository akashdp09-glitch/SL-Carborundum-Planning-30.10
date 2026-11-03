V1.2.1 HOLD MANAGER + WO LOGIC
- Preserves V1.2 fast scheduling architecture.
- Dashboard counts unique Work Orders, not issue rows. Supports future multiple rows/partial deliveries for same WO.
- HOLD/Issue Manager consolidates reasons by WO and affected quantity.
- Editable planning-layer corrections: Category, Specification, Product Code, Shape, D/T/H, Net/Gross weight. Source Plan 2026 is not overwritten.
- If data is correct but upstream capacity is genuinely insufficient, use existing Firing/Kiln Adjustment to move firing later; do not falsify machine/size data.
- Firing daily capacity display now sums distinct kiln-load capacities instead of treating one max load as the whole day.
- Forming capacity remains matched physical capacity; planned quantity remains pull requirement after existing WIP, so low utilization can be legitimate and is explained.
