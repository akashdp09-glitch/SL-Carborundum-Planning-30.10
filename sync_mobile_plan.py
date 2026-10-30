"""Load the ONE Home Plan-2026 into the phone / QR work-order database.

Older copies looked at program\\company_data\\Plan-2026-LATEST.xlsx. Home now
stores the file at CENTRAL_DATA\\COMPANY_DATA\\Plan-2026-LATEST.xlsx. QR labels
were still printed from the in-memory plan, so the phone said the work order
did not exist. This script only imports the existing shared file.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from suite.central_paths import child_environ, resolve_plan, write_pointer  # noqa: E402

os.environ.update(child_environ(ROOT))
write_pointer(ROOT)

plan = resolve_plan()
if plan is None:
    raise SystemExit("No shared Plan-2026. Upload it once on Home → Upload / replace source files.")

sys.path.insert(0, str(ROOT / "apps" / "mobile"))
from app import import_plan2026  # noqa: E402

added, updated, rejected, errors = import_plan2026(plan, plan.name, "SL_SHARED_PLAN")
print(f"plan={plan}")
print(f"db={os.environ.get('SL_DB_PATH')}")
print(f"new={added};updated={updated};rejected={rejected};diagnostics={len(errors)}")
if errors:
    print("errors=" + "; ".join(str(e) for e in errors[:8]))
