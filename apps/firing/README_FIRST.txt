V1.9.10 CONTROLLED DUE-BALANCE LONG-HORIZON

SL PPC FIRING PLANNER V1.9.4 - RELEASE-LOCKED PHYSICAL OPERATOR PATTERN

START: double-click START_FIRING_PLANNER.bat

V1.9.4 corrections
- Fixes A4 operator failure where a released WO could show patterned 0 because detailed pattern generation re-planned a different WO mix.
- Operator pattern is now LOCKED to the exact released Load ID, kiln, program and WO quantities.
- Standard rectangular / HONING / SEGMENT parts use a stable FLAT physical orientation: smallest dimension vertical, two larger dimensions as footprint.
- Shape containing ขัดพื้น keeps the explicit factory special rule: vertical / no product-on-product stack.
- P002-201125 test case (25 pcs, 102 x 200 x 22 mm) was physically packed as 25/25 and A4 Excel/PDF generated successfully in the development test.
- Exact furniture/quantity validation runs only for the selected operator load, preserving the fast 30-day allocation architecture.
- If exact selected-load furniture capacity cannot account for released quantity, the operator sheet remains blocked rather than printing unsafe evidence.

Operator evidence
- one kiln/load per A4
- top/front/side views
- refractory plate, I-block and support-node evidence
- WO, pcs, dimensions and program
- Thai uses Windows Angsana New (preferred), with Tahoma/Leelawadee UI fallback when available
- Burmese uses Windows Myanmar Text when available

Important
The 30-day forecast remains fast screening/allocation. The selected A4 operator release is the exact physical/furniture validation stage.
