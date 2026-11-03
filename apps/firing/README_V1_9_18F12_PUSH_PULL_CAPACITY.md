# V1.9.18F12 — Downstream Pull / Upstream Push Capacity Logic

## Factory planning principle
The firing plan is the downstream constraint and therefore provides the **PULL signal**. Upstream Preparation → Mixing → Forming provides the **PUSH requirement** needed to support that firing date.

The planner must not treat current firing-ready WIP as the only demand that can be planned. If compatible demand exists and the kiln has physical capacity, the planner should pull the next compatible demand forward into the same firing load and create the corresponding upstream make requirement.

## Required sequence
1. **Customer due date / delivery protection** remains the first priority.
2. **Downstream firing capacity** is evaluated using kiln availability, program compatibility, weight, furniture, geometry, height and occupancy.
3. **Ready WIP** is used first where feasible.
4. If ready quantity is smaller than the physically useful load, the planner **pulls compatible same-program open demand** from the due-date queue to use the available kiln capacity.
5. The exact furniture packer is authoritative. If it trims the fast-screen quantity, the freed space is immediately offered to the remaining same-program demand instead of waiting until the next day.
6. Every pulled quantity that is not currently ready creates an **upstream PUSH** requirement: Preparation → Mixing → Forming by the dates required to support firing.
7. A small load is accepted only when a documented physical, weight, program, kiln-availability, due-date, or demand constraint prevents further pull.

## Important correction
Previous fast planning could lose capacity after exact furniture reconciliation. Example: fast screen selected 1,000 pcs, exact furniture could physically fit only 650 pcs, but the remaining 350 pcs of capacity were not refilled until the next planning day. This could produce an unnecessarily small load even when another compatible WO was available.

V1.9.18F12 adds an exact-pack **PULL REFILL** step. It first checks the trimmed balance of selected WOs, then checks the next same-program WOs in due-date order.

## Capacity interpretation
Capacity is not only a single kg number. The firing load is limited by the combination of:
- kiln availability / cycle time;
- program compatibility;
- maximum weight;
- physical furniture and plate support;
- footprint / geometry;
- usable height / stacking;
- target occupancy;
- daily start limits;
- compatible open demand.

The planner should therefore prefer a physically useful combined load rather than repeatedly producing small loads followed by larger loads on the next day.

## Push / pull terminology in output
- **PULL:** downstream firing capacity reserves a compatible load from open demand.
- **PUSH:** upstream process quantities and target dates are created to support that firing load.
- **READY / RELEASE:** current verified formed quantity can support the planned firing quantity.
- **PLANNED — UPSTREAM CAPACITY COMMITMENT:** firing slot is reserved and upstream production must supply the missing quantity before firing.
- **PULL REFILL pcs:** quantity added after exact furniture reconciliation to recover otherwise-unused physical capacity.
