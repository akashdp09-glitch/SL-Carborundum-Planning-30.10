# V16.29-rc29.5 — complete archive repair

- Restored the controlled capacity database to the complete package at `apps/daily/CAPACITY_DATABASE.xlsx` (the exact path required by the Daily Planner) and retained the firing copy. It is a built-in planning master, not an upload.
- Mobile tracking starts automatically when Part Audit opens; mobile start script uses the same D: runtime as the hub.
- D: contains the app runtime, package cache and install temp by default. The existing RC14 `CENTRAL_DATA` is reused; otherwise local `CENTRAL_DATA` is created beside the package.
- Preserves the operator URL `176.0.3.99:8000`.
- Every signed-in role can track across sections; submitted observations remain immutable.
- No live databases, WIP photos, QR photos or audit photos are shipped.

Verification in this environment: source compilation and ZIP entry/hash checks. Full Windows setup and physical phone testing were not possible here.
