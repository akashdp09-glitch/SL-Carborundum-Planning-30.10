V16.4 — CURRENT-IP QR + DESKTOP OPERATOR CONTROL

1) Old printed QR after IP change
- A QR URL contains the server IP at the time it was created. Software cannot alter ink already printed.
- Desktop Operator QR / Mobile Audit now has REGENERATE ALL WORK ORDER QR WITH THIS CURRENT IP.
- The generated Excel contains EVERY WO, not only new WOs, and embeds the current LAN IP in every QR.
- Source/Data page retains both ALL QR and NEW QR generation choices.

2) Desktop Operator QR / Mobile Audit is the richer PC version
- Phone connection QR/current address.
- Handheld USB scanner / typed WO.
- Laptop/inbuilt camera QR capture.
- Plan-2026 quantity, initial/revised due, BY mill batches, section open/closed.
- Editable physical audit, location, verified quantity, process, notes and optional part photo; Submit saves centrally.
- Quick WIP summary and full Daily Planner access inside the desktop control.
- Existing Plan vs Physical Audit and editable Daily Status remain on the same desktop page.

3) Mobile
- Mobile layout remains compact.
- In-app camera scan now opens the same detailed /mobile/wo/<WO> audit page used by a direct QR scan.
- That detailed page contains Physical Location, Verified Qty, Status, Observed Process, Notes, Part Photo and SAVE.
- Typed WO lookup still shows status; a large PHYSICAL AUDIT · PART PHOTO · SAVE LOCATION button opens the detailed audit page.

4) Testing performed for this build
- Python compilation: hub, mobile, daily, firing.
- FastAPI runtime: login + /operator page.
- QR photo decoder runtime with URL-style QR containing an old/different IP.
- Detailed /mobile/wo/<WO> runtime page verified to contain Physical Audit, photo and location controls.
- ZIP integrity checked after packaging.
