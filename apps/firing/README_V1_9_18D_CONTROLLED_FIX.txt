V1.9.18D — controlled correction after V1.9.18C did not affect the active paths sufficiently.

REAL ROOT CAUSES CORRECTED
1. Active planning path uses fast_stage4_v15 through firing_tomorrow_fast; under-target delivery exceptions were still being RELEASED there.
   V1.9.18D removes that vitrified delivery-exception release. Below target = HOLD/COMBINE/EXPEDITE UPSTREAM unless weight is the binding hard constraint.
2. Programs with insufficient ready WIP (including P6) could disappear because the allocator plans only Release Candidate rows.
   New UPSTREAM PULL BY FIRING PROGRAM reads the full prepared demand and shows Open, Ready, Not-Yet-Ready and required action even when no load is releasable.
3. The active Streamlit 3-view is pattern_on_demand_v16, not the older Tkinter sl_ppc_pattern_3view module.
   V1.9.18D modifies the active renderer.
4. Stack segments were losing D/T/H evidence when flattened. D/T/H + raw dimension evidence are now carried into every segment.
5. Raw D/T/H strings are preserved so unequal multi-value dimensions can trigger taper visualization.

PATTERN
- deterministic color by WO
- white center hole with hole label in TOP
- taper from text OR unequal raw dimension values
- individual stack pieces in FRONT/SIDE
- approx. 2 mm quartz separator shown in sand color
- mixed Thai/Myanmar/English font fallback
- 100–250% zoom slider
- high-resolution PNG export

Release safety remains controlled by exact furniture/weight/geometry reconciliation.
