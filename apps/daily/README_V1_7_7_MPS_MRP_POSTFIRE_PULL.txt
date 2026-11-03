SL PPC DAILY PLANNER V1.7.7

Controlled changes from V1.7.6:
- Dashboard: compact Today/Tomorrow delivery views, clearer delivery-risk table, Stock in Hand graph, Open vs Closed WO graph.
- PCS display: whole-number presentation where appropriate.
- Due-date cohort wording clarified.
- WIP charts converted to interactive Plotly. Category stacked WIP shows only TOTAL labels above stacks; hover shows category/WO/ton detail.
- Operational MRP: interactive quantity graph + PO-to-need timing graph.
- Long-term: Master Production Schedule (MPS) made explicit and detailed by month/product/category/size/customer, with capacity comparisons. MRP follows MPS.
- Stock file is no longer required to build MPS; without verified stock, net MRP is not fabricated.
- Grinding and Cutting are separate post-firing processes.
- Confirmed route rule preserved: CP>1 = Cutting; S/T or Honing/Segment direct to Packing; otherwise Grinding.
- Post-firing rows remain linked to Firing Planner completion + QC + next-working-day pull logic.
- Due date remains first priority. Idle feasible capacity may pull farther-due work; capacity is never exceeded.
