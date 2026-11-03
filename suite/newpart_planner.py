"""New part / project planning and MPS netting - provisional, traceable, never 'confirmed feasible'.

Rules applied (knowledge/approved_rules.json): CAP-1..6, DATE-1, DATA-1, CLOSE-1/2.
* The start date is the CURRENT Asia/Bangkok date (or a later explicit date). No date is read from any earlier order.
* Process lead times come from CAPACITY_DATABASE 'Lead Time' (low/high days, with cell). Capacity is used only where a resource with a matching unit AND
  time basis is chosen; otherwise the step is lead-time only and the gap is listed.
* Existing bookings = open Plan-workbook orders already waiting in a section (pieces) and firing plans not yet closed. They delay the start; they are
  estimates and labelled so.
* Firing needs a part weight at the FIRED stage (pieces -> tonnes), a kiln program (load t/run, days/run) and the kilns allowed to run it.
* Materials: stock minus quantities reserved by open firm orders; forecasts never reserve stock.
* Firm demand and forecast are separate; forecasts are reduced by firm orders of the same product and month so nothing is counted twice (OD-7).
* Calendar: Sunday is non-working (OD-6); holidays are selected by the user. Resin firing applies to PB only (OD-5); mixing is counted in mills per day only (OD-2).
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sqlite3
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import pandas as pd

from .capacity import CapacityModel, MissingConversion, kiln_throughput, pieces_to_kg
from .common import bkk_now, bkk_today

PROCESS_ORDER = [
    ("Preparation", "หน่วยงานเตรียมวัตถุดิบ"), ("Mixing", "หน่วยงานผสม"), ("Forming", "หน่วยงานขึ้นรูป"), ("Drying", "หน่วยงานอบสินค้า"),
    ("Firing", "FIRING"), ("Screening", "หน่วยงานคัดกรอง (T,P)"), ("Grinding", "หน่วยงานเจียร"), ("QC", "หน่วยงานQC ตรวจสอบ"), ("Packaging prep", "หน่วยงานเจียรบรรจุภัณฑ์"),
]
CAP_SECTION = {"Mixing": "Mixing", "Forming": "Forming", "Firing": "Firing", "Grinding": "Grinding", "Packaging prep": "Packing"}
PLAN_SECTION = {"Preparation": "Preparation", "Mixing": "Mixing", "Forming": "Forming", "Firing": "Firing", "Grinding": "Grinding"}
STATUS_BLOCKED = "BLOCKED - required information missing"
STATUS_PROVISIONAL = "PROVISIONAL - not confirmed feasible"
STATUS_LATE = "PROVISIONAL - LATE against requested date, not confirmed feasible"


@dataclass
class Calendar:
    non_working_weekdays: tuple = (6,)        # Mon=0 .. Sun=6; Sunday is non-working (owner decision OD-6, 2026-10-04)
    holidays: tuple = ()                      # chosen by the user per plan (suite/user_settings.py keeps the saved list)
    supplied: bool = True

    def working(self, d: dt.date) -> bool:
        return d.weekday() not in self.non_working_weekdays and d not in self.holidays

    def add(self, d: dt.date, n: int) -> dt.date:
        step = 0
        while step < n:
            d += dt.timedelta(days=1)
            if self.working(d):
                step += 1
        return d

    def first_working(self, d: dt.date) -> dt.date:
        while not self.working(d):
            d += dt.timedelta(days=1)
        return d


@dataclass
class SectionCap:
    section: str
    resource: str
    per_day: float
    unit: str            # 'pcs' | 'mills'
    cell: str            # source cell or 'USER-ENTERED'


@dataclass
class Item:
    item_id: str
    description: str
    group: str                            # S T P R PB M
    qty_pcs: float
    demand_type: str = "FIRM"             # FIRM | FORECAST
    due: Optional[dt.date] = None
    bond_type: Optional[str] = None       # 'Vitrified' | 'Resin' (needed where the lead-time sheet is ambiguous)
    kiln_program: Optional[str] = None    # P1 P2 P3 P3 (T14) P6 KM-185 KM-170
    fired_piece_kg: Optional[float] = None
    mills: Optional[float] = None
    materials: list = field(default_factory=list)       # [(code, total_kg)]
    start_not_before: Optional[dt.date] = None
    material_ready_date: Optional[dt.date] = None
    notes: str = ""


@dataclass
class Context:
    today: dt.date = field(default_factory=bkk_today)
    calendar: Calendar = field(default_factory=Calendar)
    caps: dict = field(default_factory=dict)             # section -> SectionCap
    kilns_out_of_service: tuple = ()
    plan: Optional[pd.DataFrame] = None                  # suite.plan_reader frame (open orders = existing bookings / reservations)
    stock: Optional[pd.DataFrame] = None                 # planners.read_material_stock frame (dated evidence)
    source_revisions: dict = field(default_factory=dict) # slot -> {revision, sha256, imported_at, file}


@dataclass
class PlanResult:
    item: dict
    as_of: str
    status: str
    schedule: pd.DataFrame
    capacity_checks: pd.DataFrame
    bookings: pd.DataFrame
    materials: pd.DataFrame
    bottlenecks: list
    blockers: list
    gaps: list
    assumptions: list
    finish_optimistic: Optional[dt.date]
    finish_conservative: Optional[dt.date]
    late_days: Optional[int]
    sources: dict

    def sheets(self) -> dict:
        info = pd.DataFrame([{"field": k, "value": str(v)} for k, v in self.item.items()] + [
            {"field": "plan generated (Asia/Bangkok date)", "value": self.as_of}, {"field": "STATUS", "value": self.status},
            {"field": "finish - optimistic (lead-time low)", "value": self.finish_optimistic}, {"field": "finish - conservative (lead-time high)", "value": self.finish_conservative},
            {"field": "days late vs requested date (conservative)", "value": self.late_days}])
        return {"Item and result": info, "Schedule": self.schedule, "Capacity checks": self.capacity_checks, "Existing bookings": self.bookings, "Materials": self.materials,
                "Bottlenecks": pd.DataFrame({"bottleneck": self.bottlenecks}), "Blockers": pd.DataFrame({"blocker": self.blockers}), "Gaps": pd.DataFrame({"missing information": self.gaps}),
                "Assumptions": pd.DataFrame({"assumption": self.assumptions}),
                "Sources": pd.DataFrame([{"slot": k, **v} for k, v in self.sources.items()]) if self.sources else pd.DataFrame(columns=["slot"])}


def _lead(model: CapacityModel, proc_th: str, group: str):
    lt = model.lead_times
    r = lt[(lt.process.str.contains(proc_th, regex=False)) & (lt.group == group)]
    return None if r.empty else r.iloc[0]


def route_for(model: CapacityModel, item: Item):
    """Return (steps, blockers). A step = (name, lead_row). Firing row is chosen by bond type where the sheet is ambiguous."""
    steps, blockers = [], []
    both = {c["id"] for c in model.conflicts if c["id"].startswith("LEAD-FIRING-BOTH-")}
    for name, th in PROCESS_ORDER:
        if name == "Firing":
            res, vit = _lead(model, "เตาเผา Resin", item.group), _lead(model, "เตาเผา Vitrified", item.group)
            res_ok, vit_ok = res is not None and res.routed, vit is not None and vit.routed
            if res_ok and vit_ok:
                if f"LEAD-FIRING-BOTH-{item.group}" in both and not item.bond_type:
                    blockers.append(f"Group {item.group} has lead times in both firing rows ({res['cell']}, {vit['cell']}); give the bond type (Vitrified / Resin) or answer the open decision.")
                    continue
                pick = res if (item.bond_type or "").lower().startswith("res") else vit
                steps.append((name, pick))
            elif res_ok or vit_ok:
                steps.append((name, res if res_ok else vit))
            continue
        row = _lead(model, th, item.group)
        if row is not None and row.routed:
            steps.append((name, row))
    return steps, blockers


def _days(row) -> tuple:
    lo, hi = row.days_low, row.days_high
    return (lo if lo == lo else None, hi if hi == hi else None)


def existing_bookings(plan: Optional[pd.DataFrame], today: dt.date) -> pd.DataFrame:
    """Open orders currently waiting in each section = capacity already committed (dated evidence from the Plan workbook)."""
    if plan is None or plan.empty:
        return pd.DataFrame(columns=["section", "open_orders", "pieces_waiting", "earliest_plan_date", "latest_plan_date"])
    rows = []
    op = plan[plan["open"]]
    for name, sec in PLAN_SECTION.items():
        w = op[op["current_section"] == sec]
        rem = [max(0.0, (r.get(f"{sec}.plan_qty", 0) if r.get(f"{sec}.plan_qty", 0) > 0 else r["qty"]) - r.get(f"{sec}.done", 0)) for _, r in w.iterrows()]
        dates = [d for d in (w[f"{sec}.plan"] if f"{sec}.plan" in w else []) if d]
        rows.append({"section": name, "open_orders": len(w), "pieces_waiting": float(sum(rem)), "mills_waiting": float(w["mills"].sum()),
                     "earliest_plan_date": min(dates) if dates else None, "latest_plan_date": max(dates) if dates else None})
    return pd.DataFrame(rows)


def plan_item(model: CapacityModel, item: Item, ctx: Optional[Context] = None) -> PlanResult:
    ctx = ctx or Context()
    today = ctx.today
    cal = ctx.calendar
    blockers, gaps, assumptions, bottlenecks = [], [], [], []
    steps, route_blockers = route_for(model, item)
    blockers += route_blockers
    if item.demand_type.upper() == "FORECAST":
        assumptions.append("Demand type FORECAST: planned for visibility only; it reserves no material and is netted against firm orders before any release.")
    if not cal.supplied:
        gaps.append("Working calendar (days off, holidays, shifts) was not supplied; every calendar day is treated as working, which can make dates optimistic.")
    else:
        names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        assumptions.append("Working calendar: non-working weekdays = " + (", ".join(names[d] for d in cal.non_working_weekdays) or "none") +
                           " (Sunday off per owner decision OD-6); holidays selected: " + (", ".join(h.isoformat() for h in sorted(cal.holidays)) or "none - select any holiday or shutdown in the calendar box") + ".")
    assumptions.append("Lead time (days) from CAPACITY_DATABASE 'Lead Time' is taken as elapsed time for a normal lot; where a chosen resource needs more days for this quantity, the longer value is used.")
    bk = existing_bookings(ctx.plan, today)
    if ctx.plan is None:
        gaps.append("No Plan workbook loaded: existing capacity bookings and material reservations by open orders cannot be considered.")
    start = cal.first_working(max(today, item.start_not_before or today))
    # materials
    mat_rows = []
    for code, kg in item.materials:
        stock_kg = reserved = None
        if ctx.stock is not None and not ctx.stock.empty:
            s = ctx.stock[ctx.stock.material.astype(str).str.strip() == str(code).strip()]
            stock_kg = float(s.stock_g.iloc[0]) / 1000 if not s.empty and s.stock_g.iloc[0] == s.stock_g.iloc[0] and s.stock_g.iloc[0] is not None else None
        if ctx.plan is not None:
            op = ctx.plan[ctx.plan["open"] & ~ctx.plan["Mixing.closed"]]
            reserved = float(sum(op.loc[op[f"mat{n}"].astype(str).str.strip() == str(code).strip(), f"mat{n}_g"].sum() for n in range(1, 6))) / 1000
        avail = None if stock_kg is None else stock_kg - (reserved or 0)
        short = None if avail is None else max(0.0, kg - avail)
        mat_rows.append({"material": code, "need_kg": kg, "stock_kg (dated evidence)": stock_kg, "reserved_by_open_firm_orders_kg": reserved, "available_after_reservations_kg": avail,
                         "shortage_kg": short, "status": "UNKNOWN - no stock figure" if avail is None else ("SHORT" if short and short > 0 else "OK")})
        if avail is None:
            gaps.append(f"Material {code}: no stock figure in the loaded Stock on Hand source.")
        elif short and short > 0 and not item.material_ready_date:
            blockers.append(f"Material {code} short by {short:,.1f} kg after reservations and no material ready date was given (forecasts do not reserve; incoming receipts need a confirmed date).")
    if item.materials == []:
        gaps.append("No material requirement was given for this item (recipe / kg per piece not supplied), so material availability is not checked.")
    ready = item.material_ready_date
    if ready and ready > start:
        start = cal.first_working(ready)
        assumptions.append(f"Start delayed to material ready date {ready}.")
    # schedule, optimistic and conservative
    sched, cap_rows = [], []
    for label, pick in (("optimistic", 0), ("conservative", 1)):
        d = start
        for name, row in steps:
            lo, hi = _days(row)
            base = (lo, hi)[pick] if (lo, hi)[pick] is not None else (hi if hi is not None else lo)
            cap_days, wait_days, extra = 0.0, 0.0, ""
            sec = CAP_SECTION.get(name)
            cap = ctx.caps.get(name) or (ctx.caps.get(sec) if sec else None)
            if name == "Firing":
                fire = _firing(model, item, ctx, bk, pick)
                cap_rows.append(fire["row"]) if label == "conservative" else None
                blockers += [b for b in fire["blockers"] if b not in blockers]
                gaps += [g for g in fire["gaps"] if g not in gaps]
                cap_days, wait_days, extra = fire["run_days"], fire["wait_days"], fire["note"]
            elif cap:
                demand = item.mills if cap.unit == "mills" else item.qty_pcs
                if demand is None:
                    gaps.append(f"{name}: capacity {cap.resource} is in {cap.unit}/day but the item has no {cap.unit} figure.") if f"{name}: capacity {cap.resource}" not in " ".join(gaps) else None
                else:
                    cap_days = math.ceil(demand / cap.per_day)
                    b = bk[bk.section == name]
                    waiting = float(b["mills_waiting" if cap.unit == "mills" else "pieces_waiting"].sum()) if not b.empty else 0.0
                    wait_days = math.ceil(waiting / cap.per_day) if waiting else 0
                    if label == "conservative":
                        cap_rows.append({"step": name, "resource": cap.resource, "capacity": f"{cap.per_day:g} {cap.unit}/day", "source_cell": cap.cell, "item_demand": f"{demand:g} {cap.unit}",
                                         "days_needed_for_item": cap_days, "existing_open_orders_waiting": f"{waiting:g} {cap.unit}", "queue_days_ahead (estimate)": wait_days,
                                         "note": "unit and time basis match; other products/specs on the same resource are not separated"})
            else:
                if label == "conservative" and sec:
                    gaps.append(f"{name}: no capacity with a unit and time basis selected - lead time only.") if f"{name}: no capacity" not in " ".join(gaps) else None
            dur = max(base or 0, cap_days)
            begin = cal.add(d, int(math.ceil(wait_days))) if wait_days else d
            end = cal.add(begin, int(math.ceil(dur))) if dur else begin
            sched.append({"scenario": label, "step": name, "begin": begin, "end": end, "lead_time_days": base, "capacity_days": cap_days or None, "queue_days": wait_days or None,
                          "lead_time_cell": f"Lead Time!{row['cell']}", "lead_time_text": row["raw"], "note": extra})
            d = end
    S = pd.DataFrame(sched)
    fo = S[S.scenario == "optimistic"].end.max() if not S.empty else None
    fc = S[S.scenario == "conservative"].end.max() if not S.empty else None
    late = (fc - item.due).days if (fc and item.due) else None
    if not S.empty:
        cons = S[S.scenario == "conservative"].copy()
        cons["elapsed"] = [(r.end - r.begin).days for r in cons.itertuples()]
        top = cons.sort_values("elapsed", ascending=False).iloc[0]
        bottlenecks.append(f"Longest step (conservative): {top['step']} - {top['elapsed']} calendar days ({top['lead_time_cell']}).")
        for r in cons.itertuples():
            if r.queue_days and r.queue_days > 0:
                bottlenecks.append(f"{r.step}: existing open orders ahead add about {r.queue_days} working days (estimate).")
            if r.capacity_days and r.lead_time_days and r.capacity_days > r.lead_time_days:
                bottlenecks.append(f"{r.step}: this quantity needs {r.capacity_days} days at the chosen capacity, more than the {r.lead_time_days}-day lead time.")
    if item.due and fc and late is not None and late > 0:
        bottlenecks.append(f"Conservative finish {fc} is {late} day(s) after the requested date {item.due}.")
    if item.due is None:
        gaps.append("No requested due date given: lateness cannot be judged.")
    gaps += [g for g in model.gaps if g not in gaps and ("calendar" not in g.lower() or not cal.supplied)]
    status = STATUS_BLOCKED if blockers else (STATUS_LATE if (late is not None and late > 0) else STATUS_PROVISIONAL)
    return PlanResult(asdict(item) | {"due": item.due, "start_not_before": item.start_not_before, "material_ready_date": item.material_ready_date}, today.isoformat(), status, S,
                      pd.DataFrame(cap_rows), bk, pd.DataFrame(mat_rows), bottlenecks, blockers, list(dict.fromkeys(gaps)), assumptions, fo, fc, late, ctx.source_revisions)


def _firing(model, item: Item, ctx: Context, bk: pd.DataFrame, pick: int) -> dict:
    out = {"row": {}, "blockers": [], "gaps": [], "run_days": 0.0, "wait_days": 0.0, "note": ""}
    if not item.kiln_program:
        out["gaps"].append("Firing: kiln program (P1/P2/P3/P6/KM-…) not given, so kiln load and runs are not evaluated.")
        out["note"] = "lead time only (no program)"
        return out
    try:
        kt = kiln_throughput(model, item.kiln_program)
    except MissingConversion as e:
        out["blockers"].append(str(e))
        return out
    if not item.fired_piece_kg:
        out["gaps"].append("Firing: weight per piece at the FIRED stage is missing; pieces cannot be converted to tonnes, so the number of kiln runs is unknown.")
        out["note"] = "lead time only (no fired piece weight)"
        return out
    tonnes = pieces_to_kg(item.qty_pcs, item.fired_piece_kg, "fired", "fired") / 1000.0
    load = kt["t_per_run_low"] if pick == 1 else kt["t_per_run_high"]
    runs = math.ceil(tonnes / load)
    km = model.kiln_machines
    allowed = km[km.programs_allowed.str.contains(item.kiln_program.split()[0], regex=False) & ~km.unit.isin(ctx.kilns_out_of_service)]
    n_k = len(allowed)
    if n_k == 0:
        out["blockers"].append(f"No kiln/oven in the capacity workbook (Cap เตา) is allowed to run program {item.kiln_program}.")
        return out
    rounds = math.ceil(runs / n_k)
    per_run = kt.get("run_days_low", kt["run_days"]) if pick == 0 else kt["run_days"]
    run_days = rounds * per_run
    b = bk[bk.section == "Firing"]
    booked_pcs = float(b.pieces_waiting.sum()) if not b.empty else 0.0
    wait = 0.0
    if booked_pcs and item.fired_piece_kg:
        booked_t = booked_pcs * item.fired_piece_kg / 1000.0
        wait = math.ceil(math.ceil(booked_t / load) / n_k) * per_run
        out["gaps"].append("Firing queue estimate uses this item's piece weight for other orders' pieces (their weights are not separated).") if booked_pcs else None
    out["row"] = {"step": "Firing", "resource": f"{n_k} kilns allowed for {item.kiln_program}", "capacity": f"{load:g} t/run ({'low' if pick else 'high'} end of {kt['t_per_run_low']:g}-{kt['t_per_run_high']:g}); {per_run:g} days/run",
                  "source_cell": kt["basis"], "item_demand": f"{item.qty_pcs:g} pcs x {item.fired_piece_kg:g} kg (fired) = {tonnes:.3f} t", "days_needed_for_item": run_days,
                  "existing_open_orders_waiting": f"{booked_pcs:g} pcs", "queue_days_ahead (estimate)": wait,
                  "note": f"{runs} run(s) over {n_k} kiln(s) = {rounds} round(s). PROVISIONAL: days per run may exclude cooling/unloading; kiln calendar bookings in 'ตารางเตา' hold only zero loads in the supplied workbook."}
    out["run_days"], out["wait_days"], out["note"] = run_days, wait, f"{runs} run(s), {rounds} round(s)"
    return out


# ------------------------------------------------------------------------------------------------ MPS: firm vs forecast
def net_demand(lines: pd.DataFrame) -> pd.DataFrame:
    """lines: product, month (YYYY-MM), qty, type FIRM|FORECAST, reference. Forecast is reduced by firm quantity of the same product+month.
    The method (forecast consumption inside the same month) was confirmed by the owner on 2026-10-04 (OD-7); it is shown on every row."""
    x = lines.copy()
    x["type"] = x["type"].str.upper()
    firm = x[x.type == "FIRM"].groupby(["product", "month"], as_index=False).qty.sum().rename(columns={"qty": "firm_qty"})
    fc = x[x.type == "FORECAST"].groupby(["product", "month"], as_index=False).qty.sum().rename(columns={"qty": "forecast_qty"})
    m = firm.merge(fc, on=["product", "month"], how="outer").fillna(0.0)
    m["forecast_netted_by_firm"] = m[["firm_qty", "forecast_qty"]].min(axis=1)
    m["forecast_remaining"] = m.forecast_qty - m.forecast_netted_by_firm
    m["counted_demand"] = m.firm_qty + m.forecast_remaining
    m["method"] = "forecast consumed by firm orders of the same product and month (confirmed by the owner, OD-7, 2026-10-04)"
    return m.sort_values(["month", "product"]).reset_index(drop=True)


# ------------------------------------------------------------------------------------------------ saved scenarios
class ScenarioStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._c() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS scenarios(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, created_at TEXT NOT NULL, created_by TEXT,
                         state TEXT NOT NULL DEFAULT 'DRAFT', as_of TEXT NOT NULL, status TEXT NOT NULL, inputs TEXT NOT NULL, result TEXT NOT NULL, sources TEXT NOT NULL)""")

    def _c(self):
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        return c

    def save(self, name: str, item: Item, res: PlanResult, ctx: Context, user: str = "") -> int:
        inputs = {"item": asdict(item), "calendar": asdict(ctx.calendar), "caps": {k: asdict(v) for k, v in ctx.caps.items()}, "today": ctx.today.isoformat(),
                  "kilns_out_of_service": list(ctx.kilns_out_of_service)}
        sheets = {k: v.astype(str).to_dict("records") for k, v in res.sheets().items()}
        with self._c() as c:
            cur = c.execute("INSERT INTO scenarios(name,created_at,created_by,as_of,status,inputs,result,sources) VALUES(?,?,?,?,?,?,?,?)",
                            (name, bkk_now().isoformat(timespec="seconds"), user, res.as_of, res.status, json.dumps(inputs, default=str), json.dumps(sheets, default=str, ensure_ascii=False),
                             json.dumps(res.sources, default=str)))
            return cur.lastrowid

    def list(self) -> pd.DataFrame:
        with self._c() as c:
            return pd.DataFrame([dict(r) for r in c.execute("SELECT id,name,created_at,created_by,state,as_of,status FROM scenarios ORDER BY id DESC")])

    def get(self, sid: int) -> dict:
        with self._c() as c:
            r = c.execute("SELECT * FROM scenarios WHERE id=?", (sid,)).fetchone()
        d = dict(r)
        for k in ("inputs", "result", "sources"):
            d[k] = json.loads(d[k])
        return d

    def export_sheets(self, sid: int) -> dict:
        d = self.get(sid)
        out = {k: pd.DataFrame(v) for k, v in d["result"].items()}
        out["Saved scenario"] = pd.DataFrame([{"id": sid, "name": d["name"], "created_at": d["created_at"], "created_by": d["created_by"], "state": d["state"], "as_of": d["as_of"],
                                               "status": d["status"], "inputs": json.dumps(d["inputs"], ensure_ascii=False, default=str)}])
        return out
