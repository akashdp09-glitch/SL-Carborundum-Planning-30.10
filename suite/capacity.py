"""Capacity registry read from CAPACITY_DATABASE.xlsx.

Rules (approved factory requirements):
* every value keeps its SOURCE unit and TIME BASIS and its source file / sheet / cell;
* tonnes, pieces, mill counts, persons and days are different unit kinds and are NEVER added together;
* utilisation is calculated separately per (section, unit kind) and only against demand expressed in the same unit kind;
* a mill count is not assumed to be batches per day;
* mixing capacity is the number of mills per day ONLY (owner decision OD-2); tonnes/month and kg/day of the mixing sheet are reference values;
* tonnes -> kg only with the documented conversion in ``TONNE_TO_KG``; pieces -> kg only with a part-specific weight at the
  matching process stage (``pieces_to_kg``);
* a value without a time basis cannot be scheduled - it is reported in ``gaps``.

Pure Python + openpyxl (no Streamlit) so it can be tested headless.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable, Optional

import openpyxl
import pandas as pd

TONNE_TO_KG = 1000.0
TONNE_CONVERSION_NOTE = (
    "Thai 'ตัน' = metric tonne (1 t = 1,000 kg). The workbook does not print the definition; the factory owner confirmed it on 2026-10-04 (decision OD-1)."
)
OWNER_REF = "owner decision 2026-10-04"
FORMING_RATE_ROWS = (28, 33, 38, 40, 41, 42, 43)      # OD-3: the hourly rate (column E) is the approved figure on these sheet rows
RESIN_GROUPS = ("PB",)                                  # OD-5: the Resin firing row applies to PB only
RESIN_RUN_DAYS_OWNER = 2.0                              # OD-5: owner-stated resin firing running time (days)

KIND_MASS_T = "mass_tonne"
KIND_MASS_KG = "mass_kg"
KIND_PIECES = "pieces"
KIND_MILLS = "mill_count"
KIND_PERSONS = "persons"
KIND_DAYS = "duration_days"
KIND_EQUIPMENT = "equipment_count"
KIND_HOURS = "duration_hours"
KIND_UNKNOWN = "unknown"

MIX_REF_NOTE = "Reference only: mixing capacity is the number of mills per day (" + OWNER_REF + "); this figure is not used to schedule and is not converted."
SHEET_MIX = "CAP ผสม"
SHEET_FORM = "CAP ขึ้นรูป"
SHEET_KILN = "Cap เตา"
SHEET_GRIND = "Cap เจีย"
SHEET_SETUP = "Set Up Time, จำนวน พนักงาน เจีย"
SHEET_PACK = "Cap บรรจุ"
SHEET_STAFF = "กำลังคนแผนกผลิต"
SHEET_LEAD = "Lead Time"

SECTION_OF_SHEET = {SHEET_MIX: "Mixing", SHEET_FORM: "Forming", SHEET_KILN: "Firing", SHEET_GRIND: "Grinding",
                    SHEET_SETUP: "Grinding", SHEET_PACK: "Packing", SHEET_STAFF: "All", SHEET_LEAD: "All"}


class MissingConversion(ValueError):
    """Raised instead of guessing a unit conversion."""


@dataclass
class CapRecord:
    section: str
    resource: str
    measure: str            # what the number is (e.g. 'nominal mass per day')
    value: Optional[float]
    value_max: Optional[float]
    unit: str               # unit exactly as read (t, kg, pcs, mills, persons, days)
    unit_kind: str
    time_basis: str         # per day / per month / per hour / per firing run / per 8h shift ... or UNSTATED
    source_file: str
    sheet: str
    cell: str
    raw: str = ""
    attributes: dict = field(default_factory=dict)   # compatible materials, staffing, status, machine list ...
    assumptions: list = field(default_factory=list)
    flags: list = field(default_factory=list)       # e.g. TIME_BASIS_UNSTATED, UNIT_ASSUMED, SEMANTICS_UNCONFIRMED
    schedulable: bool = True

    def as_row(self) -> dict:
        d = asdict(self)
        d["attributes"] = "; ".join(f"{k}={v}" for k, v in self.attributes.items() if v not in (None, ""))
        d["assumptions"] = " | ".join(self.assumptions)
        d["flags"] = ", ".join(self.flags)
        return d


@dataclass
class CapacityModel:
    source_file: str
    records: list
    conflicts: list        # exact conflicting entries (cells + values)
    gaps: list             # information required to schedule but absent from the workbook
    lead_times: pd.DataFrame
    kiln_programs: pd.DataFrame
    kiln_machines: pd.DataFrame
    resolved: list = field(default_factory=list)       # conflicts closed by an owner decision (kept for traceability)
    out_of_service: list = field(default_factory=list)  # capacity rows excluded because the machine is not working now

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame([r.as_row() for r in self.records])

    def by_section(self, section: str, kind: Optional[str] = None) -> list:
        return [r for r in self.records if r.section == section and (kind is None or r.unit_kind == kind)]


# ----------------------------------------------------------------------------------------------------------- helpers
def _num(v) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _range(text) -> tuple[Optional[float], Optional[float]]:
    """'1.2-1.8' / 'ตั้งแต่ 30-120 Kg' / 1 -> (low, high)."""
    if text is None:
        return None, None
    if isinstance(text, (int, float)):
        return float(text), float(text)
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", str(text))]
    if not nums:
        return None, None
    return nums[0], nums[-1]


def pieces_to_kg(pieces: float, part_weight_kg: Optional[float], part_stage: Optional[str], capacity_stage: Optional[str]) -> float:
    """Pieces -> kg ONLY with a part-specific weight measured at the same process stage as the capacity figure."""
    if part_weight_kg is None or part_weight_kg <= 0:
        raise MissingConversion("No part-specific weight supplied; cannot convert pieces to kg.")
    if not part_stage or not capacity_stage or part_stage.strip().lower() != capacity_stage.strip().lower():
        raise MissingConversion(f"Part weight is for stage '{part_stage}' but the capacity stage is '{capacity_stage}'; weights differ by stage "
                                "(green / fired / finished). No conversion applied.")
    return pieces * part_weight_kg


def tonnes_to_kg(t: float) -> float:
    return t * TONNE_TO_KG


# ----------------------------------------------------------------------------------------------------------- readers
def _read_mixing(ws, src, recs, conflicts, resolved):
    last_name = None
    extra: dict = {}
    for r in range(3, ws.max_row + 1):
        name = ws.cell(r, 1).value
        job = ws.cell(r, 4).value
        status = ws.cell(r, 2).value
        if not name and not job:
            continue
        if name in (None, "") or str(name).startswith("15 "):
            if job and last_name:
                extra.setdefault(last_name, []).append(f"{ws.title}!D{r}: {job}")
            continue
        name = str(name).strip()
        last_name = name
        attrs = {"status": status, "job": job, "staff_on_machine": _num(ws.cell(r, 3).value), "compatible_abrasive": ws.cell(r, 9).value}
        in_use = status is not None and "ไม่ใช้" not in str(status)
        if name == "ชั่ง":
            v = _num(ws.cell(r, 3).value)
            if v is not None:
                recs.append(CapRecord("Mixing", "ชั่ง (weighing)", "weighing staff", v, None, "persons", KIND_PERSONS, "UNSTATED", src, ws.title, f"C{r}",
                                      str(ws.cell(r, 3).value), {"job": job}, [], ["TIME_BASIS_UNSTATED"], False))
            continue
        if not in_use:
            attrs["note"] = "Marked 'ไม่ใช้' (not in use) in the workbook; excluded from available capacity"
        tonnes = _num(ws.cell(r, 5).value)
        if tonnes is not None:
            recs.append(CapRecord("Mixing", name, "capacity per month (header: ตันต่อเดือน)", tonnes, None, "t", KIND_MASS_T, "per month", src, ws.title, f"E{r}",
                                  str(ws.cell(r, 5).value), dict(attrs), [TONNE_CONVERSION_NOTE, MIX_REF_NOTE], ["UNIT_CONFIRMED_METRIC_TONNE", "REFERENCE_ONLY"], False))
        mills = _num(ws.cell(r, 6).value)
        if mills is not None:
            recs.append(CapRecord("Mixing", name, "mills per day (header: CAP-โม่ / วัน)", mills, None, "mills", KIND_MILLS, "per day", src, ws.title, f"F{r}",
                                  str(ws.cell(r, 6).value), dict(attrs),
                                  ["A mill count is not converted to batches per day, kg or tonnes. Per the " + OWNER_REF + ", mixing capacity is the number of mills per day only."],
                                  ["OWNER_CONFIRMED_UNIT"], in_use))
        kg = _num(ws.cell(r, 7).value)
        if kg is not None:
            recs.append(CapRecord("Mixing", name, "machine nominal capacity (header: CAP-เครื่อง(kg) / วัน)", kg, None, "kg", KIND_MASS_KG, "per day", src, ws.title, f"G{r}",
                                  str(ws.cell(r, 7).value), dict(attrs), [MIX_REF_NOTE], ["REFERENCE_ONLY"], False))
        lo, hi = _range(ws.cell(r, 8).value)
        if lo is not None:
            recs.append(CapRecord("Mixing", name, "usable load window (header: CAP-ใช้จริง(kg) / วัน)", lo, hi, "kg", KIND_MASS_KG, "per day (header) - but value is a load window",
                                  src, ws.title, f"H{r}", str(ws.cell(r, 8).value), dict(attrs),
                                  ["Header says '/ วัน' but the value is a 'from a-b kg' window; read as the load range one mill can take, not a daily total."],
                                  ["TIME_BASIS_AMBIGUOUS", "MILL_LOAD_WINDOW"], False))
    for rec in recs:
        if rec.section == "Mixing" and rec.resource in extra:
            rec.attributes["additional_jobs_listed_below_machine"] = "; ".join(extra[rec.resource])
    # The tonnes/month vs mills/day x kg/day disagreement is closed by the owner decision OD-2; the exact entries stay on record.
    rows = []
    for r in range(3, ws.max_row + 1):
        name, t, m, kg = ws.cell(r, 1).value, _num(ws.cell(r, 5).value), _num(ws.cell(r, 6).value), _num(ws.cell(r, 7).value)
        if name and t and m and kg:
            rows.append((str(name), r, t, m, kg, t * TONNE_TO_KG / (kg * m)))
    if rows:
        days = [x[5] for x in rows]
        resolved.append({
            "id": "MIX-MONTH-vs-DAY", "sheet": ws.title,
            "entries": [f"{n}: E{r}={t} t/month, F{r}={m} mills/day, G{r}={kg} kg/day -> E/(F*G) = {d:.2f} working days" for n, r, t, m, kg, d in rows],
            "issue": f"Tonnes/month, mills/day and kg/day did not agree ({min(days):.2f} to {max(days):.2f} implied working days).",
            "decision": "OD-2 (owner 2026-10-04): mixing is in number of mills per day only. E and G are reference values and are not used for scheduling or converted.",
        })


def _read_forming(ws, src, recs, conflicts, resolved, out_of_service, out_of_service_cells=()):
    for r in range(5, ws.max_row + 1):
        no, spec, grp, mc, hr, n8, n3 = (ws.cell(r, c).value for c in range(1, 8))
        if no is None or spec is None:
            continue
        e = _num(hr)
        f, g = _num(n8), _num(n3)
        note = ws.cell(r, 8).value
        base_attrs = {"group": grp, "machines": str(mc).strip() if mc else None, "spec": str(spec).strip(), "note": note, "no": no}
        rate_rule = r in FORMING_RATE_ROWS
        oos = f"D{r}" in out_of_service_cells
        first = len(recs)
        ref_cols = set()
        if e is not None:
            recs.append(CapRecord("Forming", f"{str(mc).strip()} | {str(spec).strip()}", "rate (header: Cap./Hr.)", e, None, "pcs", KIND_PIECES, "per hour", src, ws.title,
                                  f"E{r}", str(hr), dict(base_attrs),
                                  ["Unit not printed in the header; read as pieces because F = E x 8 and G = E x 3 on every row (see checks)."],
                                  ["UNIT_INFERRED_PIECES"]))
        if f is not None:
            recs.append(CapRecord("Forming", f"{str(mc).strip()} | {str(spec).strip()}", "normal shift output (8 Hr. 08.00-17.00)", f, None, "pcs", KIND_PIECES,
                                  "per 8h normal shift (08.00-17.00)", src, ws.title, f"F{r}", str(n8), dict(base_attrs), [], ["UNIT_INFERRED_PIECES"]))
        if g is not None:
            recs.append(CapRecord("Forming", f"{str(mc).strip()} | {str(spec).strip()}", "overtime output (3 Hr. 17.30-20.30)", g, None, "pcs", KIND_PIECES,
                                  "per 3h overtime block (17.30-20.30)", src, ws.title, f"G{r}", str(n3), dict(base_attrs), [], ["UNIT_INFERRED_PIECES", "OVERTIME_ONLY"]))
        for label, col, val, mult in (("F (8 Hr.)", "F", f, 8), ("G (3 Hr.)", "G", g, 3)):
            if e is not None and val is not None:
                exp = e * mult
                if abs(exp - val) > 1e-9:
                    rel = abs(exp - val) / exp if exp else 1
                    if rate_rule and rel > 0.06:
                        resolved.append({"id": f"FORM-{col}{r}", "sheet": ws.title, "entries": [f"E{r}={e} /hr", f"{col}{r}={val}", f"E{r} x {mult} = {exp:g}"],
                                         "issue": f"{label} differs from Cap./Hr. x {mult} by {abs(exp - val):g} pcs ({rel:.1%}).",
                                         "decision": f"OD-3 (owner 2026-10-04): the hourly rate E{r} is correct for sheet row {r}; {col}{r} is reference only."})
                        ref_cols.add(col)
                        continue
                    conflicts.append({
                        "id": f"FORM-{col}{r}", "sheet": ws.title,
                        "entries": [f"E{r}={e} /hr", f"{col}{r}={val}", f"E{r} x {mult} = {exp:g}"],
                        "issue": f"{label} differs from Cap./Hr. x {mult} by {abs(exp - val):g} pcs ({rel:.1%}).",
                        "severity": "rounding" if rel <= 0.06 else "conflict",
                        "decision_needed": None if rel <= 0.06 else f"Which is approved for row {no} ({str(spec).strip()}): the hourly rate or the shift total?",
                    })
        for rec in recs[first:]:
            if rec.cell[:1] in ref_cols:
                rec.schedulable = False
                rec.flags.append("REFERENCE_ONLY_RATE_AUTHORITATIVE")
                rec.assumptions.append(f"Reference only: for sheet row {r} the hourly rate E{r} is the approved figure ({OWNER_REF}, OD-3).")
            if oos:
                rec.schedulable = False
                rec.attributes["status"] = "ไม่ใช้"
                rec.attributes["out_of_service"] = f"machine cell D{r} ({base_attrs['machines']}) is not working now ({OWNER_REF}, OD-4; editable in the application)"
                rec.flags.append("OUT_OF_SERVICE")
        if oos:
            out_of_service.append({"cell": f"D{r}", "machines": base_attrs["machines"], "spec": base_attrs["spec"], "group": grp, "sheet": ws.title,
                                   "rate_per_hour": e, "reason": f"{OWNER_REF}: not working now"})


def _read_kiln(ws, src, recs, conflicts, gaps):
    programs = []
    for r in range(2, ws.max_row + 1):
        prog, load, days = ws.cell(r, 6).value, ws.cell(r, 7).value, ws.cell(r, 8).value
        if prog in (None, ""):
            continue
        lo, hi = _range(load)
        programs.append({"program": str(prog), "load_t_low": lo, "load_t_high": hi, "cycle_days": _num(days), "load_cell": f"G{r}", "days_cell": f"H{r}", "row": r})
        if lo is not None:
            recs.append(CapRecord("Firing", f"program {prog}", "load per firing run (header: จำนวนบรรจุ (ตัน))", lo, hi, "t", KIND_MASS_T, "per firing run", src, ws.title, f"G{r}",
                                  str(load), {"program": prog}, [TONNE_CONVERSION_NOTE], ["UNIT_CONFIRMED_METRIC_TONNE"], True))
        if _num(days) is not None:
            recs.append(CapRecord("Firing", f"program {prog}", "firing duration (header: จำนวนวันที่เผา (วัน))", _num(days), None, "days", KIND_DAYS, "per firing run", src, ws.title,
                                  f"H{r}", str(days), {"program": prog},
                                  ["Whether the days include loading, cooling and unloading is not stated."], ["INCLUDES_COOLING_UNSTATED"], True))
    machines = []
    for r in range(2, ws.max_row + 1):
        kind, no, progs, note = (ws.cell(r, c).value for c in range(1, 5))
        if no in (None, ""):
            continue
        machines.append({"type": kind, "unit": str(no), "programs_allowed": str(progs or ""), "note": note, "cell": f"B{r}"})
        recs.append(CapRecord("Firing", f"{kind} {no}", "units available (count)", 1, None, "kiln" if kind == "Kiln" else "oven", KIND_EQUIPMENT,
                              "n/a", src, ws.title, f"B{r}", str(no), {"programs_allowed": progs, "restriction": note}, [], ["EQUIPMENT_LIST"], False))
    # programs referenced by kilns but not defined in the program table
    defined = {re.split(r"\s", p["program"])[0] for p in programs}
    for m in machines:
        for p in [x.strip() for x in m["programs_allowed"].split(",") if x.strip()]:
            if p not in defined and p not in ("KM-185", "KM-170"):
                conflicts.append({"id": f"KILN-PROG-{m['unit']}-{p}", "sheet": ws.title, "entries": [f"{m['cell']}: {m['unit']} allows program {p}"],
                                  "issue": f"Program {p} is allowed but no load/duration row exists in F:H.", "decision_needed": f"Give the load (t) and days for program {p}."})
    gaps.append("Firing: cooling/unloading time and kiln-specific loading limits are not in the workbook; per-kiln calendars/maintenance are only in the Plan workbook sheet 'ตารางเตา'.")
    return pd.DataFrame(programs), pd.DataFrame(machines)


def _read_grinding(ws, src, recs):
    from openpyxl.utils import column_index_from_string as ci, get_column_letter as gl
    pairs = [("บดหน้า", "DE", "DF"), ("หยอดรู", "DG", "DH"), ("แต่งขอบ", "DI", "DJ"), ("รูปทรงเล็ก", "DK", "DL"), ("รูปใหญ่-1", "DM", "DN"), ("รูปใหญ่-1 (second block)", "DO", "DP")]
    agg: dict = {}
    for r in range(3, ws.max_row + 1):
        for op, mcol, ccol in pairs:
            m = ws.cell(r, ci(mcol)).value
            c = _num(ws.cell(r, ci(ccol)).value)
            if m in (None, 0, "") or c in (None, 0.0):
                continue
            key = (op, str(m).strip(), c)
            a = agg.setdefault(key, {"n": 0, "first_row": r, "mcol": mcol, "ccol": ccol})
            a["n"] += 1
    for (op, m, c), a in sorted(agg.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2])):
        recs.append(CapRecord("Grinding", f"{m} | {op}", f"{op} capacity per day (header: CAP/ Day)", c, None, "pcs", KIND_PIECES, "per day", src, ws.title,
                              f"{a['ccol']}{a['first_row']}", str(c),
                              {"machine": m, "operation": op, "product_rows": a["n"], "machine_cell": f"{a['mcol']}{a['first_row']}"},
                              ["Per product row of the production register; unit not printed, read as pieces/day."], ["UNIT_INFERRED_PIECES"]))


def _read_setup(ws, src, recs):
    for r in range(2, ws.max_row + 1):
        m, setup, staff = ws.cell(r, 2).value, _num(ws.cell(r, 3).value), _num(ws.cell(r, 4).value)
        if not m:
            continue
        if setup is not None:
            recs.append(CapRecord("Grinding", str(m), "set-up time (header: SetUp Time (ชั่วโมง))", setup, None, "h", KIND_HOURS, "per set-up", src, ws.title,
                                  f"C{r}", str(ws.cell(r, 3).value), {}, [], ["SETUP_HOURS"], False))
        if staff is not None:
            recs.append(CapRecord("Grinding", str(m), "operators per machine", staff, None, "persons", KIND_PERSONS, "per machine", src, ws.title, f"D{r}",
                                  str(ws.cell(r, 4).value), {}, [], [], False))


def _read_packing(ws, src, recs):
    block = None
    heads: dict = {}
    for r in range(1, ws.max_row + 1):
        a = ws.cell(r, 1).value
        if a == "ขนาด":
            block = r
            heads = {c: str(ws.cell(r, c).value) for c in range(3, 7) if ws.cell(r, c).value}
            continue
        if block is None or a is None or str(a).startswith("Cap"):
            continue
        grp = ws.cell(r, 2).value
        for c, head in heads.items():
            v = _num(ws.cell(r, c).value)
            if v is None:
                continue
            per_person = "/คน" in head
            recs.append(CapRecord("Packing", f"{str(a).strip()} ({grp})", head, v, None, "pcs", KIND_PIECES, "per day per person" if per_person else "per day", src, ws.title,
                                  f"{openpyxl.utils.get_column_letter(c)}{r}", str(ws.cell(r, c).value), {"size": str(a).strip(), "group": grp, "per_person": per_person},
                                  ["Per-person figures need the headcount in 'กำลังคนแผนกผลิต' to become a section total."] if per_person else [], []))


def _read_staff(ws, src, recs):
    for r in range(4, ws.max_row + 1):
        dept = ws.cell(r, 1).value
        if not dept or str(dept).strip() == "รวม":
            continue
        for col, label in ((2, "planned headcount"), (3, "current headcount"), (4, "additional required")):
            v = _num(ws.cell(r, col).value)
            if v is not None:
                recs.append(CapRecord("All", str(dept).strip(), label, v, None, "persons", KIND_PERSONS, "monthly summary (title: เดือนกรกฎาคม)", src, ws.title,
                                      f"{openpyxl.utils.get_column_letter(col)}{r}", str(ws.cell(r, col).value), {"remark": ws.cell(r, 5).value},
                                      ["Sheet title says the figures are for July; no later headcount supplied."], ["DATED_OPERATIONAL_EVIDENCE"], False))


def _read_lead(ws) -> pd.DataFrame:
    heads = [str(ws.cell(2, c).value or "").strip() for c in range(2, 8)]
    rows = []
    for r in range(3, 13):
        proc = ws.cell(r, 1).value
        if not proc:
            continue
        for i, grp in enumerate(heads):
            raw = ws.cell(r, 2 + i).value
            txt = str(raw).strip() if raw is not None else ""
            routed = "ไม่ผ่าน" not in txt
            lo, hi = _range(txt) if routed else (None, None)
            rows.append({"process": str(proc).strip(), "group": grp.replace("กลุ่ม", "").strip(), "routed": routed, "days_low": lo, "days_high": hi,
                         "raw": txt, "cell": f"{openpyxl.utils.get_column_letter(2 + i)}{r}", "sheet": ws.title})
    return pd.DataFrame(rows)


def load_capacity(path, out_of_service_cells=None) -> CapacityModel:
    """out_of_service_cells: cells of the 'M/C.' column on sheet CAP ขึ้นรูป whose machines are not working (default = the owner's list OD-4)."""
    if out_of_service_cells is None:
        from .user_settings import default_out_of_service
        out_of_service_cells = default_out_of_service()
    path = Path(path)
    wb = openpyxl.load_workbook(path, data_only=True)
    src = path.name
    recs: list = []
    conflicts: list = []
    resolved: list = []
    oos_rows: list = []
    gaps: list = []
    kp, km = pd.DataFrame(), pd.DataFrame()
    lead = pd.DataFrame()
    if SHEET_MIX in wb.sheetnames:
        _read_mixing(wb[SHEET_MIX], src, recs, conflicts, resolved)
    if SHEET_FORM in wb.sheetnames:
        _read_forming(wb[SHEET_FORM], src, recs, conflicts, resolved, oos_rows, tuple(out_of_service_cells))
    if SHEET_KILN in wb.sheetnames:
        kp, km = _read_kiln(wb[SHEET_KILN], src, recs, conflicts, gaps)
    if SHEET_GRIND in wb.sheetnames:
        _read_grinding(wb[SHEET_GRIND], src, recs)
    if SHEET_SETUP in wb.sheetnames:
        _read_setup(wb[SHEET_SETUP], src, recs)
    if SHEET_PACK in wb.sheetnames:
        _read_packing(wb[SHEET_PACK], src, recs)
    if SHEET_STAFF in wb.sheetnames:
        _read_staff(wb[SHEET_STAFF], src, recs)
    if SHEET_LEAD in wb.sheetnames:
        lead = _read_lead(wb[SHEET_LEAD])
    if not lead.empty:
        lead["owner_note"] = ""
        lead["ignored_raw"] = ""
        is_res = lead.process.str.contains("เตาเผา Resin")
        for i in lead[is_res & lead.routed & ~lead.group.isin(RESIN_GROUPS)].index:
            row = lead.loc[i]
            resolved.append({"id": f"LEAD-FIRING-BOTH-{row['group']}", "sheet": SHEET_LEAD,
                             "entries": [f"{row['cell']}: {row['process']} / group {row['group']} = {row['raw']}"],
                             "issue": f"The Resin firing row has a value for group {row['group']} although the row is labelled for PB only.",
                             "decision": f"OD-5 (owner 2026-10-04): resin firing is for the PB category only; {row['cell']} is ignored for group {row['group']}."})
            lead.loc[i, ["routed", "days_low", "days_high"]] = [False, None, None]
            lead.loc[i, "ignored_raw"] = row["raw"]
            lead.loc[i, "owner_note"] = "Ignored: Resin firing applies to PB only (OD-5)"
        for i in lead[is_res & lead.routed & lead.group.isin(RESIN_GROUPS)].index:
            row = lead.loc[i]
            lo = RESIN_RUN_DAYS_OWNER if row["days_low"] is None or row["days_low"] != row["days_low"] else min(RESIN_RUN_DAYS_OWNER, row["days_low"])
            lead.loc[i, "days_low"] = lo
            lead.loc[i, "owner_note"] = f"Optimistic = owner's resin running time {RESIN_RUN_DAYS_OWNER:g} days (OD-5); conservative = workbook {row['raw']}"
            hv = row["days_high"] if row["days_high"] == row["days_high"] else None
            if hv is not None and hv != RESIN_RUN_DAYS_OWNER:
                conflicts.append({"id": f"RESIN-RUN-DAYS-{row['group']}", "sheet": SHEET_LEAD,
                                  "entries": [f"{row['cell']}: {row['process']} / group {row['group']} = {row['raw']}", "Cap เตา!H7 (KM-185) = 3 days, Cap เตา!H8 (KM-170) = 3 days",
                                              f"Owner (2026-10-04): resin firing running time {RESIN_RUN_DAYS_OWNER:g} days"],
                                  "issue": "The workbook gives 3 days for resin firing; the owner stated a running time of 2 days.",
                                  "decision_needed": "Is 2 days the kiln RUN time inside a 3-day lead time (loading / cooling / unloading), or should 2 days replace the 3 days? "
                                                     "Until answered the planner shows 2 days as the optimistic and 3 days as the conservative figure."})
    gaps += [
        "Mixing: capacity is the number of mills per day only (owner decision OD-2); batch size, cycle time and kg per mill are neither used nor converted.",
        "Mixing/Forming/Grinding: shift patterns are given only for Forming (normal 08.00-17.00, overtime 17.30-20.30); no shift data for other sections.",
        "Drying (อบสินค้า) and cooling: only lead times in days exist ('Lead Time' sheet); no oven/drier capacity figures.",
        "Working calendar: Sunday is non-working (owner OD-6); public holidays and shutdown days are chosen by the user per plan and are not in any supplied file.",
        "Forming machines marked not working (OD-4) are cell-specific: the same machine codes also appear on rows that were not listed, so those rows stay in service until the owner says otherwise.",
        "Material availability and existing reservations are dated operational data (stock / Plan workbook) and are supplied separately at planning time.",
        "Part weights per stage (green / fired / finished) are required to convert pieces to kg; they exist per order in the Plan workbook but are not capacity data.",
    ]
    for r in recs:
        if r.time_basis in ("UNSTATED",):
            r.schedulable = False
    return CapacityModel(src, recs, conflicts, gaps, lead, kp, km, resolved, oos_rows)


# ------------------------------------------------------------------------------------------------ utilisation
@dataclass
class Demand:
    section: str
    amount: float
    unit_kind: str
    unit: str
    period: str            # 'day' | 'month'
    source: str = ""
    note: str = ""
    resource: Optional[str] = None      # exact resource label (e.g. 'M8', 'Forming machine | spec'); required where rows are alternatives
    measure_contains: Optional[str] = None   # pick one measure of the resource (e.g. 'machine nominal')
    headcount: Optional[float] = None   # needed for 'per person' capacity


# Sections whose rows are PARALLEL equal-purpose resources, so adding them across resources is valid inside one unit kind.
# Forming / Grinding / Packing rows are per product spec / operation (alternatives) and are never summed across rows.
ADDITIVE_SECTIONS = {("Mixing", KIND_MILLS, "mills per day")}


def _to_day(value: float, basis: str, working_days_per_month: Optional[float]) -> tuple[Optional[float], str]:
    b = basis.lower()
    if b.startswith("per day"):
        return value, ""
    if b == "per month":
        if not working_days_per_month:
            return None, "needs an explicit working-days-per-month figure"
        return value / working_days_per_month, f"/{working_days_per_month:g} working days"
    return None, f"time basis '{basis}' cannot be converted to per day without more data"


def utilisation(model: CapacityModel, demands: Iterable[Demand], working_days_per_month: Optional[float] = None) -> pd.DataFrame:
    """One row per (section, unit kind). Demand and capacity are only compared when both are in the same unit kind.
    Different unit kinds are NEVER summed. Rows that cannot be compared say exactly why."""
    out = []
    for d in demands:
        cands = [r for r in model.records if r.section == d.section and r.unit_kind == d.unit_kind and r.schedulable and r.value is not None
                 and (d.resource is None or r.resource == d.resource)
                 and (d.measure_contains is None or d.measure_contains in r.measure)
                 and r.attributes.get("status", "ใช้") != "ไม่ใช้"]
        daily = []
        why = []
        if d.resource is None:
            keys = {(r.section, r.unit_kind, next((m for m in ("mills per day",) if m in r.measure), None)) for r in cands}
            if not keys or not keys <= ADDITIVE_SECTIONS or len({k[2] for k in keys}) > 1:
                out.append({"section": d.section, "unit_kind": d.unit_kind, "unit": d.unit, "demand_per_day": None, "capacity_per_day": None,
                            "utilisation_pct": None, "status": "NOT_CALCULABLE", "sources": "",
                            "reason": "Capacity rows of this section are per resource / product spec and are alternatives, not additive. "
                                      "Name the resource (and measure) the demand runs on."})
                continue
        for r in cands:
            if "per person" in r.time_basis:
                if not d.headcount:
                    why.append(f"{r.resource} {r.sheet}!{r.cell}: per-person capacity needs a headcount")
                    continue
                v, note = r.value * d.headcount, ""
            else:
                v, note = _to_day(r.value, r.time_basis, working_days_per_month)
            if v is None:
                why.append(f"{r.resource} {r.sheet}!{r.cell}: {note}")
            else:
                daily.append((r, v))
        if d.period == "day":
            dem_day = d.amount
        elif d.period == "month" and working_days_per_month:
            dem_day = d.amount / working_days_per_month
        else:
            dem_day = None
            why.append(f"demand period '{d.period}' needs working days per month")
        if not daily:
            out.append({"section": d.section, "unit_kind": d.unit_kind, "unit": d.unit, "demand_per_day": dem_day, "capacity_per_day": None, "utilisation_pct": None,
                        "status": "NOT_CALCULABLE", "reason": "; ".join(why) or "no schedulable capacity of this unit kind for this section", "sources": ""})
            continue
        cap = sum(v for _, v in daily)
        out.append({"section": d.section, "unit_kind": d.unit_kind, "unit": d.unit, "demand_per_day": dem_day, "capacity_per_day": cap,
                    "utilisation_pct": (dem_day / cap * 100) if (dem_day is not None and cap) else None,
                    "status": "CALCULATED", "reason": "; ".join(why),
                    "sources": ", ".join(sorted({f"{r.sheet}!{r.cell}" for r, _ in daily})[:12])})
    return pd.DataFrame(out)


def kiln_throughput(model: CapacityModel, program: str) -> dict:
    """Provisional tonnes/day for ONE kiln = load per run / firing days. Labelled provisional because the workbook does not say whether
    the firing days include loading, cooling and unloading."""
    k = model.kiln_programs
    row = k[k["program"].str.split().str[0] == program]
    if row.empty:
        raise MissingConversion(f"Program {program} has no load/duration row in {model.source_file}.")
    r = row.iloc[0]
    return {"program": program, "t_per_run_low": r.load_t_low, "t_per_run_high": r.load_t_high, "run_days": r.cycle_days,
            "t_per_day_low": r.load_t_low / r.cycle_days, "t_per_day_high": r.load_t_high / r.cycle_days,
            "run_days_low": RESIN_RUN_DAYS_OWNER if str(program).upper().startswith("KM-") else r.cycle_days,
            "status": "PROVISIONAL", "basis": f"{model.source_file}!{r.load_cell}/{r.days_cell}; days may exclude cooling/unloading"}
