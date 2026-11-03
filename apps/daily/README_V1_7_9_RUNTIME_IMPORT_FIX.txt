SL PPC DAILY PLANNER V1.7.9

Controlled hotfix only:
- Added `import numpy as np` to daily_planner_app.py.
- Fixes the exact runtime crash:
  NameError: name 'np' is not defined
  in _monthly_open_closed() -> np.where / np.maximum.
- No scheduling, WIP, capacity, post-firing, MPS/MRP, or dashboard logic was changed.
- All Python source files syntax-compiled successfully.
- Exact np.where/np.maximum OPEN/CLOSED calculation was runtime-tested.
