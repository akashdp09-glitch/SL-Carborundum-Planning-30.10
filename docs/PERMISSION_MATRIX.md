# Shared account and tracking permissions — RC29.54

The owner's recorded decision OD-8 allows identified signed-in users to capture, correct and link tracking evidence across sections. Server authentication is required; screen size is not an authorization boundary. An anonymous hub visitor is read-only.

| Action | Signed-in users | Anonymous |
|---|---|---|
| Exact scan/search and inspect permitted records | Yes | No mobile access |
| Section OPEN/CLOSED, WIP audit and photos | Yes, actor/time/source retained | No |
| Production events | Yes, active station, explicit quantities and reason checks | No |
| Confirm actual drying readiness | Yes on desktop, source/reason required | No |
| Correct/link an audit record | Existing reasoned edit/link flow, with retained history | No |
| See user account register | Yes on desktop; no password/hash disclosure | No |
| Administrative terminal/import operations | Existing server role checks remain | No |

New missing accounts: production, preparation, mixing, forming, firing, grinding, cutting, packing, qc, warehouse, dispatch. Section accounts have production role and a matching entry default, but may explicitly choose another section. Existing credentials and inactive flags are preserved. Defaults for new accounts only are in `user details.txt`.

Section completion does not close the whole WO. Physical observations do not add production. Final workbook KPI actual output remains `Pack จ่าย` only.
