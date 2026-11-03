# V16.29 RC27 revised working candidate — 2026-10-06

This is a review/test package assembled from the current RC26 source snapshot. The snapshot has no Git history in this workspace, so the official clean-commit release builder could not be used. This ZIP is **not a factory-validated or production-approved release**.

## Changes in this working copy
- Database and photo recovery initialization is cached once per Streamlit server process instead of running on every rerun.
- Monthly Open/Close report reads the period from the uploaded filename/workbook and caches parsing by file path, size and modification time. If the period is missing, it defaults to the present Thailand local month and tells the user.
- Weekly Recovery Action Plan has direct hub and Daily Planner navigation from Backorder / Delivery Risk.
- Removed the embedded internal-app URL/auth-ticket caption. QR and audit evidence images remain.
- Removed decorative factory/product image payloads from frequent planning views; replaced them with text/color headers.
- Removed the “Planning Center · one shared source” slogan beneath the global heading.
- Replaced the sparse homepage banner with the bundled `assets/company_front_clear.jpeg` factory photo. It is 46 KB, embedded locally and cached in the Streamlit process; no network image request is made. The functional phone-connection QR remains.
- Daily Status parsing now caches against each source file's resolved path, modification time, size, SHA-256 and column settings. Streamlit upload wrapper objects are excluded from the cache key, so reruns do not repeatedly reopen every date tab.
- Home source-registry reads are cached against file revision metadata. Removed global Streamlit cache clears after Plan uploads, status imports, and override saves; file-based caches naturally invalidate on source revisions.
- Home/source upload widgets are idempotent within a browser session using Streamlit's upload ID, filename and size. A retained Plan, WIP or section workbook is not repeatedly re-hashed/re-imported on unrelated page reruns, and an already processed Plan upload does not re-run the phone database sync.
- Visible timestamps identify Thailand local time at Phan Thong, Chonburi. Internal clock uses the IANA Thailand zone Asia/Bangkok (UTC+7).
- KPI definitions/scoring were not changed.

## Verification
Python syntax compilation passed for changed modules. Static regression checks cover the bundled hero image, absent slogan, source-fingerprint cache key, upload idempotency and removal of broad cache clears. A local smoke test passed for a November workbook and for a simulated January 2027 local-date fallback. `pytest` is not installed in this environment, so checks were run directly rather than through pytest. `apps/daily/VERIFY_RELEASE.py` passed with six pre-existing legacy changes still pending review. Streamlit UI, Windows startup, phone cameras, mapped drive access, concurrent factory use, and factory workbook agreement were not available for this check.

## Install/use
Unzip to a separate test folder. Do not replace the live factory installation until Windows and factory-data checks pass. Live databases, photos, secrets, upload archives, current operational workbooks and generated reports are excluded; retain/copy the existing CENTRAL_DATA separately.
