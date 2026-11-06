# RC29.58 — issued plan is a Production instruction

Owner clarification: issued firing dates are targets for Production to achieve, using upstream push/pull and evaluating overtime. Current forming shortages no longer reject an otherwise valid issued commitment. The date and quantity remain in the main Firing Loads and Operator Print. Production Instructions shows the additional forming quantity and required firing date, with exact source rows. Actual output is never invented. Quantities are reserved against remaining firing demand before optimization, including quantities still to be formed.

Physical kiln/program/overlap limits, closed or missing WOs and quantities exceeding remaining demand still produce explicit exceptions. Overtime hours and additional capacity are not assumed approved or calculated without resource inputs. Drying and physical release checks remain separate from the issued production target. Earlier RC29.57 notes describe the superseded formed-WIP rejection policy; this note supersedes that policy only.

Focused regression tests and operational export checks are synthetic, not verification of the older factory workbook named in pasted chat. Other RC29.57 test results/limitations remain applicable; no full factory acceptance is claimed. Extract the new folder and reuse existing CENTRAL_DATA without overwriting it. No private factory files/databases are bundled.

Schedule visibility correction: retained issued targets remain visible in the main schedule even when release checks remain HOLD. This does not release other physically blocked new loads. A dedicated regression checks that distinction. MAKE quantities are shown for retained rows. Pattern verification remains a separate physical check.
