# Source workbook analysis and planning evidence

Prepared 2026-09-30 (Asia/Bangkok). The six Daily Status workbooks use worksheet tab names as authoritative event dates; conflicting cell dates are ignored for this analysis. Malformed three-digit years are inferred from valid sibling tabs and flagged.

## Files available in this session

The references were in `/workspace/scratch/1b539f183d18/upload/`. They are analysis-only and are not silently installed as current operational data in this release.

- `Plan 2026-2-Update-240926.xlsx` — 16,756,066 bytes; Excel internal modified 2026-09-24 14:42:08 +07. Main sheet `แผนการเผา`: C = initial due, E = revised due, EV = actual warehouse date.
- `Stock on hand_230926(1).xlsx` — 2,420,998 bytes; Excel internal modified 2026-09-23 18:38:14 +07. This is older than 2026-09-30 and is not assumed to be current stock.
- `Cap แต่ละแผนก(20260911-074159).xlsx` — 2,544,698 bytes; Excel internal modified 2026-09-11 10:01:33 +07. Reference only: its schema differs from the bundled capacity database, so it is not automatically substituted.
- Six separate Daily Status books: `1.เดือน กันยายน เตรียม(1).xlsx`, `2.เดือน กันยายน ผสม(1).xlsx`, `3.เดือน กันยายน ชึ้นรูป(1).xlsx`, `4.เดือน กันยายน 2026 เตา-1.xlsx`, `5.เดือน กันยายน เจีย(1).xlsx`, `6.เดือน กันยายน 2026 Pack-1(1).xlsx`. A Mixing cell on tab `5-7-2026` conflicts with the tab date; tab date is used. Malformed tabs `12-9-206` and `4-9-206` infer the year from valid sibling tabs.
- `5. KPI_ผลิตตามแผนกแยกตาม หน่วยงาน-กันยายน-1.xlsx` — seven sheets; section performance parsed separately from reasons.
- `5. KPI_ส่งมอบสินค้าเข้าคลัง กันยายน-1.xlsx` — two sheets; delivery sheet tab says August while report title says September 2569. Title month takes precedence; mismatch remains reviewable.

Requested files absent from this session's upload area: `Stock on hand_250926(1).xlsx`, `สรุปทบทวน38A400P4VB04 80X25X7 Q26-009 - ผลิตทดแทน - ครั้งที่2.xlsx`, `Revice Forecast P,PB in Quater 3,4.xlsx`, `SL_Planning_MD_Daily_20260924.xlsx`. They were not substituted with similar files.

## Plan delivery performance

From the inspected Plan workbook: 3,409 valid WOs; 3,073 have parseable initial due dates; 2,929 have parseable revised due dates; 2,351 have actual warehouse dates. Score only rows with actual date and valid due date:

| Measure | On time | Scored WOs | Rate |
|---|---:|---:|---:|
| Warehouse actual <= initial due (C) | 1,337 | 2,172 | 61.6% |
| Warehouse actual <= revised due (E) | 1,672 | 2,114 | 79.1% |

These are historical workbook calculations, not a claim about current satisfaction. Missing/invalid dates are excluded. Home provides traceable WO detail and Plan source row.

Daily Status analysis: 3,757 valid WO rows; 225 rows with missing/invalid WO IDs excluded; zero workbook read errors; about 2.5 seconds parsing. Section completion is the earliest dated section tab where cumulative actual meets required quantity or balance is <=0. Plan has no section close timestamps or section-specific due dates; section-vs-customer timeliness is explicitly a proxy.

## Application storage defaults

Shared root defaults to `CENTRAL_DATA` beside the app, configurable by `SL_SHARED_ROOT`. Actual resolved paths appear in Files & Traceability.

- Source registry: `CENTRAL_DATA/source_registry.json`
- Plan/stock/source books: `CENTRAL_DATA/COMPANY_DATA/`
- Department workbooks: `CENTRAL_DATA/DAILY_STATUS/`; prior replaced period versions: `CENTRAL_DATA/DAILY_STATUS/history/`
- Separate KPI books: `CENTRAL_DATA/KPI/`
- Archived uploaded files: `CENTRAL_DATA/SOURCE_COPIES/`
- WIP: `CENTRAL_DATA/PRODUCTION_WIP/`
- Generated reports/QR workbook: `CENTRAL_DATA/REPORTS/`; QR temporary images: `CENTRAL_DATA/REPORTS/QR_TEMP/`
- Desktop QR registry: `CENTRAL_DATA/QR_REGISTRY.json`
- Mobile QR scan images: `CENTRAL_DATA/PHOTOS/QR_SCANS/YYYY/MM/DD/`; audit photos: `CENTRAL_DATA/PHOTOS/MOBILE_AUDITS/`
- Database: `CENTRAL_DATA/DATABASE/sl_planning.db`

`SL_REPORT_ROOT`, `SL_PHOTO_ROOT`, `SL_DB_PATH`, and `SL_SOURCE_COPY_ROOT` can override defaults. Import timestamps in the app mean the time of app import, not the analysis receipt date or Excel internal modified property.
