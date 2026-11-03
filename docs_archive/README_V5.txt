SL CARBORUNDUM INTEGRATED PRODUCTION & PLANNING CENTER — V5 FOUNDATION

NEW IN THIS RELEASE
1. Fast Operator QR screen: http://SERVER-IP:8000/operator
   - designed for phone, section PC, and USB QR/barcode scanner
   - only four main actions: Enter Section, Complete, Problem, Unidentified Part
   - predefined problem buttons: Man, Machine, Material, Method, NCR, Breakdown, Rework, Waiting
2. Central persistent database under shared_database/sl_planning.db.
   - Existing v4 mobile audit DB is copied automatically on first start so audit/event history is preserved.
   - Set environment variable SL_SHARED_ROOT to a Windows network/share folder to place shared_database there.
   - Set SL_DB_PATH for an explicit DB file location.
3. Plan-2026/shared source files remain persistent until replaced.
4. Operator events are timestamped in the same work-order event database used by Mobile Audit.
5. Unidentified physical parts receive a temporary UNID-YYYYMMDD-... identity instead of being lost from control.
6. Branded SL.Carborundum interface using supplied company imagery, optimized for speed.
7. Existing Daily, Firing, MPS/MRP and analysis functions are retained.

IMPORTANT ARCHITECTURE STATUS
This is a V5 integration foundation, not a false claim that every legacy Daily/Firing calculation is already bidirectionally recalculated from every operator event. Shop-floor actuals now have one central event database. The next consolidation step is to make both planning engines consume those actual events directly for automatic rescheduling.

USB QR SCANNER
Use a normal USB scanner configured as keyboard/HID with Enter suffix. Click the WO field once; scanning types the QR/WO and Enter triggers lookup.

SHARE DRIVE EXAMPLE
Before starting, Windows IT can set:
  setx SL_SHARED_ROOT "\\SERVER\\Production\\SL_Planning"
Then restart Windows/session and launch the program.
For reliable simultaneous multi-user operation, a database server is preferable to a cloud-synchronised folder. A normal LAN file server may work for light SQLite use but should be backed up.
