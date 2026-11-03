SL CARBORUNDUM SMART FACTORY CENTER V12

Main changes
1. Clickable left hierarchy: links open the related Hub tab. Hiding the native sidebar releases the space to the main work area.
2. Central file registry: Plan-2026, Sales Forecast, Stock, recipe master and Packaging Standard are stored under SL_SHARED_ROOT\COMPANY_DATA and reused until replaced.
3. Active source name, full location, update time, user and section are shown. Duplicate/stale copies in known program locations are highlighted as conflict risks and are not used by Hub calculations.
4. Shared edit/audit override store: editable WO tables save controlled field changes with Edited By, Section and time. Hub model reapplies those edits.
5. Updated Plan-2026 download: creates a new controlled copy from the active Plan plus saved supported overrides and adds SOFTWARE_EDIT_AUDIT. Original company source is not overwritten.
6. Daily Status uploads persist in SL_SHARED_ROOT\DAILY_STATUS and are reused on later sessions until replaced/removed by an authorized server administrator.
7. Daily and Firing Plan-2026 paths now use SL_COMPANY_DATA so they read the same central source as Hub.
8. Mobile/operator screen has English / Thai / Burmese language selection; user roles remain permission controlled.
9. Everyone with login can view permitted dashboards/work-order pages; write actions continue to use role permissions in the mobile service.
10. Existing firing photos, company hero and product images remain section-specific. No newly claimed company/parts photos were added unless present in this package.

Authoritative production/material close rule remains:
ยังไม่ปิด = OPEN.
ปิดใบสั่ง = CLOSED.
ปิด = CLOSED.
Any controlling Preparation/Final close excludes the WO from backorder and remaining material planning.

Important implementation boundary
The Hub override store is authoritative for Hub analysis/export. Legacy Daily/Firing internal edit widgets are not all rewritten to use the override table; their source uploads are centralized, but a complete row-level bidirectional edit migration across every legacy widget remains a larger refactor. V12 highlights central source and audit data rather than silently pretending every legacy editor writes the same table.
