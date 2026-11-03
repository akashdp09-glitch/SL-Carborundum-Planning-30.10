SL PPC DAILY PLANNER V1.6.0
LEAD-TIME CONTROL + BASE-WIP SEMANTICS + LONG-TERM STACKED MPS/MRP
Date: 09-Sep-2026

CORE RULES FROZEN IN THIS RELEASE
1. User-selected Planning Start Date is the horizon start for ALL EXISTING executable Plan 2026 queues.
2. Existing physical downstream WIP does not wait for newly-created upstream work or a new firing cycle.
3. New upstream output obeys Delivery Control inter-process lead-time gates.
4. Firing dates come from the current Firing Planner. Daily Planner does not shift an issued firing date.
5. New firing output follows Firing completion -> QC working day -> post-firing route.
6. Grinding/Cutting is shown as one common post-firing route in the Daily Planner.
7. Sunday is non-working.
8. Capacity/resource constraints remain active. Lead time does not replace capacity.

DELIVERY CONTROL LEAD-TIME SOURCE
The user-provided Delivery Control Process image is included as REFERENCE_Delivery_Control_Process.jpg.
The exact source table is visible inside the program under Evidence / Export and in Excel output sheet "Lead Time Master".
The actual per-WO profile and offsets are in "WO Lead Time Applied".
The kiln/program controlled duration from Cap เตา is in "Lead Time Cap Override".
If controlled Cap เตา / issued Firing Plan requires a longer duration, the controlled kiln/program rule wins; the Daily Planner never shortens it.

DAILY INTER-PROCESS OFFSETS USED
- Preparation -> Mixing: based on source Weighing lead time, rounded up to working-day boundary; minimum 1 WD.
- Mixing -> Forming: based on source Mixing lead time, rounded up; minimum 1 WD.
- Forming -> Firing readiness: Dry/Pre-Curing + Loading (Pre-Finishing), rounded up; minimum 1 WD.
These are profile-specific. AUTO profile is visible and can be overridden with Lead Time Profile in the WO correction editor.

WIP SEMANTICS
The program now follows the older SL_PPC_EXCEL_PPC_SYSTEM_BASE business interpretation:
- Preparation Required = Open Demand (NOT physical WIP)
- Ready for Mixing
- Ready for Forming
- Ready for Firing
- Ready for Grinding/Cutting
- Ready for Packing
WIP charts are broken down by P, R, S, T, M, PB, and UNCLASSIFIED.

MPS / MRP
- MPS is monthly/long-term and shows category/group and size-range stacked charts.
- MRP shows monthly material requirements with materials stacked by month.
- Purchase view shows WHAT / WHEN / HOW MUCH.
- Stock parser reads actual uploaded stock and shows source sheet/column/unit.
- Missing/unmatched stock is NEVER silently treated as verified zero. It is shown as a data gap.

TV DASHBOARD
- Due-date / urgent / delivery-risk WOs
- Current bottleneck/status
- Today and tomorrow by process with WO, customer and quantity
- WIP by process/category
- JPEG export
- Thai-capable Windows font fallback (Tahoma / Leelawadee UI) is used for Thai customer names.

PERFORMANCE
Real-file development benchmark (Plan 2026: 3,207 rows; Capacity master includes 3,789 grinding rows):
- Plan sync approximately 7.8 s in development container
- Capacity DB read approximately 3.6 s
- 30-day scheduling core approximately 4.2 s
- Full detailed build including source sync + lead-time audit approximately 17.3 s
Windows runtime depends on PC/storage and is not claimed to be identical.

VALIDATION REFERENCE
See VALIDATION_REPORT_V1_6_0.txt.
