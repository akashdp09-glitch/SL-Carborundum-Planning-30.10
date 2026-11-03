SL CARBORUNDUM SMART FACTORY CENTER V15

MAIN CHANGE: ONE SOURCE, ONE UPLOAD LOCATION
Upload/replace operational files only in Home -> Active Files / Upload.
Daily Planner, Firing Planner, Capacity, MRP, Packaging and Mobile use those same central files.
Daily Planner and Firing Planner do not ask for duplicate Plan/Firing uploads.

DAILY PLANNER RESET CONTROL
The last calculated Daily Plan is saved to CENTRAL_DATA/CACHE/daily_result.pkl and restored when the embedded Daily Planner reloads. Source paths also reload from CENTRAL_DATA/COMPANY_DATA.

NEW REQUIREMENT PLAN
New Requirement now outputs a PLAN-2026 FORMAT SUGGESTION, not a separate simplified request sheet.
It reads the exact active Plan-2026 columns, finds the closest historical/similar row, can use the optional test/request workbook, preserves useful technical/master attributes, clears execution/closure fields, fills known request fields, and creates a second PLANNING_BASIS sheet.
The original Plan-2026 is never edited. Review capacity/WIP/audit before release, then copy/paste the suggested row into the controlled Plan-2026.

MOBILE LANGUAGE
EN / ไทย / မြန်မာ now changes the operator/mobile navigation and operator screen to ONE selected language. It no longer intentionally prints three languages in the same labels.
Operator lookup shows Plan/system status and the last physical audit separately.
MPS/MRP remain removed from operator mobile navigation.

MAIN IMAGE
The supplied company-front image is used without stretching: background-size=contain, centered, so the colored/green circle remains visible and the small source image is not enlarged into a blurry crop.

ORIGINAL FILE CONTROL
Uploaded originals remain unchanged. Software-generated reconciliation/planning files are separate downloads.
