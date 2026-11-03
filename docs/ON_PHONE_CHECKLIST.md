# On-phone and on-site checklist (not verifiable in the cloud)

The cloud tests use synthetic images and a headless desktop browser. They do **not** prove any item below. Run each on the real phones and the real factory network, record the result, date and tester, and keep the evidence photos.

Test with: one Android phone (Chrome) and one iPhone (Safari) at least; the server started by `START_SL_CARBORUNDUM_PLANNING_CENTER.bat`; a **trial copy** of the data. Use only test work orders until all items pass.

## A. Reach the server (factory Wi-Fi)
| # | Step | Expected | Result |
|---|---|---|---|
| A1 | Phone on factory Wi-Fi opens `http://SERVER-IP:8000/mobile` (no certificate). Optional: `https://SERVER-IP:8443/mobile` after installing `http://SERVER-IP:8000/tls/ca.crt` | Login page. HTTP must open even if HTTPS/cert fails | |
| A2 | Same from the far end of the plant / the weakest-signal area | Page loads (note seconds) | |
| A3 | Switch Wi-Fi off in the middle of a submit | Screen says NOT saved, data kept | |
| A4 | Switch Wi-Fi on, press Submit again | Exactly one record on the desktop register | |
| A5 | Windows Firewall: another PC reaches 8000 | Opens | |
| A6 | Server IP changes (DHCP) or server restarts | Printed `SLWO:` QR labels still work | |
| A7 | Live camera on the HTTPS page | Camera starts after permission; if refused, Photo of QR and type still work | |

## B. Camera and QR
| # | Step | Expected | Result |
|---|---|---|---|
| B1 | Scan page -> live camera, point at a printed `SLWO:` label from daylight | Reads and goes to the confirm page (not auto-saved) | |
| B2 | Same under factory lighting, at 20 cm, 40 cm, 60 cm | Note the working distance | |
| B3 | Curved/dusty/shiny label; label on a pallet at an angle | Note failures | |
| B4 | "Take photo" of the label (no live camera) | Decoded by the server; wrong or two labels in frame -> clear message, never a guess | |
| B5 | Old URL-style QR label | Still resolves | |
| B6 | Phone's own camera app on a direct-link (`/q/...`) QR | Opens the page (needs a stable `SL_PUBLIC_URL`) | |
| B7 | Label with a duplicate production code | Candidate list; you must choose | |

## C. Photos
| # | Step | Expected | Result |
|---|---|---|---|
| C1 | Audit with one camera photo, then with a gallery photo | Saved; photo shown on phone **and** desktop register | |
| C2 | iPhone set to High Efficiency (HEIC): take and upload a photo | Accepted; desktop shows a thumbnail (server has `pillow-heif`) | |
| C3 | Four photos in one submission | All saved; note upload time | |
| C4 | 12 MP photo on factory Wi-Fi | Note seconds from tap to "saved" (cloud emulation: 15 s at 2 Mbps up) | |
| C5 | Photo larger than 8 MB | Rejected with a message, nothing saved | |

## D. GPS and location
| # | Step | Expected | Result |
|---|---|---|---|
| D1 | Allow location when asked | Status CAPTURED with accuracy in metres | |
| D2 | Deny the permission | Status DENIED; the typed/selected location is still required and is used | |
| D3 | Inside the building | Note accuracy; GPS indoors is only a hint, the physical location text is the record | |

## E. Behaviour
| # | Step | Expected | Result |
|---|---|---|---|
| E1 | Part with no WO or QR: unidentified capture with photo and description | Temporary ID `UNID-...`; label printable | |
| E2 | Planning links the temporary ID to a WO | History shows CREATED, LINKED; not double counted | |
| E3 | Two phones submit at the same moment | Two records, no loss | |
| E4 | Role check: operator, management, View Only | Every signed-in role can record, correct and link; the change is stored with user, time and reason (`docs/PERMISSION_MATRIX.md`) | |
| E5 | Open the same part on the desktop | Same photos, location, history | |
| E6 | Thai text in location/notes and in the F1 help | Shown correctly | |

Sign-off: name / date / phone models / OS and browser versions / network. Until this is signed off, the mobile workflow is **verified only in a simulated environment**.
