V16.1 CORRECTIVE BUILD

1. FIXED DAILY PLANNER NameError
The obsolete local uploader variables su, salesu, packu, diamu, kpisecu and kpidevu were remnants from older Daily versions.
Daily now reads the central shared sources only. The stale upload block was removed, not merely hidden.

2. PLAN-2026 ROW-3 MAPPING SOURCE
Based on the user-provided Row_3_Thai_English_Cell_Mapping.xlsx:
A ProductionCode / WO
C Scheduled warehouse receipt date = initial due date
E Revised delivery date
J Quantity
K Product code
BY Number of mills/mill batches
CP Number of cuts per piece
CQ Weight per piece
CY Preparation status
DH Mixing status (#VALUE may exist in source)
DR Forming close work order
EC Firing close work order
EL Grinding close work order
FB Packing/status
FC Production closure
HH:HX process-progress fields
IA Akash/Planning closure
IB Scheduled sales delivery date

HH:HX sequence:
HH production order issue/start
HI planning
HJ preparation start
HK waiting mixing
HL mixing start
HM waiting forming
HN forming start
HO waiting kiln loading
HP loaded kiln
HQ firing
HR unloaded kiln
HS waiting sorting/screening
HT grinding start
HU waiting packing
HV packing start
HW waiting dispatch
HX dispatch start

Rows 1 and 2 were not present in the uploaded mapping workbook supplied to this build; therefore V16.1 does not invent their section grouping. The software exposes section status using the confirmed row-3 fields above. If a replacement mapping workbook contains row 1/2 grouping, it can be incorporated in a later controlled mapping revision.

3. WO TRACKING
Desktop Home and Operator/Audit allow WO lookup regardless of case or hyphens/spaces.
They show quantity, initial due date, revised date, BY mill batches, Plan-2026 current location basis, and OPEN/CLOSED by confirmed section fields.
Mobile API and operator page now also return/display section OPEN/CLOSED.

4. ORIGINAL SOURCE FILES
Never edited by this correction.

V16.2 RUNTIME CORRECTION
Daily Status no longer references the removed `actualu` uploader. `actualu` is explicitly an empty shared-source input list, and Daily Status continues to load saved files from CENTRAL_DATA/DAILY_STATUS.
