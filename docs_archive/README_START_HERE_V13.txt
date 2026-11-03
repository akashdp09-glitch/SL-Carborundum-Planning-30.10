SL CARBORUNDUM SMART FACTORY CENTER V13 — START HERE

MAIN CHANGES
- Home Page replaces Control Cockpit.
- Small Meeting mode switch in sidebar; when ON use Display zoom 125%/140% for larger meeting text.
- Active Files is available from every tab and shows active server location, file modified time, original filename, upload page, user/department when registered.
- Only CENTRAL_DATA\COMPANY_DATA is calculation truth. Identical legacy copies are not shown as conflicts; different old copies are warned and ignored.
- Firing Plan upload is directly available on the Firing page, Capacity page and Sources.
- Capacity vs Plan is a real page using the controlled Daily engine, CAPACITY_DATABASE.xlsx, active Plan-2026 and latest Firing Plan.
- New Request Plan can create a DRAFT even without WO/due date. Generated/estimated fields are marked provisional and must be capacity-checked before release.
- MRP Thai-mode KeyError 'Required kg' fixed: translated editor labels no longer rename internal calculation keys.
- Packaging: one-click same-size substitution for unmatched items plus Include checkbox to manually exclude exceptions.
- Grinding and Cutting remain separate planning processes. WIP may show combined Grinding/Cutting because Production reports them together.
- History tab shows logins/imports/scans/exports and saved planning-field edits.
- Mobile interface has English / Thai / Burmese.

DEFAULT INITIAL ACCOUNTS (change passwords after installation)
admin / admin123
planning / planning123
supervisor / supervisor123
operator / operator123
management / management123

These are factory DEFAULT credentials created only when a username does not already exist. If a password was changed later, the software stores only its secure hash; the changed password cannot be recovered from this README. Admin should reset it instead.

LOGIN BEHAVIOR
- Main Hub opens in VIEW mode without asking for a password.
- Login is requested only for controlled editing. Once logged in, it remains active until Switch Login/logout or the browser session ends.
- Mobile uses its browser session and does not ask again until logout/session expiry.

FILE LOCATION NOTE
Web browsers do not provide the full local Windows/phone folder path of an uploaded file. V13 therefore records the original filename, upload page, user, time, file properties and the central server path actually used by the software.

CUTTING / GRINDING ROUTING
The controlled Daily engine already keeps Grinding and Cutting as separate post-firing routes. V13 does NOT invent a new cutting-factor formula because the exact cutting-factor field/rule was not found in the current package. Existing engine/master routing remains authoritative until that exact source rule is present.

PICTURES USED
- company_front.jpeg: Home Page
- products_main.jpeg: Mobile/QR subtle background
- packing_section.jpg: Packaging page
- factory_site_1.jpg: Daily Planning
- factory_site_2.jpg: Active Files / Sources

VALIDATION
Python syntax compilation completed for Hub, Mobile, Daily and Firing modules. Full Streamlit browser runtime was not executed in the build environment because the Streamlit executable is not installed there.
