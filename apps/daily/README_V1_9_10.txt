V1.9.10 DATE-KEY RUNTIME FIX
- Fixes pandas merge ValueError in _crosscheck_ppc_production_actual.
- Root cause: Daily Status Date and PPC plan Date could be different key dtypes (datetime64[s] vs Python object/date).
- Both sides are now normalized to pandas datetime before grouping/merge.
- Section and Work Order keys are stripped strings on both sides.
- many_to_one validation protects against accidental duplicate PPC aggregate keys.
- V1.9.9 TV dashboard and planning rules are unchanged.
