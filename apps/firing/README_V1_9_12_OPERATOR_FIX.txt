SL PPC FIRING PLANNER V1.9.13 — OPERATOR / GRAPH CONTROLLED FIX

Changes from V1.9.11:
- Fixed NameError: imported math for Kilns Waiting for Parts calculation.
- Daily kiln loading stack uses solid fills only; no hatch/pattern.
- Removed confusing numeric labels from graphs; exact values/details remain on hover.
- Renamed PM VALIDATION to PL Mgr VALIDATION.
- Main firing export sheet previously named Firing Detail is now Operator Print.
- Exact A4 operator pattern now physically packs valid circular hole-host parts first, then compatible same-program P2 nested parts. This changes only physical placement order, not released kiln/date/program/WO quantities or due-date priority.
- Operator A4 still requires exact released quantity to be represented in the pattern and retains kiln/furniture validation.
