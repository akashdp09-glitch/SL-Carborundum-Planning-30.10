# Local D: storage guide — RC29.21

The active root is selected in this order:

1. `D:\<new program folder>\CENTRAL_DATA`, when you copy the data folder beside the revised program.
2. Otherwise, `D:\SL_Carborundum_Planning_V16.29-rc14\CENTRAL_DATA` when the legacy root exists.

The revised program prefers its own copied folder so the previous audit records, reports, source files and pictures travel with the version. The app does not require a mapped Z: drive. Mobile phones send scans, status updates, and photos to the app over factory Wi-Fi; the app PC writes those uploads to its active D: folder. A phone does not need direct access to D:.

| Data | Local path |
|---|---|
| Main planning / audit database | `<active CENTRAL_DATA>\DATABASE\sl_planning.db` |
| Mobile audit photos | `<active CENTRAL_DATA>\PHOTOS\MOBILE_AUDITS` |
| QR scan evidence images | `<active CENTRAL_DATA>\PHOTOS\QR_SCANS` |
| Unidentified part photos | `<active CENTRAL_DATA>\PHOTOS\UNIDENTIFIED_PARTS` |
| Source workbook copies | `<active CENTRAL_DATA>\COMPANY_DATA` and `SOURCE_COPIES` |
| Daily Status workbooks | `<active CENTRAL_DATA>\DAILY_STATUS` |
| KPI workbooks | `<active CENTRAL_DATA>\KPI` |
| Production WIP inputs | `<active CENTRAL_DATA>\PRODUCTION_WIP` |
| Reports and generated QR files | `<active CENTRAL_DATA>\REPORTS` (`QR_TEMP` holds individual QR PNGs) |
| Backups and calculation cache | `<active CENTRAL_DATA>\BACKUPS` and `CACHE` |
| Scenario / user settings databases | `<active CENTRAL_DATA>\DATA` |

`SERVER_STORAGE_CONFIG.bat` checks that the selected local root is writable. It creates missing child folders but never empties or replaces the root. If D: is unavailable or not writable, startup stops with a local-drive message. The app UI's Files & Traceability page shows the exact resolved path.

Before installing a new code ZIP, close the app and make a dated backup of the complete `CENTRAL_DATA` folder. Do not delete or replace it when updating application code. Use one app-server process as the SQLite writer; operators connect as browser/mobile clients. The in-app Files & Traceability screen displays the resolved active locations.
