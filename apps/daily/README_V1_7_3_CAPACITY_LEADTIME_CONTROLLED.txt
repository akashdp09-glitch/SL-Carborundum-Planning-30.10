SL PPC DAILY PLANNER V1.7.3 — CAPACITY + LEAD TIME CONTROLLED

CONTROLLED SOURCE
Embedded CAPACITY_DATABASE.xlsx is the user's Cap แต่ละแผนก(10).xlsx supplied 10-Sep-2026.
All eight sheets were audited before this release.

SHEET-BY-SHEET ENGLISH SUMMARY
1) CAP ผสม — Mixing capacity
- Active/inactive mixer status, job family, monthly tonnage reference, batches/day (CAP-โม่), machine kg, usable batch range, abrasive compatibility.
- Active examples: M2 P 8 batches/day 30-120kg; M3 P 8; M4 P 10 3-30kg; M5 R 8; M8/M14 P 7 120-280kg; M9/M10/M15 PB.
- Planner uses machine/job/category, active status, batch count, batch range and abrasive match. It does NOT replace batch capacity by a generic pcs/day number.

2) CAP ขึ้นรูป — Forming capacity
- 39 product/spec-size groups with category, eligible forming machines, pcs/hour, normal 8h capacity and 3h OT capacity.
- Examples: T rubber-knife stones H5/H15 100 pcs/h = 800 normal +300 OT; P 2-8in H18/H7 15 pcs/h =120 normal; R KVT H12/H23 4 pcs/h =32 normal; PB lines use H14/H23/H9/H7 with product-specific rates.
- Planner matches spec/category/dimensions and eligible machine. Normal rated capacity is primary; OT is recovery, not normal planning.

3) Cap เตา — Firing/kiln capacity
- A:D is kiln capability, NOT program capacity: T1-T12 support P1/P2/P3/P6; T14 P3 only with note for S/T; R4/R5/R6 KM-185/KM-170.
- F:H is the actual program capacity/duration table: P1 1.2-1.8t 7d; P2 1.2-1.8t 7d; P3 1.3-2.0t 6d; P3(T14) 3.8-4.5t 6d; P6 1.2-1.8t 5d; KM-185 1t 3d; KM-170 1t 3d.
- V1.7.2 incorrectly read A:C as program/capacity/days. V1.7.3 corrects this and keeps the issued Firing Planner as exact kiln-date authority.

4) Cap เจีย — Grinding/Cutting product routing master
- 4,250 product rows and product/spec/category/shape data.
- Product-specific sequential operation-machine-capacity pairs:
  Face grinding DE/DF; Hole operation DG/DH; Edge finishing DI/DJ; Small-shape DK/DL; Large-shape DM/DN; second large-shape DO/DP.
- It is not one generic grinding capacity. V1.7.3 keeps the product-specific route/bottleneck and additionally uses setup/machine status/manpower evidence.

5) Set Up Time, จำนวน พนักงาน เจีย — Grinding setup and machine manpower
- 57 grinding machines/resources.
- Setup time is 0.5 h for listed machines.
- Worker requirement is normally 1 or 2; machines D7,D8,D9,D10,D11,D12,D15,D19,D25,D26,D32 are marked ชำรุด (broken) and must not be treated as available capacity.
- V1.7.3 makes broken required machines a HOLD route and charges setup time against the bottleneck machine-day.

6) Cap บรรจุ — Packing capacity
- Three capacity blocks: S/T product-specific stamping/boxing; P/PB size-based Balance/Speedtest/Stamp/Label+Box; R product-specific Balance/Speedtest/Gasket/Label+Box.
- Planner uses the slowest positive required process as bottleneck pcs/day/person and multiplies by available packing people.
- Current packing manpower default is read from the manpower sheet, not hardcoded to 1.

7) กำลังคนแผนกผลิต — Production manpower
- Planned 95, current 90, gap 5.
- Mixing 7/7; Forming 30 plan/28 current (gap 2); Kiln 12/12; Grinding 30/28 (gap 2); Packing 13/12 (gap 1); Mounted stone 3/3.
- V1.7.3 uses current packing people as default and grinding manpower as a hard daily check for newly activated bottleneck machines. Other departments remain machine/rated-capacity controlled where worker-to-machine mapping is not supplied.

8) Lead Time — Category-specific process lead time
- Categories: S,T,P,R,PB,M. PB is Resin; S/T/P/R/M are Vitrified.
- Preparation 1 day and Mixing 1 day for all categories.
- Forming: S2, T5, P2, R3, PB0.5, M2 days.
- Oven/drying time from CAPACITY_DATABASE.xlsx / Lead Time row 6: S=2, T=3, P=3, R=2, M=1 days; PB does not pass.
- Resin firing: PB 3 days. Source also contains M 5-7 days in this row although M is defined as Vitrified; retained as an audit conflict, not used to reclassify M.
- Vitrified firing: S5, T5, P7, R7, M7 days.
- Screening row: 1 day across table.
- Grinding: P6, R6, PB3, M3 days; S/T do not pass.
- QC: 0.5 day all categories.
- Grinding/Packing: 4 days all categories.
- Applied upstream scheduling gates: Prep→Mix = 1 WD; Mix→Form = 1 WD; Form→Fire = ceil(Forming + Oven), minimum 1 WD. Actual firing dates/finish dates are still controlled by the issued Firing Planner.
- Post-firing fixed lead-time values are exported for audit, while daily executable quantities remain governed by matched CAP/day and manpower so the planner does not double-count fixed lead time plus rated daily capacity.

RELEASE PRINCIPLES
- Due date protection first.
- Capacity/resource feasibility is mandatory; no overcapacity release.
- Existing WIP is executable at its current process subject to capacity.
- New quantity follows the controlled working-day gates above.
- Firing plan is the anchor for upstream pull and downstream flow.
- Sunday is non-working.
- OT is recovery only when required; normal plan uses normal capacity.
