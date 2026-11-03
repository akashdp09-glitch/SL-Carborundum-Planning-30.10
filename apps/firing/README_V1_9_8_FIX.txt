SL PPC FIRING PLANNER V1.9.8 FIX

Corrections:
1. Mixing Status default column corrected from FH to DH.
2. REJECT remains FH.
3. sl_ppc_fast_store_v4_6.full_sync now accepts mapping=None.
4. GUI mapping is merged over DEFAULT_MAP during full synchronization.
5. Existing configurable Plan 2026 mapping behavior is preserved.

This revision addresses:
TypeError: full_sync() got an unexpected keyword argument 'mapping'
