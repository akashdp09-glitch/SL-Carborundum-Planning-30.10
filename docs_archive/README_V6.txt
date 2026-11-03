SL CARBORUNDUM INTEGRATED PLANNING CENTER V7

OPERATOR LOGIN
- Login once on each phone/section PC. Session is remembered for 30 days unless Logout is used or browser cookies are cleared.
- Audit/event records use the logged-in username automatically. Operators do not type their name for every scan.

SOURCE FILE SAFETY
- Original Excel files selected by the user are never edited, renamed, moved or deleted by this application.
- The application works from its own imported/copy data.

CENTRAL STORAGE
Edit SERVER_STORAGE_CONFIG.bat before first production use.
Default: this program folder\CENTRAL_DATA
Recommended server example: \\SERVER\Production\SL_Carborundum_Data
Folders:
 DATABASE\sl_planning.db = central transactions/audit history
 PHOTOS\MOBILE_AUDITS = audit pictures
 SOURCE_COPIES = application-controlled source copies
 REPORTS = generated reports

IMPORTANT: Test the chosen server path with 2-3 WOs before factory-wide deployment. For many simultaneous users, a server database (PostgreSQL/SQL Server) is safer than SQLite on a sync folder. Do not use a OneDrive/SharePoint sync folder for the live SQLite database.
