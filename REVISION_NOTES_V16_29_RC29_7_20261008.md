# V16.29-RC29.7 — one-click setup for the user's Python 3.14 PC

## Base

Built on the user's requested RC29.5 baseline, retaining the RC29.6 capacity-path repair and traceable costing/KPI analysis already applied in this folder. The mobile QR/audit and recovery-plan modules are carried forward from RC29.5.

## Changes in this package

- First start detects the existing Python. If the computer only has CPython 3.14, it automatically installs private CPython 3.12.15 under `RUNTIME\\python312` (no administrator rights and no PATH modification), then installs dependencies into `RUNTIME\\venv`.
- Installer downloads only on first setup; subsequent starts skip the installer and dependency installation when the environment is healthy.
- Python and pip caches remain in `RUNTIME` beside the program. Factory data is not part of this ZIP and remains in the configured D: `CENTRAL_DATA` folder.
- Added a decision test confirming that a Python 3.14-only computer selects the private 3.12 runtime.

## Checks run here

- Python compile check for all included `.py` files.
- Cost/KPI synthetic unit tests.
- Capacity fallback, backorder/recovery navigation, source-slot contract and ZIP/hash checks from the preceding RC29.6 work.
- Installer selection/provisioning logic checked with a simulated Python 3.14-only computer. The download and Windows installer were not executed in this Linux workspace.

## Limits stated plainly

This is a complete program ZIP with an automatic first-run installer, not an MSI. The first setup needs internet access to python.org and PyPI. Real Windows setup, live phone scanning/camera, factory Wi-Fi, concurrent operators, and acceptance against current factory data cannot be exercised from this workspace. Keep the existing working folder and data until the first start succeeds.
