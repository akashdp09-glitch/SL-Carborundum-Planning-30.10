SL CARBORUNDUM INTEGRATED PLANNING CENTER — V7 CORRECTIVE RELEASE

Key corrections:
1) Fixed Daily Planner scalar .fillna crash when WIP pcs column is absent.
2) Shared Backorder now uses Due Date < today AND Open Qty > 0, matching Daily Planner basis.
3) Shared Material MRP reads actual Plan-2026 headers material1..material5 + g/g.1..g.4 and CY/FB/FC close rule.
4) Correct shop-floor sections: Preparation, Mixing, Forming, Firing (including Waiting/Curing location), Grinding, Cutting, Packing, Other.
5) Audit History page shows who, when, WO, status/location and pictures.
6) Data Location page shows exact live DB, picture, source-copy and report folders.
7) Plan-2026 import creates a software-owned source copy and an ALL-WO QR report. Original selected Excel is never edited.
8) Operator WO lookup can create/view the permanent unique QR for that WO.
9) Login remains remembered for 30 days on the device.

IMPORTANT MULTI-USER STORAGE:
- Application can stay local on each PC.
- Photos/source copies/reports can be on server using SL_SHARED_ROOT / SL_PHOTO_ROOT / SL_SOURCE_COPY_ROOT / SL_REPORT_ROOT.
- Do not put a live SQLite DB on OneDrive/SharePoint sync. For many simultaneous users, use one central FastAPI service and have all browsers connect to it; a server database migration is the production-scale next step.
