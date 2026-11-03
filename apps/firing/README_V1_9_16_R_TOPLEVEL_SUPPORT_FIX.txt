SL PPC FIRING PLANNER V1.9.16

Controlled correction for large R / rice-stone physical loading.

Root cause corrected
--------------------
The previous detailed engine required an I-block above EVERY loaded floor,
including the top floor. A thick rice stone could therefore be rejected as
patterned 0 when no single I-block was tall enough, even though Production can
physically load that R part on the top refractory level.

V1.9.16 physical model
----------------------
1. Large R/rice stone may span multiple adjacent refractory plates.
2. The real center hole remains open.
3. Compatible circular/rectangular parts may use the hole when geometry fits.
4. Inter-floor support columns may pass through the open center hole.
5. A NON-TOP loaded floor needs an I-block/support height sufficient to create
   another shelf above it.
6. The TOP loaded floor does NOT require an imaginary upper shelf or I-block.
7. Kiln outer dimensions, top/bottom clearance, plate quantity, weight and
   released quantities are still validated. No unrestricted override is used.
8. Hin Khat Phuen remains upright / no product-on-product stack.
9. Operator pattern keeps short Part IDs and larger legend/furniture text.

Capacity database
-----------------
CAPACITY_DATABASE.xlsx is retained from the user's latest revised master used
in V1.9.15.

Validation
----------
- Python syntax compile: required.
- Synthetic thick R/rice stone regression: required.
- Multi-floor test: a second floor above an over-height R remains blocked unless
  a valid inter-floor support height exists.
