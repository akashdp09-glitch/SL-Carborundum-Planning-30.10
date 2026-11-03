SL PPC FIRING PLANNER V1.9.17

KEY CORRECTION
The fast planner previously selected a released quantity by weight/envelope,
then the A4 generator applied the detailed physical furniture model afterwards.
That could produce errors such as released 2258 / patterned 166.

V1.9.17:
FAST candidate -> EXACT detailed physical/furniture reconciliation -> RELEASE.

A released quantity must therefore be reproducible by the A4 pattern engine.

NORMAL STACKABLE VITRIFIED PRODUCTS
The artificial two-piece ceiling is removed. Capacity is controlled by actual
piece height, controlled max stack height, clearance, I-block/support height,
kiln usable height, furniture quantity and weight.

NO-STACK RULES RETAINED
Hin Khat Phuen / ขัดพื้น: upright, no product-on-product stacking.
Resinoid: no product-on-product stacking in this model.

R / RICE STONE RULES RETAINED
Large rings may span multiple plates; center holes remain open; compatible
parts may use the hole; top level needs no imaginary upper shelf; any real
upper floor still needs valid support clearance.
