F12X EDITABLE PLANNING DATA + TAB NAV + RELEASE VALIDATION
- Removed decorative firing ticker from planner working screen.
- Replaced Function select-slider with horizontal clickable page tabs.
- Added WO-level Planning Data Editor: Due Date, Order Qty, Shape, D/T/H, Planner Closed Override and TEST/NORMAL.
- Planner overrides are applied to the in-memory firing candidate dataframe before firing calculation; original Plan2026 remains unchanged.
- Shape/D/T/H override therefore flows into the firing calculation/pattern input on the next CREATE FIRING PLAN run.
- Existing Test Work logic retained: Product Code starting 1 defaults TEST; any WO may be manually TEST/NORMAL; code 4 is not automatic TEST.
- Normal vitrified starts remain hard capped at 2/day excluding T0; resin separate.
- Company logo assets bundled when available.
Static compile validation passed; full Streamlit runtime not available in build environment.
