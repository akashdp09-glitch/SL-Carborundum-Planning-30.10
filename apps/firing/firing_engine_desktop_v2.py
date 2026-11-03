from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from io import BytesIO
from typing import Optional

import pandas as pd
try:
    import plotly.graph_objects as go
    import plotly.express as px
except ImportError as _plotly_error:  # plotly is a REQUIRED dependency (INSTALL_REQUIREMENTS.bat); fail with a clear message, not NameError/AttributeError
    class _PlotlyMissing:
        def __init__(self, name, error): self._name, self._error = name, error
        def __getattr__(self, attr):
            raise ImportError(f"plotly is required for charts ({self._name}.{attr}); run INSTALL_REQUIREMENTS.bat. Original error: {self._error}")
    go, px = _PlotlyMissing("plotly.graph_objects", _plotly_error), _PlotlyMissing("plotly.express", _plotly_error)


# ==========================================================
# SL CARBORUNDUM - FIRING PLANNER V6.8 DIRECT PLAN 2026
# Mixed-floor + mixed-stack packing with floor verification
# ==========================================================

CLOSED = {"CLOSED", "FINISHED", "DONE", "ปิดใบสั่ง"}
PRIORITY_RANK = {"HIGH": 1, "MEDIUM": 2, "LOW": 3}

PROGRAM_RULES = {
    "P1": {"cycle": 7, "minkg": 1200, "maxkg": 1800},
    "P2": {"cycle": 7, "minkg": 1200, "maxkg": 1800},
    "P3": {"cycle": 6, "minkg": 1300, "maxkg": 2000},
    "P4": {"cycle": 7, "minkg": 0, "maxkg": 1500},
    "P6": {"cycle": 5, "minkg": 1600, "maxkg": 1800},
    "KM-185": {"cycle": 3, "minkg": 0, "maxkg": 1000},
    "KM-170": {"cycle": 3, "minkg": 0, "maxkg": 1000},
    "BK-170": {"cycle": 3, "minkg": 0, "maxkg": 1000},
}


# Refractory furniture master for vitrified kilns.
# The operator/planner can edit Enabled and Available Qty in the GUI before planning.
DEFAULT_PLATES = [
    {"Enabled": True, "Plate": "360x410x10", "L mm": 360.0, "W mm": 410.0, "T mm": 10.0, "Available Qty": 376},
    {"Enabled": True, "Plate": "400x400x20", "L mm": 400.0, "W mm": 400.0, "T mm": 20.0, "Available Qty": 97},
    {"Enabled": True, "Plate": "420x370x15", "L mm": 420.0, "W mm": 370.0, "T mm": 15.0, "Available Qty": 252},
    {"Enabled": True, "Plate": "400x500x20", "L mm": 400.0, "W mm": 500.0, "T mm": 20.0, "Available Qty": 1070},
    {"Enabled": True, "Plate": "510x510x20", "L mm": 510.0, "W mm": 510.0, "T mm": 20.0, "Available Qty": 41},
    {"Enabled": True, "Plate": "650x530x20", "L mm": 650.0, "W mm": 530.0, "T mm": 20.0, "Available Qty": 164},
]

DEFAULT_IBLOCKS = [
    {"Enabled": True, "I-block": '2"',   "Height mm": 50.8,  "Available Qty": 412},
    {"Enabled": True, "I-block": '2.5"', "Height mm": 63.5,  "Available Qty": 575},
    {"Enabled": True, "I-block": '3"',   "Height mm": 76.2,  "Available Qty": 597},
    {"Enabled": True, "I-block": '3.5"', "Height mm": 88.9,  "Available Qty": 33},
    {"Enabled": True, "I-block": '4"',   "Height mm": 101.6, "Available Qty": 480},
    {"Enabled": True, "I-block": '4.5"', "Height mm": 114.3, "Available Qty": 1242},
    {"Enabled": True, "I-block": '5"',   "Height mm": 127.0, "Available Qty": 292},
    {"Enabled": True, "I-block": '5.5"', "Height mm": 139.7, "Available Qty": 1100},
    {"Enabled": True, "I-block": '6"',   "Height mm": 152.4, "Available Qty": 800},
    {"Enabled": True, "I-block": '8"',   "Height mm": 203.2, "Available Qty": 191},
]

PLATE_MASTER = [x.copy() for x in DEFAULT_PLATES]
IBLOCK_MASTER = [x.copy() for x in DEFAULT_IBLOCKS]
STAGE4_PROGRESS_CALLBACK = None
STAGE4_HOLD_SIGNATURES = set()
CURRENT_SETTINGS = None

DEFAULT_KILNS = [
    ("T0", "VITRIFIED", 1000, 900, 700, 600, "P1,P2,P3,P4,P6"),
    ("T1", "VITRIFIED", 2150, 1650, 1600, 2000, "P1,P2,P3,P4,P6"),
    ("T2", "VITRIFIED", 2150, 1650, 1600, 2000, "P1,P2,P3,P4,P6"),
    ("T3", "VITRIFIED", 2150, 1650, 1600, 2000, "P1,P2,P3,P4,P6"),
    ("T4", "VITRIFIED", 2150, 1650, 1600, 2000, "P1,P2,P3,P4,P6"),
    ("T5", "VITRIFIED", 2150, 1650, 1600, 2000, "P1,P2,P3,P4,P6"),
    ("T6", "VITRIFIED", 2150, 1650, 1600, 2000, "P1,P2,P3,P4,P6"),
    ("T7", "VITRIFIED", 2150, 1650, 1600, 2000, "P1,P2,P3,P4,P6"),
    ("T8", "VITRIFIED", 2150, 1650, 1600, 2000, "P1,P2,P3,P4,P6"),
    ("T9", "VITRIFIED", 2150, 1650, 1600, 2000, "P1,P2,P3,P4,P6"),
    ("T10", "VITRIFIED", 2150, 1650, 1600, 2000, "P1,P2,P3,P4,P6"),
    ("T11", "VITRIFIED", 2150, 1650, 1600, 2000, "P1,P2,P3,P4,P6"),
    ("T12", "VITRIFIED", 2150, 1650, 1600, 2000, "P1,P2,P3,P4,P6"),
    ("T14", "VITRIFIED", 1500, 2900, 1500, 4500, "P1,P2,P3,P4,P6"),
    ("R4", "RESINOID", 2200, 1200, 1200, 1000, "KM-185,KM-170,BK-170"),
    ("R5", "RESINOID", 2200, 1200, 1200, 1000, "KM-185,KM-170,BK-170"),
    ("R6", "RESINOID", 2200, 1200, 1200, 1000, "KM-185,KM-170,BK-170"),
]


@dataclass
class Settings:
    planning_start: date
    vitrified_starts_per_day: int = 2
    target_volume: float = 0.80
    max_volume: float = 0.95
    space_factor: float = 1.10
    gap_mm: float = 15
    plate_gap_mm: float = 10
    edge_mm: float = 25
    shelf_mm: float = 35
    vertical_clearance_mm: float = 20
    max_stack_height_mm: float = 9999
    quartz_separator_mm: float = 2.0
    max_direct_stack_pieces: int = 999
    preferred_min_vitrified_floors: int = 8
    top_bottom_clearance_mm: float = 50
    resin_fixed_levels: int = 5
    resin_clear_height_mm: float = 185
    risk_days: int = 2
    allow_partial: bool = False
    allow_urgent_partial: bool = True
    allow_mixed_stack: bool = True
    working_days: tuple[int, ...] = (0, 1, 2, 3, 4, 5)
    prep_lead: int = 3
    mix_lead: int = 2
    form_lead: int = 1
    # Performance: physical screening uses a bounded same-program look-ahead.
    # The queue is widened only when the initial window cannot approach the target.
    stage4_candidate_limit: int = 80


def txt(v) -> str:
    return "" if pd.isna(v) else str(v).strip()


def stat(v) -> str:
    return txt(v).upper()


def thai_status(v) -> str:
    """Display production process status in Thai while accepting English input."""
    s = stat(v)
    if s in {"CLOSED","FINISHED","DONE","ปิดใบสั่ง"}:
        return "ปิดใบสั่ง"
    if s in {"NOT CLOSED","NOTCLOSED","OPEN","IN PROCESS","IN PROGRESS","ยังไม่ปิด"}:
        return "ยังไม่ปิด"
    return txt(v)




def contains_khat_phuen(r: pd.Series) -> bool:
    """Factory rule: ONLY Shape containing ขัดพื้น identifies Hin Khat Phuen."""
    return "ขัดพื้น" in txt(r.get("Shape", ""))


def loading_rule(r: pd.Series) -> dict:
    if contains_khat_phuen(r):
        return {
            "family":"HIN KHAT PHUEN / ขัดพื้น",
            "orientation":"VERTICAL GRID",
            "stack_allowed":False,
            "hollow_preferred":True,
            "rule_note":"Shape contains ขัดพื้น: keep vertical, no product-on-product stack; prefer suitable hollow R-category host when feasible."
        }
    return {
        "family":"STANDARD",
        "orientation":"FLAT / STANDARD",
        "stack_allowed":True,
        "hollow_preferred":False,
        "rule_note":"Standard loading rule."
    }


def effective_process_quantities(row: pd.Series):
    """Use downstream actual as evidence of upstream completion.
    Returns cumulative effective quantities for Prep, Mix, Form, Fire, Grind, Pack.
    """
    pa=num(row.get("Preparation Actual Qty",0),0); ma=num(row.get("Mixing Actual Qty",0),0)
    fa=num(row.get("Forming Actual Qty",0),0); fia=num(row.get("Firing Actual Qty",0),0)
    ga=num(row.get("Grinding Actual Qty",0),0); pka=num(row.get("Packing Actual Qty",0),0)
    vals=[pa,ma,fa,fia,ga,pka]
    for i in range(4,-1,-1): vals[i]=max(vals[i],vals[i+1])
    return vals


def verified_firing_ready_qty(row: pd.Series):
    """Qty that is physically defensible for Released Firing Plan.
    Priority: quantity evidence from Plan 2026 actual columns. If no quantity
    trace exists, allow status-only readiness but mark as confirmation required.
    """
    vals=effective_process_quantities(row)
    pa,ma,fa,fia,ga,pka=vals
    if any(v>0 for v in vals):
        return max(fa-fia,0), "FORMING ACTUAL - FIRING ACTUAL", f"Prep {pa:g} | Mix {ma:g} | Form {fa:g} | Fire {fia:g} | Grind {ga:g} | Pack {pka:g}"
    if txt(row.get("Readiness","")) == "READY / FIRING PREPARATION":
        return max(num(row.get("Effective Qty",0),0),0), "STATUS-ONLY READY - PRODUCTION CONFIRMATION REQUIRED", "No quantity trace supplied; release needs production confirmation."
    return 0, "NOT READY FOR FIRING", "No verified forming output available."


def num(v, default=0.0) -> float:
    try:
        return float(v)
    except Exception:
        a = re.findall(r"\d+(?:\.\d+)?", txt(v))
        return float(a[0]) if a else default


def maxdim(v) -> float:
    a = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", txt(v))]
    return max(a) if a else 0.0


def sumdim(v) -> float:
    a = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", txt(v))]
    return sum(a) if a else 0.0


def pdate(v) -> Optional[date]:
    if pd.isna(v) or v == "":
        return None
    if isinstance(v, pd.Timestamp):
        return v.date()
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return pd.to_datetime(v).date()
    except Exception:
        return None


def normalize_kiln_name(v) -> str:
    """Normalize factory kiln labels. Example: T1/2 means physical kiln T1."""
    raw = txt(v).upper().replace(" ", "")
    if not raw:
        return ""
    m = re.match(r"^(T(?:0|[1-9]|1[0-4])|R[456])(?:[/\\-].*)?$", raw)
    if m:
        name = m.group(1)
        return "" if name == "T13" else name
    return raw


def nprog(v) -> str:
    s = txt(v).upper().replace(" ", "")
    try:
        f = float(s)
        if f.is_integer():
            return f"P{int(f)}"
    except Exception:
        pass
    return (
        s.replace("KM185", "KM-185")
         .replace("KM170", "KM-170")
         .replace("BK170", "BK-170")
         .replace("P-", "P")
    )


def add_workdays(d: date, n: int, working=(0, 1, 2, 3, 4, 5)) -> date:
    if n == 0:
        return d
    step = 1 if n > 0 else -1
    left = abs(n)
    x = d
    while left:
        x += timedelta(days=step)
        if x.weekday() in working:
            left -= 1
    return x


def next_workday(d: date, working=(0, 1, 2, 3, 4, 5)) -> date:
    x = d
    while x.weekday() not in working:
        x += timedelta(days=1)
    return x


# -------------------------
# Product geometry
# -------------------------

def _looks_like_honing(*values) -> bool:
    """Treat common/near misspellings of HONING/HONE/HONNING as rectangular.
    This is intentionally tolerant because legacy master text is not always consistent.
    Manual Geometry Override in the UI remains authoritative.
    """
    import re
    from difflib import SequenceMatcher
    target = "HONING"
    for value in values:
        text = txt(value).upper()
        if not text:
            continue
        if any(k in text for k in ["HONING", "HONNING", "HONE", "HONN", "HON "]):
            return True
        tokens = re.findall(r"[A-Z]+", text)
        for tok in tokens:
            if len(tok) >= 4 and SequenceMatcher(None, tok, target).ratio() >= 0.67:
                return True
    return False

def _looks_like_segment(*values) -> bool:
    from difflib import SequenceMatcher
    for value in values:
        text = txt(value).upper()
        if not text:
            continue
        compact = re.sub(r"[^A-Z0-9]", "", text)
        if any(k in compact for k in ["SEGMENT", "SEGMENTR", "SEGMNT", "SEGMEN", "SEMENT"]):
            return True
        for tok in re.findall(r"[A-Z]+", text):
            if len(tok) >= 5 and SequenceMatcher(None, tok, "SEGMENT").ratio() >= 0.72:
                return True
    return False

def geometry(r: pd.Series) -> str:
    ov = txt(r.get("Geometry Override", "")).upper()
    if ov in {"CIRCULAR", "RECTANGULAR"}:
        return ov
    cat = txt(r.get("Category", "")).upper()
    vals=(r.get("Product Type", ""), r.get("Specification", ""), r.get("Shape", ""))
    if contains_khat_phuen(r) or _looks_like_honing(*vals) or _looks_like_segment(*vals) or cat in {"S","T"}:
        return "RECTANGULAR"
    return "CIRCULAR"


def dimensions(r: pd.Series):
    """Factory convention: circular D=outer dia, T=thickness, H=hole dia;
    rectangular D=length, T=thickness, H=width."""
    notes = txt(r.get("Notes", "")).upper()
    D = maxdim(r.get("D / Length mm", 0))
    T = sumdim(r.get("T / Width mm", 0)) if ("TWO LAYER" in notes or "2 LAYER" in notes) else maxdim(r.get("T / Width mm", 0))
    H = maxdim(r.get("H / Hole mm", 0))
    return D, T, H


def loading_orientation(r: pd.Series, g, D, T, H):
    """Return physically defensible footprint + height for kiln loading.

    Circular wheels stay flat with T as height.  Standard rectangular/HONING/SEGMENT
    parts are loaded in their stable flat orientation: smallest positive dimension is
    vertical, and the two larger dimensions form the floor footprint.  The explicit
    factory exception Shape containing ขัดพื้น keeps its special vertical rule.
    """
    if g == "CIRCULAR":
        return max(D,1), max(D,1), max(T,1), "FLAT CIRCULAR"
    if contains_khat_phuen(r):
        # Factory/photo rule: Hin Khat Phuen is stood upright in rows and must not
        # be product-on-product stacked.  Use the largest physical dimension as
        # vertical height; the two smaller dimensions are the supported footprint.
        dims = sorted([max(D,1), max(T,1), max(H,1)])
        return dims[0], dims[1], dims[2], "UPRIGHT GRID / ขัดพื้น / NO STACK"
    dims = sorted([max(D,1), max(T,1), max(H,1)])
    # stable flat orientation: smallest dimension is vertical height
    return dims[2], dims[1], dims[0], "FLAT AUTO - SMALLEST DIMENSION VERTICAL"


def footprint(g, D, T, H):
    # Compatibility helper for legacy callers. Prepared orders use loading_orientation().
    return (max(D,1),max(D,1)) if g=="CIRCULAR" else (max(D,1),max(H,1))


def piece_height(g, D, T, H):
    # Compatibility helper for legacy callers. Prepared orders use loading_orientation().
    return max(T,1)


def physical_volume(g, D, T, H):
    if g=="RECTANGULAR":
        return max(D,0)*max(H,0)*max(T,0)/1e9
    hole=min(max(H,0),max(D,0))
    return math.pi/4*max(D*D-hole*hole,0)*max(T,0)/1e9


# -------------------------
# Order input and readiness
# -------------------------

REQUIRED = [
    "Work Order", "Category", "Customer", "Specification", "Product Type", "Shape",
    "D / Length mm", "T / Width mm", "H / Hole mm",
    "Order Qty", "Remaining Qty", "Weight kg/pc", "Program",
    "Due Date", "Priority", "Compatible?", "Notes",
    "Order Status", "Preparation Status", "Mixing Status",
    "Forming Status", "Firing Status", "Geometry Override",
]


def done(v) -> bool:
    return stat(v) in CLOSED


def readiness(r: pd.Series, settings: Settings):
    if not done(r.get("Preparation Status", "")):
        return "PREPARATION REQUIRED", add_workdays(settings.planning_start, settings.prep_lead, settings.working_days)
    if not done(r.get("Mixing Status", "")):
        return "MIXING REQUIRED", add_workdays(settings.planning_start, settings.mix_lead, settings.working_days)
    if not done(r.get("Forming Status", "")):
        return "FORMING REQUIRED", add_workdays(settings.planning_start, settings.form_lead, settings.working_days)
    return "READY / FIRING PREPARATION", settings.planning_start


def prepare_orders(df: pd.DataFrame, settings: Settings) -> pd.DataFrame:
    df = df.copy()
    for c in REQUIRED:
        if c not in df.columns:
            df[c] = ""

    rows = []
    for i, r in df.iterrows():
        wo = txt(r["Work Order"])
        if not wo:
            continue

        oq = num(r["Order Qty"])
        rq = num(r["Remaining Qty"])
        effective = max(0.0, min(oq, rq))
        kgpc = num(r["Weight kg/pc"])
        category = txt(r["Category"]).upper()
        program = nprog(r["Program"])
        # PB = resinoid. Keep the Plan Input program when supplied.
        # If PB program is blank, use KM-185 so PB demand cannot disappear.
        if category == "PB" and not program:
            program = "KM-185"
        due = pdate(r["Due Date"])
        priority = txt(r["Priority"]).upper() or "LAST"
        compatible = txt(r["Compatible?"]).upper()

        g = geometry(r)
        D, T, H = dimensions(r)
        fx, fy, ph, load_orientation = loading_orientation(r, g, D, T, H)
        v = physical_volume(g, D, T, H)
        rd, earliest = readiness(r, settings)
        lr = loading_rule(r)

        checks = []
        if rq > oq:
            checks.append("Remaining Qty > Order Qty")
        if kgpc <= 0:
            checks.append("Weight missing")
        if not program:
            checks.append("Program missing")
        if category == "PB" and program not in {"KM-185","KM-170","BK-170"}:
            checks.append("PB category requires resin program KM-185 / KM-170 / BK-170")
        if due is None:
            checks.append("Due date missing")
        if D <= 0 or T <= 0:
            checks.append("Dimension missing")
        if contains_khat_phuen(r):
            checks.append("SPECIAL LOADING: ขัดพื้น vertical / no stack / hollow nesting preferred")

        include = (
            effective > 0
            and compatible == "YES"
            and stat(r["Order Status"]) not in CLOSED
            and stat(r["Firing Status"]) not in CLOSED
        )

        rows.append({
            "Source Row": i + 2,
            "Work Order": wo,
            "Category": category,
            "Customer": txt(r["Customer"]),
            "Specification": txt(r["Specification"]),
            "Product Type": txt(r["Product Type"]),
            "Shape": txt(r.get("Shape", "")),
            "D": D, "T": T, "H": H,
            "D Raw": r.get("D / Length mm",""), "T Raw": r.get("T / Width mm",""), "H Raw": r.get("H / Hole mm",""),
            "Footprint X": fx,
            "Footprint Y": fy,
            "Piece Height": ph,
            "Loading Orientation": load_orientation,
            "Loading Family": lr.get("family","STANDARD"),
            "Stack Allowed": bool(lr.get("stack_allowed",True)),
            "Hollow Nesting Preferred": bool(lr.get("hollow_preferred",False)),
            "Loading Rule Note": lr.get("rule_note",""),
            "Order Qty": oq,
            "Remaining Qty": rq,
            "Effective Qty": effective,
            "Weight kg/pc": kgpc,
            "Program": program,
            "Due Date": due,
            "Priority": priority,
            "Priority Rank": PRIORITY_RANK.get(priority, 9),
            "Compatible": compatible,
            "Preparation Status": thai_status(r["Preparation Status"]),
            "Mixing Status": thai_status(r["Mixing Status"]),
            "Forming Status": thai_status(r["Forming Status"]),
            "Firing Status": thai_status(r["Firing Status"]),
            "Preparation Actual Qty": num(r.get("Preparation Actual Qty",0),0),
            "Mixing Actual Qty": num(r.get("Mixing Actual Qty",0),0),
            "Forming Actual Qty": num(r.get("Forming Actual Qty",0),0),
            "Firing Actual Qty": num(r.get("Firing Actual Qty",0),0),
            "Grinding Actual Qty": num(r.get("Grinding Actual Qty",0),0),
            "Packing Actual Qty": num(r.get("Packing Actual Qty",0),0),
            "Geometry": g,
            "Unit Volume m3": v,
            "Unit Space m3": v * settings.space_factor,
            "Readiness": rd,
            "Earliest Normal Firing": earliest,
            "Include": include,
            "Data Check": "; ".join(checks),
        })

    out = pd.DataFrame(rows)
    if out.empty:
        return out

    out["_due"] = out["Due Date"].apply(lambda x: x or date(2099, 12, 31))
    out["Readiness Rank"] = out["Readiness"].map({
        "READY / FIRING PREPARATION": 0,
        "FORMING REQUIRED": 1,
        "MIXING REQUIRED": 2,
        "PREPARATION REQUIRED": 3,
    }).fillna(9).astype(int)
    out=add_plan2026_trace_visibility(out)
    _vr = out.apply(lambda rr: pd.Series(verified_firing_ready_qty(rr), index=["Verified Ready for Firing Qty","Firing Ready Basis","Firing Ready Trace"]), axis=1)
    out = pd.concat([out, _vr], axis=1)
    out["Release Candidate"] = (out["Include"] & (pd.to_numeric(out["Verified Ready for Firing Qty"], errors="coerce").fillna(0) > 0))
    # Business priority: earliest customer due date first.
    # Readiness remains a hard feasibility gate in build_plan().
    return out.sort_values(
        ["_due","Priority Rank","Readiness Rank","Earliest Normal Firing","Source Row"]
    ).reset_index(drop=True)



def add_plan2026_trace_visibility(prepared):
    """Use optional Plan 2026 trace columns carried in Plan Input.
    If they are absent, do not guess quantities; status-only readiness remains visible.
    """
    if prepared is None or prepared.empty:return prepared
    x=prepared.copy()
    loc=[]; qloc=[]; action=[]; trace=[]
    for _,r in x.iterrows():
        pa=num(r.get("Preparation Actual Qty",0),0); ma=num(r.get("Mixing Actual Qty",0),0)
        fa=num(r.get("Forming Actual Qty",0),0); fia=num(r.get("Firing Actual Qty",0),0)
        ga=num(r.get("Grinding Actual Qty",0),0); pka=num(r.get("Packing Actual Qty",0),0)
        # Downstream actual is evidence that quantity passed upstream.
        vals=[pa,ma,fa,fia,ga,pka]
        for i in range(4,-1,-1): vals[i]=max(vals[i],vals[i+1])
        pa,ma,fa,fia,ga,pka=vals
        if pka>0: cp="PACKING / FINISHED GOODS"; q=pka; ac="Delivery / warehouse follow-up"
        elif ga>0: cp="POST-FIRING PROCESS → PACKING"; q=max(ga-pka,0); ac="Expedite Packing"
        elif fia>0: cp="FIRED → CONFIRMED GRINDING OR CUTTING ROUTE"; q=max(fia-ga,0); ac="Expedite confirmed Grinding or Cutting process"
        elif fa>0: cp="FORMED → FIRING"; q=max(fa-fia,0); ac="Prepare / release to firing"
        elif ma>0: cp="MIXED → FORMING"; q=max(ma-fa,0); ac="Expedite Forming"
        elif pa>0: cp="PREPARED → MIXING"; q=max(pa-ma,0); ac="Expedite Mixing"
        else:
            # With no quantity trace, use status evidence only and say quantity unavailable.
            rd=txt(r.get("Readiness",""))
            cp={"PREPARATION REQUIRED":"PREPARATION","MIXING REQUIRED":"MIXING","FORMING REQUIRED":"FORMING","READY / FIRING PREPARATION":"READY FOR FIRING"}.get(rd,rd)
            q=None; ac="Expedite "+cp.title() if cp and cp!="READY FOR FIRING" else "Firing preparation"
        loc.append(cp); qloc.append(q); action.append(ac)
        trace.append(f"Prep {pa:g} | Mix {ma:g} | Form {fa:g} | Fire {fia:g} | Grind {ga:g} | Pack {pka:g}" if any(vals) else "Quantity trace not supplied in Plan Input")
    x["Calculated Current Process"]=loc
    x["Qty at Current Process / Ready Next"]=qloc
    x["Required Action"]=action
    x["Plan2026 Actual Trace"]=trace
    return x

# -------------------------
# Kiln master
# -------------------------

def default_kilns(settings: Settings):
    rows = []
    for name, typ, L, W, H, kg, programs in DEFAULT_KILNS:
        rows.append({
            "Enabled": True,
            "Kiln": name,
            "Type": typ,
            "Status": "AVAILABLE",
            "Available From": settings.planning_start,
            "L mm": L, "W mm": W, "H mm": H,
            "Gross m3": L * W * H / 1e9,
            "Physical kg": kg,
            "Programs": programs,
            "Furniture": "METAL FRAME" if typ == "RESINOID" else "REFRACTORY SHELF",
            "Fixed Levels": settings.resin_fixed_levels if typ == "RESINOID" else 0,
            "Level Clear Height mm": settings.resin_clear_height_mm if typ == "RESINOID" else 0,
        })
    return pd.DataFrame(rows)


def prepare_kilns(df: pd.DataFrame, settings: Settings):
    rows = []
    for _, k in df.iterrows():
        name = normalize_kiln_name(k["Kiln"])
        if not name or name == "T13":
            continue
        status = txt(k["Status"]).upper() or "AVAILABLE"
        enabled = bool(k["Enabled"]) and status != "DISABLED"

        # UI is the authority for kiln availability.
        av = pdate(k["Available From"]) or settings.planning_start
        if not enabled:
            av = date(2099, 12, 31)

        rows.append({
            "Enabled": enabled,
            "Kiln": name,
            "Type": txt(k["Type"]).upper(),
            "Status": status,
            "Available From": av,
            "Next Available": av,
            "L mm": num(k["L mm"]),
            "W mm": num(k["W mm"]),
            "H mm": num(k["H mm"]),
            "Gross m3": num(k["Gross m3"]),
            "Physical kg": num(k["Physical kg"]),
            "Programs": [nprog(x) for x in txt(k["Programs"]).split(",") if txt(x)],
            "Furniture": txt(k["Furniture"]),
            "Fixed Levels": int(num(k["Fixed Levels"])),
            "Level Clear Height mm": num(k["Level Clear Height mm"]),
        })
    return pd.DataFrame(rows)


def program_rule(program, kiln):
    r = PROGRAM_RULES.get(program, {"cycle": 7, "maxkg": 1800}).copy()
    if program == "P3" and kiln == "T14":
        r["cycle"] = 6
        r["minkg"] = 3800
        r["maxkg"] = 4000
    return r


# -------------------------
# Mixed floor / stack packer
# -------------------------

def active_plates():
    return [
        x for x in PLATE_MASTER
        if bool(x.get("Enabled", True)) and num(x.get("Available Qty", 0)) > 0
    ]


def active_iblocks():
    return sorted(
        [
            x for x in IBLOCK_MASTER
            if bool(x.get("Enabled", True)) and num(x.get("Available Qty", 0)) > 0
        ],
        key=lambda x: num(x.get("Height mm", 0)),
    )


def select_iblock(stack_zone_height, settings):
    required = float(stack_zone_height) + float(settings.vertical_clearance_mm)
    for ib in active_iblocks():
        if num(ib.get("Height mm", 0)) + 1e-9 >= required:
            return ib
    return None


def plate_usage(floors):
    use = {}
    for f in floors:
        name = txt(f.get("plate_name", ""))
        if name and name != "METAL FRAME":
            use[name] = use.get(name, 0) + int(f.get("plate_count", 0))
    return use


def iblock_usage(floors, settings, override_floor=None, proposed_stack=None):
    """
    Count inter-floor I-block/support columns.

    Physical correction V1.9.16:
    an I-block is required to support the NEXT refractory floor above a loaded
    floor.  The TOP loaded floor does not require an imaginary upper shelf.
    This is important for large R/rice stones: Production can load one thick
    ring on a multi-plate floor even when no single I-block is tall enough to
    create another floor above it.

    For an R x C tiled support grid, adjacent plates share corner/junction
    support positions.  Required positions = (R+1)*(C+1) for each NON-TOP
    floor that actually supports another floor.
    """
    use = {}
    n = len(floors)
    for i, f in enumerate(floors):
        if f.get("plate_name") == "METAL FRAME":
            continue
        # No imaginary upper floor above the top loaded level.
        if i == n - 1:
            continue
        stack_h = proposed_stack if (override_floor is not None and i == override_floor) else f["stack_zone_height"]
        ib = select_iblock(stack_h, settings)
        if ib is None:
            use["__NO_IBLOCK__"] = 10**9
            continue
        name = txt(ib["I-block"])
        qty = int(f.get("support_nodes", 0))
        use[name] = use.get(name, 0) + qty
    return use


def furniture_feasible(floors, settings, override_floor=None, proposed_stack=None):
    pcap = {txt(x["Plate"]): int(num(x["Available Qty"])) for x in active_plates()}
    for name, qty in plate_usage(floors).items():
        if qty > pcap.get(name, 0):
            return False

    icap = {txt(x["I-block"]): int(num(x["Available Qty"])) for x in active_iblocks()}
    for name, qty in iblock_usage(floors, settings, override_floor, proposed_stack).items():
        if name == "__NO_IBLOCK__" or qty > icap.get(name, 0):
            return False
    return True


def plate_layout_candidate(kiln, plate, fx, fy, settings):
    """
    A vitrified floor is a tiled refractory support surface.
    Large R / large wheels may span adjacent plates; requiring the whole part
    to fit on ONE plate incorrectly rejects valid products such as rice stones.
    The part must fit inside the contiguous tiled support footprint and kiln
    usable dimensions. Furniture quantity remains checked separately.
    """
    edge=float(settings.edge_mm)
    pgap=float(settings.plate_gap_mm)
    usable_l=max(float(kiln["L mm"])-2*edge,1)
    usable_w=max(float(kiln["W mm"])-2*edge,1)
    cands=[]
    for rotated in (False,True):
        pl=num(plate["L mm"]); pw=num(plate["W mm"])
        if rotated: pl,pw=pw,pl
        max_cols=int((usable_l+pgap)//(pl+pgap))
        max_rows=int((usable_w+pgap)//(pw+pgap))
        if max_cols<=0 or max_rows<=0: continue

        # Minimum contiguous plate grid required to support the first part.
        req_cols=max(1,int(math.ceil(max(fx-pgap,0)/(pl+pgap))))
        req_rows=max(1,int(math.ceil(max(fy-pgap,0)/(pw+pgap))))
        if req_cols>max_cols or req_rows>max_rows:
            # Try footprint rotation relative to the tiled floor.
            req_cols2=max(1,int(math.ceil(max(fy-pgap,0)/(pl+pgap))))
            req_rows2=max(1,int(math.ceil(max(fx-pgap,0)/(pw+pgap))))
            if req_cols2>max_cols or req_rows2>max_rows:
                continue

        # Use the available tiled floor grid. The packing engine can then place
        # large circular/rectangular parts over adjacent supported plates.
        cols=max_cols; rows=max_rows; count=cols*rows
        covered_l=cols*pl+(cols-1)*pgap
        covered_w=rows*pw+(rows-1)*pgap
        if not ((fx<=covered_l+1e-9 and fy<=covered_w+1e-9) or
                (fy<=covered_l+1e-9 and fx<=covered_w+1e-9)):
            continue
        cands.append({
            "plate_name":txt(plate["Plate"]),"plate_l":pl,"plate_w":pw,
            "plate_t":num(plate["T mm"]),"plate_cols":cols,"plate_rows":rows,
            "plate_count":count,"support_nodes":(cols+1)*(rows+1),
            "covered_area":covered_l*covered_w,
            "covered_l":covered_l,"covered_w":covered_w,
            "plate_available_qty":int(num(plate["Available Qty"])),
            "support_mode":"CONTIGUOUS TILED REFRACTORY FLOOR"
        })
    return max(cands,key=lambda x:x["covered_area"]) if cands else None

def choose_plate_layout(kiln, order, floors, settings):
    fx = float(order["Footprint X"])
    fy = float(order["Footprint Y"])
    used = plate_usage(floors)
    cands = []

    for plate in active_plates():
        c = plate_layout_candidate(kiln, plate, fx, fy, settings)
        if c is None:
            continue
        if used.get(c["plate_name"], 0) + c["plate_count"] > c["plate_available_qty"]:
            continue

        # Higher supported floor coverage first; fewer plates as tie-breaker.
        cands.append(c)

    if not cands:
        return None
    return max(cands, key=lambda x: (x["covered_area"], -x["plate_count"]))


def new_floor(kiln, settings, order, floors):
    if kiln["Type"] == "RESINOID":
        edge = settings.edge_mm
        return {
            "free": [{
                "x": edge,
                "y": edge,
                "w": max(float(kiln["L mm"]) - 2 * edge, 1),
                "h": max(float(kiln["W mm"]) - 2 * edge, 1),
                "plate_zone": "METAL FRAME",
            }],
            "placements": [],
            "stack_zone_height": 0.0,
            "plate_name": "METAL FRAME",
            "plate_l": max(float(kiln["L mm"]) - 2 * edge, 1),
            "plate_w": max(float(kiln["W mm"]) - 2 * edge, 1),
            "plate_t": float(settings.shelf_mm),
            "plate_cols": 1,
            "plate_rows": 1,
            "plate_count": 1,
            "support_nodes": 0,
        }

    layout = choose_plate_layout(kiln, order, floors, settings)
    if layout is None:
        return None

    edge = float(settings.edge_mm)
    pgap = float(settings.plate_gap_mm)
    # Treat adjacent refractory plates as one contiguous supported floor.
    # This allows large R / large wheels to bridge adjacent plates while still
    # checking total furniture quantity, kiln wall clearance and floor height.
    covered_l=layout.get("covered_l",layout["plate_cols"]*layout["plate_l"]+(layout["plate_cols"]-1)*pgap)
    covered_w=layout.get("covered_w",layout["plate_rows"]*layout["plate_w"]+(layout["plate_rows"]-1)*pgap)
    free=[{
        "x":edge,"y":edge,"w":covered_l,"h":covered_w,
        "plate_zone":"TILED FLOOR"
    }]

    floor = {
        "free": free,
        "placements": [],
        "stack_zone_height": 0.0,
    }
    floor.update(layout)
    return floor


def floor_pitch(floor, kiln, settings, proposed_stack=None):
    if kiln["Type"] == "RESINOID" and kiln["Fixed Levels"] > 0:
        return float(kiln["Level Clear Height mm"]) + settings.shelf_mm

    stack_h = floor["stack_zone_height"] if proposed_stack is None else proposed_stack
    ib = select_iblock(stack_h, settings)
    if ib is None:
        return float("inf")
    return float(ib["Height mm"]) + float(floor.get("plate_t", settings.shelf_mm))


def total_height(floors, kiln, settings):
    """
    Physical load height.

    Inter-floor levels need an I-block tall enough to clear the product below.
    The top loaded floor has no upper refractory plate, so its contribution is
    simply its own plate thickness + loaded stack height.

    This removes the old false rejection of thick single-level R/rice stones.
    """
    if not floors:
        return 0.0
    if kiln["Type"] == "RESINOID" and kiln["Fixed Levels"] > 0:
        pitches = [floor_pitch(f, kiln, settings) for f in floors]
        if any(not math.isfinite(x) for x in pitches):
            return float("inf")
        return sum(pitches)

    h = 0.0
    for i, f in enumerate(floors):
        if i == len(floors) - 1:
            h += float(f.get("plate_t", settings.shelf_mm)) + float(f.get("stack_zone_height", 0.0))
        else:
            p = floor_pitch(f, kiln, settings)
            if not math.isfinite(p):
                return float("inf")
            h += p
    return h


def height_feasible(
    floors, kiln, settings,
    floor_index=None, proposed_floor_stack=None,
    adding_floor_stack=None, new_floor_obj=None
):
    usable = max(float(kiln["H mm"]) - settings.top_bottom_clearance_mm, 1)

    if kiln["Type"] == "RESINOID" and kiln["Fixed Levels"] > 0:
        if adding_floor_stack is not None:
            return (
                len(floors) < int(kiln["Fixed Levels"])
                and adding_floor_stack <= float(kiln["Level Clear Height mm"]) + 1e-9
            )
        if floor_index is not None:
            return proposed_floor_stack <= float(kiln["Level Clear Height mm"]) + 1e-9
        return True

    if adding_floor_stack is not None:
        if new_floor_obj is None:
            return False
        test = list(floors) + [new_floor_obj]
        test[-1]["stack_zone_height"] = float(adding_floor_stack)
        h = total_height(test, kiln, settings)
        return (
            math.isfinite(h)
            and h <= usable + 1e-9
            and furniture_feasible(test, settings)
        )

    if floor_index is not None:
        # Re-evaluate the COMPLETE floor stack after the proposed height change.
        # This is essential for the top level: the top floor has no imaginary
        # upper shelf/I-block, while any floor below another level still does.
        test = [dict(f) for f in floors]
        test[floor_index]["stack_zone_height"] = float(proposed_floor_stack)
        h = total_height(test, kiln, settings)
        return (
            math.isfinite(h)
            and h <= usable + 1e-9
            and furniture_feasible(test, settings)
        )

    return (
        total_height(floors, kiln, settings) <= usable + 1e-9
        and furniture_feasible(floors, settings)
    )


def orientation_fit(rect, fx, fy):
    opts = []
    if fx <= rect["w"] + 1e-9 and fy <= rect["h"] + 1e-9:
        opts.append((fx, fy, "NORMAL"))
    if fy <= rect["w"] + 1e-9 and fx <= rect["h"] + 1e-9:
        opts.append((fy, fx, "ROTATED 90°"))
    if not opts:
        return None
    return min(opts, key=lambda x: rect["w"] * rect["h"] - x[0] * x[1])


def split_rect(rect, pw, ph, gap):
    out = []
    zone = rect.get("plate_zone", "")
    right_w = rect["w"] - pw - gap
    if right_w > 1:
        out.append({
            "x": rect["x"] + pw + gap, "y": rect["y"],
            "w": right_w, "h": ph, "plate_zone": zone
        })
    top_h = rect["h"] - ph - gap
    if top_h > 1:
        out.append({
            "x": rect["x"], "y": rect["y"] + ph + gap,
            "w": rect["w"], "h": top_h, "plate_zone": zone
        })
    return out


def stack_piece_capacity(order, current_height, kiln, settings, current_piece_count=0):
    """
    Physical direct-stack capacity.

    V1.9.17:
    Normal stackable vitrified products are limited by real vertical geometry
    and support clearance, not by the former artificial two-piece ceiling.
    Explicit no-stack products (e.g. Hin Khat Phuen / ขัดพื้น) remain blocked.
    """
    if kiln["Type"] == "RESINOID":
        return 0
    if "Stack Allowed" in order.index and not bool(order.get("Stack Allowed", True)):
        return 0

    ibs = active_iblocks()
    if not ibs:
        return 0

    max_clear = max(num(x["Height mm"]) for x in ibs) - float(settings.vertical_clearance_mm)
    height_limit = min(float(settings.max_stack_height_mm), max_clear)
    ph = max(float(order["Piece Height"]), 1e-9)
    qz = max(float(getattr(settings,"quartz_separator_mm",2.0)),0.0)
    remaining_h=max(height_limit-float(current_height),0.0)
    # Existing stack: each added piece needs quartz + product height.
    # Empty stack: no quartz below first product.
    if int(current_piece_count)>0:
        by_height=max(0,int(remaining_h//max(ph+qz,1e-9)))
    else:
        by_height=max(0,int((remaining_h+qz)//max(ph+qz,1e-9)))

    # High guard only; real capacity is controlled by height.
    guard = max(int(getattr(settings, "max_direct_stack_pieces", 999)) - int(current_piece_count), 0)
    return min(by_height, guard)

def place_on_existing_stack(floors, order, qty, kiln, settings):
    if not settings.allow_mixed_stack or qty <= 0 or kiln["Type"] == "RESINOID":
        return None

    fx, fy = float(order["Footprint X"]), float(order["Footprint Y"])
    ph = float(order["Piece Height"])
    candidates = []

    for fi, floor in enumerate(floors):
        for pi, p in enumerate(floor["placements"]):
            # Upper part must fit inside the IMMEDIATE supporting top part.
            # This prevents a larger WO being placed on top of a smaller WO
            # merely because the original bottom part was large.
            top_w = p.get("top_w", p["w"])
            top_h = p.get("top_h", p["h"])

            normal_ok = fx <= top_w + 1e-9 and fy <= top_h + 1e-9
            rotated_ok = fy <= top_w + 1e-9 and fx <= top_h + 1e-9

            if not (normal_ok or rotated_ok):
                continue

            if normal_ok:
                upper_w, upper_h, upper_orientation = fx, fy, "NORMAL"
            else:
                upper_w, upper_h, upper_orientation = fy, fx, "ROTATED 90°"

            current_piece_count = sum(int(seg.get("Qty",0)) for seg in p.get("segments",[]))
            cap = stack_piece_capacity(
                order, p["stack_height"], kiln, settings,
                current_piece_count=current_piece_count
            )
            if cap <= 0:
                continue

            take = min(qty, cap)
            qz=max(float(getattr(settings,"quartz_separator_mm",2.0)),0.0)
            sep_count=take if current_piece_count>0 else max(take-1,0)
            new_stack = p["stack_height"] + take*ph + sep_count*qz
            new_floor_stack = max(floor["stack_zone_height"], new_stack)

            if not height_feasible(floors, kiln, settings, fi, new_floor_stack):
                continue

            candidates.append((
                new_floor_stack, fi, pi, take, new_stack,
                upper_w, upper_h, upper_orientation
            ))

    if not candidates:
        return None

    # Best-fit: smallest new floor stack height.
    _, fi, pi, take, new_stack, upper_w, upper_h, upper_orientation = min(
        candidates, key=lambda x: x[0]
    )
    p = floors[fi]["placements"][pi]
    z0 = p["stack_height"]

    p["segments"].append({
        "Work Order": order["Work Order"],
        "Qty": take,
        "z0": z0,
        "z1": new_stack,
        "Geometry": order["Geometry"],
        "Piece Height": ph,
    })
    p["stack_height"] = new_stack
    p["top_w"] = upper_w
    p["top_h"] = upper_h
    p["top_orientation"] = upper_orientation
    floors[fi]["stack_zone_height"] = max(floors[fi]["stack_zone_height"], new_stack)

    return {"floor": fi, "placement": pi, "qty": take, "mode": "TOP STACK / MIXED WO"}


def place_new_position(floors, order, qty, kiln, settings):
    if qty <= 0:
        return None

    fx, fy = float(order["Footprint X"]), float(order["Footprint Y"])
    ph = float(order["Piece Height"])
    # Stability-first: open a new supported footprint with ONE base piece.
    # Additional pieces may be stacked later only after supported floor area
    # has been used as much as possible.
    stack_cap = 1

    candidates = []
    for fi, floor in enumerate(floors):
        for ri, rect in enumerate(floor["free"]):
            fit = orientation_fit(rect, fx, fy)
            if not fit:
                continue
            pw, phoriz, orient = fit
            take = 1
            stack_h = ph
            new_floor_stack = max(floor["stack_zone_height"], stack_h)

            if not height_feasible(floors, kiln, settings, fi, new_floor_stack):
                continue

            waste = rect["w"] * rect["h"] - pw * phoriz
            candidates.append((waste, fi, ri, pw, phoriz, orient, take, stack_h))

    if not candidates:
        return None

    _, fi, ri, pw, phoriz, orient, take, stack_h = min(candidates, key=lambda x: x[0])
    floor = floors[fi]
    rect = floor["free"].pop(ri)

    floor["placements"].append({
        "x": rect["x"], "y": rect["y"], "w": pw, "h": phoriz,
        "orientation": orient,
        "plate_zone": rect.get("plate_zone", ""),
        "geometry": order["Geometry"],
        "stack_height": stack_h,
        # Immediate supporting top footprint. This changes when a different WO
        # is stacked on top, so the next part must fit the actual top part,
        # not only the original base footprint.
        "top_w": pw,
        "top_h": phoriz,
        "segments": [{
            "Work Order": order["Work Order"],
            "Qty": take,
            "z0": 0.0,
            "z1": stack_h,
            "Geometry": order["Geometry"],
            "Piece Height": ph,
            "Loading Orientation": order.get("Loading Orientation", ""),
            "D": float(order.get("D",0) or 0),
            "T": float(order.get("T",0) or 0),
            "H": float(order.get("H",0) or 0),
            "D Raw": order.get("D Raw",""),
            "T Raw": order.get("T Raw",""),
            "H Raw": order.get("H Raw",""),
        }],
    })
    floor["free"].extend(split_rect(rect, pw, phoriz, settings.gap_mm))
    floor["stack_zone_height"] = max(floor["stack_zone_height"], stack_h)

    return {"floor": fi, "placement": len(floor["placements"]) - 1, "qty": take, "mode": "SAME FLOOR / NEW POSITION"}


def place_new_floor(floors, order, qty, kiln, settings):
    if qty <= 0:
        return None

    f = new_floor(kiln, settings, order, floors)
    if f is None or not f["free"]:
        return None

    fx, fy = float(order["Footprint X"]), float(order["Footprint Y"])
    ph = float(order["Piece Height"])
    # Stability-first: open a new supported footprint with ONE base piece.
    # Additional pieces may be stacked later only after supported floor area
    # has been used as much as possible.
    stack_cap = 1

    candidates = []
    for ri, rect in enumerate(f["free"]):
        fit = orientation_fit(rect, fx, fy)
        if not fit:
            continue
        pw, phoriz, orient = fit
        waste = rect["w"] * rect["h"] - pw * phoriz
        candidates.append((waste, ri, pw, phoriz, orient))

    if not candidates:
        return None

    _, ri, pw, phoriz, orient = min(candidates, key=lambda x: x[0])
    take = 1
    stack_h = ph

    if not height_feasible(
        floors, kiln, settings,
        adding_floor_stack=stack_h,
        new_floor_obj=f
    ):
        return None

    rect = f["free"].pop(ri)
    f["placements"].append({
        "x": rect["x"], "y": rect["y"], "w": pw, "h": phoriz,
        "orientation": orient,
        "plate_zone": rect.get("plate_zone", ""),
        "geometry": order["Geometry"],
        "stack_height": stack_h,
        "top_w": pw,
        "top_h": phoriz,
        "segments": [{
            "Work Order": order["Work Order"],
            "Qty": take,
            "z0": 0.0,
            "z1": stack_h,
            "Geometry": order["Geometry"],
            "Piece Height": ph,
            "Loading Orientation": order.get("Loading Orientation", ""),
            "D": float(order.get("D",0) or 0),
            "T": float(order.get("T",0) or 0),
            "H": float(order.get("H",0) or 0),
            "D Raw": order.get("D Raw",""),
            "T Raw": order.get("T Raw",""),
            "H Raw": order.get("H Raw",""),
        }],
    })
    f["free"].extend(split_rect(rect, pw, phoriz, settings.gap_mm))
    f["stack_zone_height"] = stack_h
    floors.append(f)

    return {
        "floor": len(floors) - 1,
        "placement": 0,
        "qty": take,
        "mode": "NEW FLOOR / REFRACTORY FURNITURE",
    }



def best_grid_fit(rect, fx, fy, gap):
    """
    Return the best regular grid for one free supported rectangle.
    This replaces thousands of repeated one-piece best-fit searches.
    """
    candidates = []
    for pw, phoriz, orient in [(fx,fy,"NORMAL"),(fy,fx,"ROTATED")]:
        if pw <= 0 or phoriz <= 0:
            continue
        nx = int((float(rect["w"]) + gap) // (pw + gap))
        ny = int((float(rect["h"]) + gap) // (phoriz + gap))
        n = max(nx,0) * max(ny,0)
        if n <= 0:
            continue
        used = n * pw * phoriz
        candidates.append((n, used, pw, phoriz, orient, nx, ny))
    if not candidates:
        return None
    # Max number of positions first, then occupied area.
    return max(candidates, key=lambda x: (x[0],x[1]))


def bulk_fill_supported_area(floors, order, qty, kiln, settings):
    """
    Fill unused supported plate areas in bulk.

    Each physical base position is still stored separately for visualization and
    later mixed-WO stacking, but candidate searching is done ONCE per free
    rectangle instead of once per piece.
    """
    if qty <= 0:
        return 0, []

    fx, fy = float(order["Footprint X"]), float(order["Footprint Y"])
    ph = float(order["Piece Height"])
    remaining = int(qty)
    allocations = []

    for fi, floor in enumerate(floors):
        if remaining <= 0:
            break

        # A one-piece base does not increase floor stack height beyond ph.
        new_floor_stack = max(float(floor["stack_zone_height"]), ph)
        if not height_feasible(floors, kiln, settings, fi, new_floor_stack):
            continue

        new_free = []

        for rect in floor["free"]:
            if remaining <= 0:
                new_free.append(rect)
                continue

            fit = best_grid_fit(rect, fx, fy, float(settings.gap_mm))
            if fit is None:
                new_free.append(rect)
                continue

            nfit, _, pw, phoriz, orient, nx, ny = fit
            take = min(remaining, nfit)
            if take <= 0:
                new_free.append(rect)
                continue

            # Fill row-major. All base placements start as one piece high.
            placed = 0
            used_rows = 0
            last_row_count = 0

            for iy in range(ny):
                if placed >= take:
                    break
                row_count = min(nx, take - placed)
                if row_count <= 0:
                    break

                used_rows += 1
                last_row_count = row_count

                for ix in range(row_count):
                    x = float(rect["x"]) + ix * (pw + settings.gap_mm)
                    y = float(rect["y"]) + iy * (phoriz + settings.gap_mm)

                    floor["placements"].append({
                        "x": x, "y": y, "w": pw, "h": phoriz,
                        "orientation": orient,
                        "plate_zone": rect.get("plate_zone",""),
                        "geometry": order["Geometry"],
                        "D":float(order["D"]),"T":float(order["T"]),"H":float(order["H"]),
                        "hole_diameter":float(order["H"]) if order["Geometry"]=="CIRCULAR" else 0.0,
                        "stack_height": ph,
                        "top_w": pw,
                        "top_h": phoriz,
                        "segments": [{
                            "Work Order": order["Work Order"],
                            "Qty": 1,
                            "z0": 0.0,
                            "z1": ph,
                            "Geometry": order["Geometry"],
                            "Piece Height": ph,
            "Loading Orientation": order.get("Loading Orientation", ""),
                            "D":float(order["D"]),"T":float(order["T"]),"H":float(order["H"]),
                            "Placement Mode":"BASE",
                        }],
                    })
                    placed += 1

            floor["stack_zone_height"] = new_floor_stack
            remaining -= placed
            allocations.append({
                "floor": fi,
                "qty": placed,
                "mode": "BULK SAME FLOOR / NEW POSITIONS"
            })

            # Keep only meaningful residual free rectangles.
            # 1) unused full rows above filled grid
            used_height = used_rows * phoriz + max(used_rows-1,0) * settings.gap_mm
            top_h = float(rect["h"]) - used_height - settings.gap_mm
            if top_h > 1:
                new_free.append({
                    "x": rect["x"],
                    "y": float(rect["y"]) + used_height + settings.gap_mm,
                    "w": rect["w"],
                    "h": top_h,
                    "plate_zone": rect.get("plate_zone",""),
                })

            # 2) residual width on partially used last row
            if used_rows > 0 and last_row_count < nx:
                used_width = last_row_count * pw + max(last_row_count-1,0) * settings.gap_mm
                right_w = float(rect["w"]) - used_width - settings.gap_mm
                if right_w > 1:
                    last_y = float(rect["y"]) + (used_rows-1) * (phoriz + settings.gap_mm)
                    new_free.append({
                        "x": float(rect["x"]) + used_width + settings.gap_mm,
                        "y": last_y,
                        "w": right_w,
                        "h": phoriz,
                        "plate_zone": rect.get("plate_zone",""),
                    })

        floor["free"] = new_free

    return int(qty) - remaining, allocations


def bulk_nest_inside_circular_holes(floors, order, qty, kiln, settings):
    """Use the *plan-view void* of a real circular host hole as supported floor area.

    Factory-photo controlled interpretation:
      - host must be a circular part with a genuine center hole H;
      - circular nested pieces fit by radius;
      - rectangular/upright Hin Khat Phuen fit only when all four footprint corners
        stay inside the circular hole;
      - multiple pieces occupy distinct x/y positions inside the hole;
      - Hin Khat Phuen remains NO STACK; its upright height is included in floor height;
      - this never bypasses kiln/furniture total-height feasibility.
    """
    if qty<=0 or order["Geometry"] not in ("CIRCULAR","RECTANGULAR"):
        return 0,[]

    geom=str(order["Geometry"]).upper()
    fw=max(float(order.get("Footprint X",order.get("D",0)) or 0),1.0)
    fh=max(float(order.get("Footprint Y",order.get("H",0)) or 0),1.0)
    piece_h=max(float(order.get("Piece Height",order.get("T",0)) or 0),1.0)
    gap=max(float(settings.gap_mm),0.0)
    khat=contains_khat_phuen(order)
    remaining=int(qty); alloc=[]

    def _overlap(a,b):
        return (a[0] < b[0]+b[2]+gap-1e-9 and a[0]+a[2]+gap > b[0]+1e-9 and
                a[1] < b[1]+b[3]+gap-1e-9 and a[1]+a[3]+gap > b[1]+1e-9)

    for fi,floor in enumerate(floors):
        if remaining<=0: break
        for pi,p in enumerate(floor.get("placements",[])):
            if remaining<=0: break
            if str(p.get("geometry","")).upper()!="CIRCULAR": continue
            hole=float(p.get("hole_diameter",0) or 0)
            # Some legacy placements keep the host H only in the first segment.
            if hole<=0 and p.get("segments"):
                hole=float(p["segments"][0].get("H",0) or 0)
            if hole<=0: continue
            rad=max(hole/2-gap/2,0)
            if rad<=0: continue
            cx=float(p.get("x",0))+float(p.get("w",0))/2
            cy=float(p.get("y",0))+float(p.get("h",0))/2

            # Fast whole-footprint rejection.
            if geom=="CIRCULAR":
                if max(fw,fh)/2 + gap/2 > rad+1e-9: continue
            else:
                if math.hypot(fw/2,fh/2) + gap/2 > rad+1e-9: continue

            proposed_floor=max(float(floor.get("stack_zone_height",0) or 0),piece_h)
            if not height_feasible(floors,kiln,settings,floor_index=fi,proposed_floor_stack=proposed_floor):
                continue

            occupied=[]
            for seg in p.get("nested_segments",[]):
                sx=float(seg.get("Nested x mm",cx-float(seg.get("Nested Footprint W mm",seg.get("D",1)))/2))
                sy=float(seg.get("Nested y mm",cy-float(seg.get("Nested Footprint H mm",seg.get("D",1)))/2))
                sw=max(float(seg.get("Nested Footprint W mm",seg.get("D",1)) or 1),1)
                sh=max(float(seg.get("Nested Footprint H mm",seg.get("D",1)) or 1),1)
                occupied.append((sx,sy,sw,sh))

            # Generate a center-biased regular grid inside the hole.  The corner/radius
            # test makes every accepted rectangular footprint physically inside the void.
            pitchx=fw+gap; pitchy=fh+gap
            nx=max(int(hole//pitchx)+2,1); ny=max(int(hole//pitchy)+2,1)
            candidates=[]
            for iy in range(-ny,ny+1):
                for ix in range(-nx,nx+1):
                    pcx=cx+ix*pitchx; pcy=cy+iy*pitchy
                    x0=pcx-fw/2; y0=pcy-fh/2
                    if geom=="CIRCULAR":
                        ok=math.hypot(pcx-cx,pcy-cy)+max(fw,fh)/2+gap/2 <= rad+1e-9
                    else:
                        corners=((x0,y0),(x0+fw,y0),(x0,y0+fh),(x0+fw,y0+fh))
                        ok=all(math.hypot(xx-cx,yy-cy)+gap/2 <= rad+1e-9 for xx,yy in corners)
                    if ok:
                        candidates.append((math.hypot(pcx-cx,pcy-cy),x0,y0))
            candidates.sort(key=lambda z:z[0])

            host_wo=p.get("segments",[{}])[0].get("Work Order","")
            host_cat=p.get("segments",[{}])[0].get("Category",p.get("Category",""))
            for _,x0,y0 in candidates:
                if remaining<=0: break
                rect=(x0,y0,fw,fh)
                if any(_overlap(rect,o) for o in occupied): continue
                fit_measure=max(fw,fh) if geom=="CIRCULAR" else math.hypot(fw,fh)
                seg={
                    "Work Order":order["Work Order"],"Qty":1,
                    "Host Work Order":host_wo,"Host Category":host_cat,
                    "Host Hole Diameter":hole,
                    "Nesting Clearance mm":max(hole-fit_measure,0),
                    "Required Fit Diameter mm":fit_measure,
                    "Nesting Fit Rule":("CIRCLE IN HOST HOLE" if geom=="CIRCULAR" else "ALL RECTANGLE CORNERS INSIDE HOST HOLE"),
                    "z0":0.0,"z1":piece_h,
                    "Geometry":geom,"Piece Height":piece_h,
                    "D":float(order.get("D",0)),"T":float(order.get("T",0)),"H":float(order.get("H",0)),
                    "Nested Footprint W mm":fw,"Nested Footprint H mm":fh,
                    "Nested x mm":x0,"Nested y mm":y0,
                    "Loading Orientation":order.get("Loading Orientation",""),
                    "Stack Allowed":bool(order.get("Stack Allowed",True)),
                    "Placement Mode":("NESTED IN CIRCULAR HOLE / UPRIGHT NO STACK" if khat else "NESTED IN CIRCULAR HOLE")
                }
                p.setdefault("nested_segments",[]).append(seg)
                occupied.append(rect)
                floor["stack_zone_height"]=proposed_floor
                p["stack_height"]=max(float(p.get("stack_height",0) or 0),piece_h)
                remaining-=1
                alloc.append({"floor":fi,"placement":pi,"qty":1,
                              "mode":"KHAT PHUEN UPRIGHT GRID IN R-HOLE" if khat else ("RECTANGULAR IN CIRCULAR HOLE" if geom=="RECTANGULAR" else "CIRCULAR IN CIRCULAR HOLE")})
    return int(qty)-remaining,alloc

def bulk_stack_existing(floors, order, qty, kiln, settings):
    """
    Add the permitted direct-stack layer across compatible positions in one pass.

    This preserves the V4.5 rule (floor area first, limited stacking second)
    while avoiding O(N^2) repeated stack searches.
    """
    if qty <= 0 or not settings.allow_mixed_stack or kiln["Type"] == "RESINOID":
        return 0, []
    if "Stack Allowed" in order.index and not bool(order.get("Stack Allowed", True)):
        return 0, []

    ph = float(order["Piece Height"])
    remaining = int(qty)
    allocations = []

    for fi, floor in enumerate(floors):
        if remaining <= 0:
            break

        for pi, p in enumerate(floor["placements"]):
            if remaining <= 0:
                break

            # Immediate supporting footprint = topmost product footprint
            # currently present at this stack position.
            sw = float(p.get("top_w", p["w"]))
            sh = float(p.get("top_h", p["h"]))
            fx = float(order["Footprint X"])
            fy = float(order["Footprint Y"])

            normal_ok = fx <= sw + 1e-9 and fy <= sh + 1e-9
            rotated_ok = fy <= sw + 1e-9 and fx <= sh + 1e-9

            if not (normal_ok or rotated_ok):
                continue

            if normal_ok:
                upper_w, upper_h, upper_orientation = fx, fy, "NORMAL"
            else:
                upper_w, upper_h, upper_orientation = fy, fx, "ROTATED 90°"
            current_piece_count = sum(int(seg.get("Qty",0)) for seg in p.get("segments",[]))
            cap = stack_piece_capacity(
                order, p["stack_height"], kiln, settings,
                current_piece_count=current_piece_count
            )
            if cap <= 0:
                continue

            take = min(remaining, cap)
            qz=max(float(getattr(settings,"quartz_separator_mm",2.0)),0.0)
            sep_count=take if current_piece_count>0 else max(take-1,0)
            new_stack = float(p["stack_height"]) + take*ph + sep_count*qz
            new_floor_stack = max(float(floor["stack_zone_height"]), new_stack)

            if not height_feasible(floors, kiln, settings, fi, new_floor_stack):
                continue

            z0 = float(p["stack_height"])
            p["segments"].append({
                "Work Order": order["Work Order"],
                "Qty": take,
                "z0": z0,
                "z1": new_stack,
                "Geometry": order["Geometry"],
                "Piece Height": ph,
            "Loading Orientation": order.get("Loading Orientation", ""),
            "D": float(order.get("D",0) or 0),
            "T": float(order.get("T",0) or 0),
            "H": float(order.get("H",0) or 0),
            "D Raw": order.get("D Raw",""),
            "T Raw": order.get("T Raw",""),
            "H Raw": order.get("H Raw",""),
            })
            p["stack_height"] = new_stack
            p["top_w"] = upper_w
            p["top_h"] = upper_h
            p["top_orientation"] = upper_orientation
            floor["stack_zone_height"] = new_floor_stack

            remaining -= take
            allocations.append({
                "floor": fi,
                "placement": pi,
                "qty": take,
                "mode": "BULK TOP STACK / MIXED WO"
            })

    return int(qty) - remaining, allocations



def bulk_stack_final_top_level(floors, order, qty, kiln, settings):
    """
    Final top-level loading rule confirmed from factory photographs.

    Use only after another supported furniture floor cannot be opened.
    Intermediate floors still require valid I-block/support clearance.
    The final top loaded floor has no upper refractory shelf, so a tall part
    or valid direct stack may use the remaining usable kiln height.
    """
    if qty <= 0 or not floors or kiln["Type"] == "RESINOID":
        return 0, []
    if "Stack Allowed" in order.index and not bool(order.get("Stack Allowed", True)):
        return 0, []

    fi = len(floors) - 1
    floor = floors[fi]
    usable = max(float(kiln["H mm"]) - float(settings.top_bottom_clearance_mm), 1.0)
    lower_h = total_height(floors[:-1], kiln, settings) if len(floors) > 1 else 0.0
    if not math.isfinite(lower_h):
        return 0, []

    plate_t = float(floor.get("plate_t", settings.shelf_mm))
    top_available_stack_h = usable - lower_h - plate_t
    if top_available_stack_h <= 0:
        return 0, []

    ph = max(float(order["Piece Height"]), 1e-9)
    fx = float(order["Footprint X"])
    fy = float(order["Footprint Y"])
    remaining = int(qty)
    allocations = []

    for pi, p in enumerate(floor.get("placements", [])):
        if remaining <= 0:
            break

        sw = float(p.get("top_w", p["w"]))
        sh = float(p.get("top_h", p["h"]))
        normal_ok = fx <= sw + 1e-9 and fy <= sh + 1e-9
        rotated_ok = fy <= sw + 1e-9 and fx <= sh + 1e-9
        if not (normal_ok or rotated_ok):
            continue

        if normal_ok:
            upper_w, upper_h, upper_orientation = fx, fy, "NORMAL"
        else:
            upper_w, upper_h, upper_orientation = fy, fx, "ROTATED 90°"

        current_h = float(p.get("stack_height", 0.0))
        qz=max(float(getattr(settings,"quartz_separator_mm",2.0)),0.0)
        existing_count=sum(int(seg.get("Qty",0)) for seg in p.get("segments",[]))
        avail=max(top_available_stack_h-current_h,0.0)
        extra_cap=max(int(avail//max(ph+qz,1e-9)),0) if existing_count>0 else max(int((avail+qz)//max(ph+qz,1e-9)),0)
        if extra_cap <= 0:
            continue

        take = min(remaining, extra_cap)
        sep_count=take if existing_count>0 else max(take-1,0)
        new_stack = current_h + take*ph + sep_count*qz
        proposed_floor_stack = max(float(floor.get("stack_zone_height", 0.0)), new_stack)

        if not height_feasible(
            floors, kiln, settings,
            floor_index=fi, proposed_floor_stack=proposed_floor_stack
        ):
            continue

        z0 = current_h
        p.setdefault("segments", []).append({
            "Work Order": order["Work Order"],
            "Qty": take,
            "z0": z0,
            "z1": new_stack,
            "Geometry": order["Geometry"],
            "Piece Height": ph,
            "Loading Orientation": order.get("Loading Orientation", ""),
            "D": float(order.get("D", 0) or 0),
            "T": float(order.get("T", 0) or 0),
            "H": float(order.get("H", 0) or 0),
            "Placement Mode": "FINAL TOP LEVEL / NO UPPER SHELF",
        })
        p["stack_height"] = new_stack
        p["top_w"] = upper_w
        p["top_h"] = upper_h
        p["top_orientation"] = upper_orientation
        floor["stack_zone_height"] = proposed_floor_stack

        remaining -= take
        allocations.append({
            "floor": fi,
            "placement": pi,
            "qty": take,
            "mode": "FINAL TOP LEVEL / NO UPPER SHELF"
        })

    return int(qty) - remaining, allocations


def open_floor_and_bulk_fill(floors, order, qty, kiln, settings):
    """
    Create ONE new furniture floor and fill its supported plate zones in bulk.
    """
    if qty <= 0:
        return 0, []

    f = new_floor(kiln, settings, order, floors)
    if f is None:
        return 0, []

    ph = float(order["Piece Height"])
    f["stack_zone_height"] = ph

    if not height_feasible(
        floors, kiln, settings,
        adding_floor_stack=ph,
        new_floor_obj=f
    ):
        return 0, []

    floors.append(f)
    placed, alloc = bulk_fill_supported_area(
        [floors[-1]], order, qty, kiln, settings
    )

    # Correct local floor index in allocations.
    real_index = len(floors)-1
    for a in alloc:
        a["floor"] = real_index
        a["mode"] = "BULK NEW FLOOR / REFRACTORY FURNITURE"

    if placed <= 0:
        floors.pop()
        return 0, []

    return placed, alloc

def pack_order(floors, order, requested, weight_cap, volume_cap, kiln, settings):
    target = int(min(requested, weight_cap, volume_cap))
    remaining = target
    allocations = []

    # Guard prevents unexpected infinite loops while keeping normal jobs fast.
    safety = 0
    while remaining > 0 and safety < 100:
        safety += 1
        progress = 0

        # 0) Fill usable circular-host hole space with compatible circular OR rectangular parts before opening more plate area.
        nested, alloc = bulk_nest_inside_circular_holes(floors, order, remaining, kiln, settings)
        if nested:
            remaining -= nested
            progress += nested
            allocations.extend(alloc)
        if remaining <= 0:
            break

        # 1) Fill all unused supported plate area in bulk.
        placed, alloc = bulk_fill_supported_area(
            floors, order, remaining, kiln, settings
        )
        if placed:
            remaining -= placed
            progress += placed
            allocations.extend(alloc)

        if remaining <= 0:
            break

        # 2) Use the limited direct stack layer in one pass.
        stacked, alloc = bulk_stack_existing(
            floors, order, remaining, kiln, settings
        )
        if stacked:
            remaining -= stacked
            progress += stacked
            allocations.extend(alloc)

        if remaining <= 0:
            break

        # 3) Open one new supported furniture floor and fill it in bulk.
        opened, alloc = open_floor_and_bulk_fill(
            floors, order, remaining, kiln, settings
        )
        if opened:
            remaining -= opened
            progress += opened
            allocations.extend(alloc)

        # 4) If no more supported floor can be opened and normal I-block-limited
        # stacking made no progress, use the remaining kiln height on the FINAL
        # TOP floor. Factory photos confirm this loading practice.
        if remaining > 0 and opened <= 0 and progress <= 0:
            topped, alloc = bulk_stack_final_top_level(
                floors, order, remaining, kiln, settings
            )
            if topped:
                remaining -= topped
                progress += topped
                allocations.extend(alloc)

        if progress <= 0:
            break

    return target - remaining, allocations


def flatten_floor_plan(load_id, floors):
    rows=[]
    for fi,floor in enumerate(floors,start=1):
        ib=None
        is_top = (fi == len(floors))
        if floor.get("plate_name")!="METAL FRAME" and CURRENT_SETTINGS is not None and not is_top:
            ib=select_iblock(floor["stack_zone_height"],CURRENT_SETTINGS)
        for pi,p in enumerate(floor["placements"],start=1):
            sid=f"F{fi}-S{pi}"
            common={
                "Load ID":load_id,"Floor":fi,"Stack ID":sid,
                "x mm":p["x"],"y mm":p["y"],"Plate Zone":p.get("plate_zone",""),
                "Plate":floor.get("plate_name",""),"Plate L mm":floor.get("plate_l",0),
                "Plate W mm":floor.get("plate_w",0),"Plate T mm":floor.get("plate_t",0),
                "Plate Cols":floor.get("plate_cols",0),"Plate Rows":floor.get("plate_rows",0),
                "Plates / Floor":floor.get("plate_count",0),"Support Nodes / Floor":floor.get("support_nodes",0),
                "I-block":txt(ib.get("I-block","")) if ib else "",
                "I-block Height mm":num(ib.get("Height mm",0)) if ib else 0,
                "Floor Pitch mm":(
                    (float(floor.get("plate_t", CURRENT_SETTINGS.shelf_mm)) + float(floor.get("stack_zone_height",0)))
                    if (CURRENT_SETTINGS is not None and floor.get("plate_name")!="METAL FRAME" and is_top)
                    else (floor_pitch(floor,{"Type":"VITRIFIED","Fixed Levels":0},CURRENT_SETTINGS)
                          if CURRENT_SETTINGS is not None and floor.get("plate_name")!="METAL FRAME" else 0)
                ),
                "Top Level":("YES - NO UPPER SHELF / NO I-BLOCK ABOVE" if is_top else "NO"),
                "Floor Stack Zone Height mm":floor["stack_zone_height"],
            }
            for si,seg in enumerate(p["segments"],start=1):
                r=common.copy();r.update({
                    "Stack Segment":si,"Footprint W mm":p["w"],"Footprint H mm":p["h"],
                    "Orientation":p["orientation"],"Base Geometry":p["geometry"],
                    "D mm":seg.get("D",p.get("D",0)),"T mm":seg.get("T",p.get("T",0)),
                    "H mm":seg.get("H",p.get("H",0)),
                    "Hole Diameter mm":seg.get("H",p.get("H",0)) if seg.get("Geometry",p["geometry"])=="CIRCULAR" else 0,
                    "Placement Mode":seg.get("Placement Mode","BASE/TOP"),
                    "Work Order":seg["Work Order"],"Qty":seg["Qty"],
                    "Segment Bottom mm":seg["z0"],"Segment Top mm":seg["z1"],
                    "Stack Total Height mm":p["stack_height"],
                });rows.append(r)
            for ni,seg in enumerate(p.get("nested_segments",[]),start=1):
                r=common.copy();r.update({
                    "Stack Segment":1000+ni,
                    "x mm":seg.get("Nested x mm",p["x"]),"y mm":seg.get("Nested y mm",p["y"]),
                    "Footprint W mm":seg.get("Nested Footprint W mm",seg.get("D",0)),
                    "Footprint H mm":seg.get("Nested Footprint H mm",seg.get("D",0)),
                    "Orientation":seg.get("Loading Orientation","NESTED IN HOST HOLE"),
                    "Base Geometry":seg.get("Geometry","CIRCULAR"),
                    "D mm":seg.get("D",0),"T mm":seg.get("T",0),"H mm":seg.get("H",0),
                    "Hole Diameter mm":seg.get("H",0) if seg.get("Geometry","CIRCULAR")=="CIRCULAR" else 0,
                    "Placement Mode":seg.get("Placement Mode","NESTED IN CIRCULAR HOLE"),
                    "Host Work Order":seg.get("Host Work Order",""),
                    "Host Hole Diameter mm":seg.get("Host Hole Diameter",0),
                    "Nesting Clearance mm":seg.get("Nesting Clearance mm",0),
                    "Work Order":seg["Work Order"],"Qty":seg["Qty"],
                    "Segment Bottom mm":seg["z0"],"Segment Top mm":seg["z1"],
                    "Stack Total Height mm":p["stack_height"],
                });rows.append(r)
    return rows


def nesting_host_score(order):
    """Geometry-only sequencing aid. Larger circular holes are placed first so
    compatible smaller same-program circular parts can use the otherwise empty hole.
    This changes only physical placement order inside the SAME kiln load/date; it does
    not change customer due date, priority, program, or quantity.
    """
    if txt(order.get("Geometry","")).upper() != "CIRCULAR":
        return 0.0
    h=max(num(order.get("H",0),0),0)
    d=max(num(order.get("D",0),0),0)
    if h<=0 or d<=0 or h>=d:
        return 0.0
    return h


# -------------------------
# Scheduling
# -------------------------

def candidate_kilns(kilns, program, day):
    ids = []
    for i, k in kilns.iterrows():
        if not k["Enabled"] or k["Next Available"] > day or program not in k["Programs"]:
            continue
        if program in {"KM-185", "KM-170", "BK-170"} and k["Type"] != "RESINOID":
            continue
        if program not in {"KM-185", "KM-170", "BK-170"} and k["Type"] == "RESINOID":
            continue
        ids.append(i)

    normal = [i for i in ids if kilns.at[i, "Kiln"] != "T0"]
    t0 = [i for i in ids if kilns.at[i, "Kiln"] == "T0"]
    # T0 is a special auxiliary vitrified kiln for urgent/test work.
    # It is evaluated separately and is NOT part of the normal two-vitrified-start ceiling.
    return normal + t0



def is_small_part(order):
    """Heuristic only; not a capacity rule."""
    fx = float(order.get("Footprint X", 0) or 0)
    fy = float(order.get("Footprint Y", 0) or 0)
    ph = float(order.get("Piece Height", 0) or 0)
    return max(fx, fy) <= 300 and ph <= 100



def is_rectangular_order(order):
    typ=txt(order.get("Type","")).upper()
    geom=txt(order.get("Geometry","")).upper()
    return typ in {"S","T"} or geom=="RECTANGULAR"



def estimated_order_envelope_m3(order, settings):
    """
    Selection-only physical-envelope estimate.

    Uses actual footprint X/Y and piece height plus vertical clearance.
    It is NOT used as the hard packing capacity; the full furniture packing
    engine remains authoritative after kiln selection.
    """
    fx=max(float(order.get("Footprint X",0) or 0),1.0)
    fy=max(float(order.get("Footprint Y",0) or 0),1.0)
    ph=max(float(order.get("Piece Height",0) or 0),1.0)
    qty=max(float(order.get("Qty To Plan",0) or 0),0.0)

    # Direct-stack preference can reduce the number of independent vertical
    # envelopes needed. Keep this conservative by using at most 2.
    stack_factor=max(min(int(settings.max_direct_stack_pieces),2),1)
    effective_positions=math.ceil(qty/stack_factor)

    vertical_zone=ph+float(settings.vertical_clearance_mm)
    return effective_positions*fx*fy*vertical_zone/1e9


def same_program_rectangular_demand_envelope_m3(orders, program, settings):
    if orders is None or orders.empty:
        return 0.0
    rect = orders["_rect_static"] if "_rect_static" in orders.columns else orders.apply(is_rectangular_order,axis=1)
    x=orders[(orders["Program"]==program) & (orders["Qty To Plan"]>0) & rect]
    if x.empty:
        return 0.0
    if "_env_per_piece_static" in x.columns:
        return float((x["Qty To Plan"] * x["_env_per_piece_static"]).sum())
    return float(sum(estimated_order_envelope_m3(r,settings) for _,r in x.iterrows()))

def same_program_rectangular_demand_kg(orders, program):
    if orders is None or orders.empty:
        return 0.0
    rect = orders["_rect_static"] if "_rect_static" in orders.columns else orders.apply(is_rectangular_order,axis=1)
    x=orders[(orders["Program"]==program) & (orders["Qty To Plan"]>0) & rect]
    if x.empty:
        return 0.0
    return float((x["Qty To Plan"]*x["Weight kg/pc"]).sum())


def same_program_rectangular_qty(orders, program):
    if orders is None or orders.empty:
        return 0
    rect = orders["_rect_static"] if "_rect_static" in orders.columns else orders.apply(is_rectangular_order,axis=1)
    x=orders[(orders["Program"]==program) & (orders["Qty To Plan"]>0) & rect]
    return int(x["Qty To Plan"].sum()) if not x.empty else 0


def t0_p6_right_size_candidate(kilns, order, orders, settings):
    """Allow P6 to use auxiliary T0 when T0 is the physically right-sized kiln.

    This does NOT make T0 the default P6 kiln.
    It only returns True when:
      - current program is P6,
      - the current part physically fits T0 chamber,
      - same-program remaining demand can reach the selected T0 occupancy target,
      - that same demand is still below the occupancy target of a normal vitrified kiln.

    Exact furniture/pattern and hard weight checks remain downstream authorities.
    """
    if txt(order.get("Program","")).upper()!="P6" or orders is None or orders.empty:
        return False
    t0rows=kilns[kilns["Kiln"].astype(str).str.upper().eq("T0")]
    if t0rows.empty:
        return False
    t0=t0rows.iloc[0]
    fx=max(float(order.get("Footprint X",0) or 0),0)
    fy=max(float(order.get("Footprint Y",0) or 0),0)
    ph=max(float(order.get("Piece Height",0) or 0),0)
    usable_l=max(float(t0.get("L mm",0))-2*float(getattr(settings,"edge_mm",0)),0)
    usable_w=max(float(t0.get("W mm",0))-2*float(getattr(settings,"edge_mm",0)),0)
    usable_h=max(float(t0.get("H mm",0))-float(getattr(settings,"top_bottom_clearance_mm",0)),0)
    footprint_fit=((fx<=usable_l and fy<=usable_w) or (fy<=usable_l and fx<=usable_w))
    if not (footprint_fit and ph<=usable_h):
        return False

    sp=orders[(orders["Program"].astype(str).str.upper()=="P6") & (pd.to_numeric(orders["Qty To Plan"],errors="coerce").fillna(0)>0)].copy()
    if sp.empty:
        return False
    if "_envpc" in sp.columns:
        pool_env=float((pd.to_numeric(sp["Qty To Plan"],errors="coerce").fillna(0)*
                        pd.to_numeric(sp["_envpc"],errors="coerce").fillna(0)).sum())
    elif "_env_per_piece_static" in sp.columns:
        pool_env=float((pd.to_numeric(sp["Qty To Plan"],errors="coerce").fillna(0)*
                        pd.to_numeric(sp["_env_per_piece_static"],errors="coerce").fillna(0)).sum())
    else:
        pool_env=float(sum(estimated_order_envelope_m3(r,settings) for _,r in sp.iterrows()))

    t0_target=float(t0.get("Gross m3",0))*float(settings.target_volume)
    normal=kilns[(kilns["Type"].astype(str).str.upper()=="VITRIFIED") &
                 (~kilns["Kiln"].astype(str).str.upper().isin(["T0","T14"]))]
    if normal.empty:
        normal_target=float("inf")
    else:
        normal_target=float(pd.to_numeric(normal["Gross m3"],errors="coerce").dropna().min())*float(settings.target_volume)

    return pool_env>=t0_target and pool_env<normal_target


def t0_special_candidate(order):
    priority=txt(order.get("Priority","")).upper()
    notes=" ".join([txt(order.get("Notes","")),txt(order.get("Planner Remark","")),txt(order.get("Customer",""))]).upper()
    test_words=("TEST","TRIAL","SAMPLE","ทดลอง","ทดสอบ")
    # Controlled Plan2026 classification: Product Code starting 1 or 4 = test/not-for-sale.
    # Starting 4 = M axis grinding wheel test work. This makes test recognition deterministic.
    product_code=txt(order.get("Product Code","")).strip()
    test_override=txt(order.get("Test Work Override","AUTO")).strip().upper() or "AUTO"
    test_flag=(txt(order.get("Test Work","")).upper().startswith("YES") or product_code.startswith("1"))
    if test_override=="NORMAL": test_flag=False
    elif test_override=="TEST": test_flag=True
    return priority in {"HIGH","OVERDUE","URGENT"} or test_flag or any(w in notes for w in test_words)


def _stage4_program_signature(orders, program):
    if orders is None or len(orders)==0:
        return (0,0.0,0)
    x=orders[(orders["Program"]==program)&(orders["Qty To Plan"]>0)]
    if x.empty:
        return (0,0.0,0)
    qty=int(pd.to_numeric(x["Qty To Plan"],errors="coerce").fillna(0).sum())
    kg=float((pd.to_numeric(x["Qty To Plan"],errors="coerce").fillna(0)*pd.to_numeric(x["Weight kg/pc"],errors="coerce").fillna(0)).sum())
    return (qty,round(kg,1),len(x))

def choose_kiln(kilns, program, day, order, settings, orders=None):
    ids=candidate_kilns(kilns,program,day)
    if orders is not None and ids:
        sig=_stage4_program_signature(orders,program)
        ids=[ki for ki in ids if (int(ki),txt(program),sig) not in STAGE4_HOLD_SIGNATURES]
    if not ids:
        return None

    scored=[]
    small=is_small_part(order)
    rect=is_rectangular_order(order)

    rect_qty=same_program_rectangular_qty(orders,program) if orders is not None else 0
    rect_kg=same_program_rectangular_demand_kg(orders,program) if orders is not None else 0.0
    rect_env=same_program_rectangular_demand_envelope_m3(orders,program,settings) if orders is not None else 0.0

    # SPEED: the same-program pool does not depend on the kiln, so compute it ONCE per call
    # (was recomputed for every candidate kiln). Results are numerically identical.
    _pool_cache=None
    if orders is not None and not orders.empty:
        _pool=orders[(orders["Program"]==program)&(orders["Qty To Plan"]>0)].head(40)
        if not _pool.empty:
            _pk=float((_pool["Qty To Plan"]*_pool["Weight kg/pc"]).sum())
            _pe=float(sum(estimated_order_envelope_m3(r,settings) for _,r in _pool.iterrows()))
            _hs=[max(float(h or 0),0.0) for h in _pool["Piece Height"]] if "Piece Height" in _pool.columns else [0.0]*len(_pool)
            _pool_cache=(_pk,_pe,_hs)

    for ki in ids:
        k=kilns.loc[ki]
        rule=program_rule(program,k["Kiln"])
        maxkg=min(float(k["Physical kg"]),float(rule["maxkg"]))
        minkg=float(rule.get("minkg",0))
        if program=="P3" and k["Kiln"]=="T14":
            maxkg=min(float(k["Physical kg"]),4000)
            minkg=3800

        gross=float(k["Gross m3"])
        target_env=gross*float(settings.target_volume)

        score=0.0

        if k["Kiln"]=="T0":
            if t0_special_candidate(order):
                # Existing benchmark behavior: urgent/test work prefers auxiliary T0.
                score += 5000
            elif t0_p6_right_size_candidate(kilns,order,orders,settings):
                # Minimal benchmark extension:
                # if P6 cannot efficiently fill a normal kiln but can reach the selected
                # occupancy target in T0, prefer T0 as the right-sized auxiliary resource.
                # Exact physical/furniture/weight validation still follows.
                score += 4500
            else:
                score -= 20000

        if k["Kiln"]=="T14":
            # T14 is the largest kiln and must NOT be chosen just because the
            # part is rectangular. It is preferred only when the available
            # same-program rectangular demand can substantially justify BOTH
            # volume and weight.
            weight_ready = rect_kg >= max(minkg, 0.75*maxkg)
            volume_ready = rect_env >= target_env

            if rect and weight_ready and volume_ready:
                score += 12000
            else:
                # Strong penalty protects T14 from under-filled loads.
                score -= 10000

                # If demand is close to target, keep it possible but not preferred.
                if rect and rect_kg >= 0.9*max(minkg,1) and rect_env >= 0.9*target_env:
                    score += 6000

        # T4 remains preferred for suitable small vitrified parts unless T14
        # has passed its large-load gate above.
        t14_ready = (
            rect
            and rect_kg >= max(3800 if program=="P3" else 0, 0.75*4000 if program=="P3" else 0)
            and rect_env >= (
                float(kilns.loc[kilns["Kiln"]=="T14","Gross m3"].iloc[0])*settings.target_volume
                if (kilns["Kiln"]=="T14").any() else float("inf")
            )
        )

        if small and k["Kiln"]=="T4" and not t14_ready:
            score += 2200

        # Smart combination fit: score a bounded SAME-PROGRAM candidate pool,
        # while upstream due-date/priority ordering remains authoritative.
        wo_kg=float(order["Qty To Plan"])*float(order["Weight kg/pc"])
        wo_env=estimated_order_envelope_m3(order,settings)
        pool_kg,pool_env=wo_kg,wo_env
        height_fit=min(max(float(order.get("Piece Height",0) or 0),0.0)/max(float(k.get("Usable H mm",k.get("Height mm",1)) or 1),1.0),1.0)
        if _pool_cache is not None:
            pool_kg,pool_env,_hs=_pool_cache
            usable=max(float(k.get("Usable H mm",k.get("Height mm",1)) or 1),1.0)
            height_fit=min(sum(_hs)/usable,1.0) if _hs else 0.0

        weight_fit=min(pool_kg/max(maxkg,1),1.0)
        volume_fit=min(pool_env/max(gross*settings.target_volume,1e-9),1.0)
        # Volume primary, then weight, then vertical-use opportunity.
        score += volume_fit*1100 + weight_fit*650 + height_fit*300
        score += (volume_fit*.55 + weight_fit*.30 + height_fit*.15)*500

        # Avoid selecting an unnecessarily large chamber when a same-program
        # combination still leaves most of its gross volume empty.
        if gross>0 and pool_env < gross*0.35:
            score -= (gross-pool_env)*100

        score -= ki*0.001
        scored.append((score,ki))

    return max(scored,key=lambda x:x[0])[1] if scored else None



def remaining_same_program_summary(orders, program):
    x=orders[(orders["Program"]==program)&(orders["Qty To Plan"]>0)].copy()
    if x.empty:
        return {"qty":0,"kg":0.0,"wo":0,"urgent_wo":0}
    kg=float((x["Qty To Plan"]*x["Weight kg/pc"]).sum())
    urgent=int((x["Priority"].astype(str).str.upper().isin(["HIGH","OVERDUE"])).sum())
    return {"qty":int(x["Qty To Plan"].sum()),"kg":kg,"wo":len(x),"urgent_wo":urgent}




# V1.5 bounded Stage-4 candidate selection.
# Planning rules are unchanged: due date / priority order remains authoritative.
# The optimization limits expensive exact furniture packing to the earliest
# physically relevant same-program WOs, then progressively widens only if the
# load still needs more compatible material.
def _stage4_candidate_window(same_program, kiln, maxkg, settings, start_n=18, max_n=60):
    if same_program is None or same_program.empty:
        return same_program
    x=same_program.copy()
    # Preserve caller's sort order. Build a bounded prefix large enough to
    # theoretically cover the kiln by weight and estimated occupied envelope.
    gross=max(float(kiln.get("Gross m3",0) or 0),1e-9)
    target_env=gross*float(settings.target_volume)*1.20
    target_kg=max(float(maxkg)*1.10,1.0)
    kg=0.0; env=0.0; take=0
    for _,r in x.iterrows():
        q=max(float(r.get("Qty To Plan",0) or 0),0.0)
        w=max(float(r.get("Weight kg/pc",0) or 0),0.0)
        e=max(float(r.get("_env_per_piece_static",0) or 0),0.0)
        kg += q*w
        env += q*e
        take += 1
        if take>=start_n and (kg>=target_kg or env>=target_env):
            break
        if take>=max_n:
            break
    take=max(min(take,max_n),min(start_n,len(x)))
    return x.iloc[:take].copy()


def _stage4_extra_window(all_same_program, used_indices, block=12, max_total=72):
    if all_same_program is None or all_same_program.empty:
        return all_same_program
    used=set(used_indices or [])
    rem=all_same_program.loc[~all_same_program.index.isin(used)]
    if rem.empty:
        return rem
    allowed=max(max_total-len(used),0)
    if allowed<=0:
        return rem.iloc[:0]
    return rem.iloc[:min(block,allowed)].copy()

def build_plan(prepared, kilns, settings):
    global STAGE4_HOLD_SIGNATURES
    STAGE4_HOLD_SIGNATURES=set()
    orders = prepared[prepared.get("Release Candidate", prepared["Include"])].copy().reset_index(drop=True)
    if "Verified Ready for Firing Qty" in orders.columns:
        orders["Qty To Plan"] = pd.to_numeric(orders["Verified Ready for Firing Qty"], errors="coerce").fillna(0).clip(lower=0)
    else:
        orders["Qty To Plan"] = orders["Effective Qty"]

    # V1.4 PERFORMANCE ONLY: cache static geometry classifications used repeatedly
    # by Stage 4. These values do not change as quantities are allocated, so this
    # removes thousands of repeated DataFrame.apply/row calculations without
    # changing kiln selection or packing rules.
    orders["_rect_static"] = orders.apply(is_rectangular_order, axis=1)
    orders["_nest_host_static"] = orders.apply(nesting_host_score, axis=1)
    def _env_per_piece(r):
        q=max(float(r.get("Qty To Plan",0) or 0),1.0)
        try:
            return float(estimated_order_envelope_m3(r,settings))/q
        except Exception:
            return 0.0
    orders["_env_per_piece_static"] = orders.apply(_env_per_piece, axis=1)

    loads, details, floor_rows, exceptions = [], [], [], []
    # Planning Start is the first firing target date selected by the planner.
    # next_workday() preserves that date when it is a configured working day.
    day = settings.planning_start  # selected start date is always day 1
    load_no = 0
    guard = 0

    while (orders["Qty To Plan"] > 0).any() and guard < 730:
        guard += 1
        if day.weekday() not in settings.working_days and day != settings.planning_start:
            day += timedelta(days=1)
            continue

        vitrified_starts = 0
        resin_starts = 0
        vitrified_programs_started = set()
        resin_programs_started = set()
        daily_attempts = 0

        # The daily start limit applies ONLY to vitrified kilns.
        # Resin kilns R4/R5/R6 may start independently whenever parts are ready
        # and the selected resin kiln is available/compatible.
        while daily_attempts < 20:
            daily_attempts += 1
            if STAGE4_PROGRESS_CALLBACK is not None:
                try:
                    STAGE4_PROGRESS_CALLBACK({"phase":"4A","day":day,"attempt":daily_attempts,"remaining":int((orders["Qty To Plan"]>0).sum()),"loads":len(loads)})
                except Exception:
                    pass
            first_idx = kiln_idx = None

            # Planning Start is the first firing TARGET date selected by Planning.
            # Upstream-incomplete WOs remain plannable and are flagged EXPEDITE REQUIRED.
            candidates = orders[orders["Qty To Plan"]>0].copy()
            candidates["_pull_ready_rank"] = candidates["Readiness"].apply(
                lambda x: 0 if x == "READY / FIRING PREPARATION" else 1
            )
            candidates = candidates.sort_values(
                ["_pull_ready_rank","_due","Priority Rank","Earliest Normal Firing","Source Row"],
                ascending=[True,True,True,True,True], na_position="last"
            )
            for oi, order in candidates.iterrows():
                ki = choose_kiln(kilns, order["Program"], day, order, settings, orders)
                if ki is not None:
                    candidate_type = txt(kilns.loc[ki].get("Type","")).upper()
                    if candidate_type == "VITRIFIED" and vitrified_starts >= 2 and txt(kilns.loc[ki,"Kiln"]).upper() != "T0":
                        continue
                    if candidate_type == "RESINOID" and resin_starts >= 2:
                        continue

                    # Do not force a second kiln of the same program.
                    # Prefer another READY program, with due date deciding its order.
                    started_set = vitrified_programs_started if candidate_type == "VITRIFIED" else resin_programs_started
                    if order["Program"] in started_set:
                        alternatives = candidates[
                            (candidates["Program"] != order["Program"])
                            & (candidates["_pull_ready_rank"] == 0)
                        ]
                        alt_available = False
                        for _, alt in alternatives.iterrows():
                            aki = choose_kiln(kilns, alt["Program"], day, alt, settings, orders)
                            if aki is not None and txt(kilns.loc[aki,"Type"]).upper() == candidate_type:
                                alt_available = True
                                break
                        if alt_available:
                            continue
                    first_idx, kiln_idx = oi, ki
                    break

            if first_idx is None:
                break

            first = orders.loc[first_idx]
            kiln = kilns.loc[kiln_idx]
            program = first["Program"]
            if STAGE4_PROGRESS_CALLBACK is not None:
                try:
                    STAGE4_PROGRESS_CALLBACK({"phase":"4B","day":day,"kiln":kiln["Kiln"],"program":program,"loads":len(loads)})
                except Exception:
                    pass
            rule = program_rule(program, kiln["Kiln"])

            maxkg = min(float(kiln["Physical kg"]), float(rule["maxkg"]))
            minkg = float(rule.get("minkg", 0))
            if program == "P3" and kiln["Kiln"] == "T14":
                maxkg = min(float(kiln["Physical kg"]), 4000)
                minkg = 3800
            maxvol = float(kiln["Gross m3"]) * settings.max_volume

            floors = []
            total_qty = 0
            total_weight = 0.0
            total_space = 0.0
            detail_lines = []

            # All same-program WOs may fill this load.
            # Primary sequence remains priority/due date.
            # For T14 rectangular-heavy loads, rectangular WOs are grouped first
            # because they pack efficiently together and are the preferred T14 use.
            all_same_program = orders[
                (orders["Qty To Plan"]>0) & (orders["Program"]==program)
            ].copy()
            all_same_program["_rect"] = all_same_program["_rect_static"]
            all_same_program["_nest_host"] = all_same_program["_nest_host_static"]
            if kiln["Kiln"]=="T14" and bool(first.get("Type","") in ["S","T"] or first.get("Geometry","")=="RECTANGULAR"):
                all_same_program = all_same_program.sort_values(
                    ["_rect","Due Date","Priority Rank"],
                    ascending=[False,True,True],
                    na_position="last", kind="stable"
                )
            else:
                all_same_program = all_same_program.sort_values(
                    ["Due Date","Priority Rank","_nest_host","D"],
                    ascending=[True,True,False,False],
                    na_position="last", kind="stable"
                )
            same_program = _stage4_candidate_window(all_same_program, kiln, maxkg, settings)
            if STAGE4_PROGRESS_CALLBACK is not None:
                try:
                    STAGE4_PROGRESS_CALLBACK({"phase":"4C","day":day,"kiln":kiln["Kiln"],"program":program,"candidates":len(all_same_program),"shortlist":len(same_program),"loads":len(loads)})
                except Exception:
                    pass
            stage4_used_indices=[]

            for oi, order in same_program.iterrows():
                stage4_used_indices.append(oi)

                weight_cap = math.floor(max(maxkg - total_weight, 0) / order["Weight kg/pc"]) if order["Weight kg/pc"] > 0 else 0
                # V6.8 DIRECT PLAN 2026: physical furniture packing is authoritative for volume occupancy.
                # Do NOT stop a load from raw per-piece Unit Space m3 before the actual
                # plate/floor/height model has attempted to use the kiln.
                # Weight remains a hard safety/capacity limit.
                volume_cap = int(order["Qty To Plan"])
                requested = int(order["Qty To Plan"])
                remaining_before_this_load = requested

                if weight_cap <= 0 or volume_cap <= 0:
                    continue

                packed, allocations = pack_order(
                    floors, order, requested, weight_cap, volume_cap, kiln, settings
                )
                if packed <= 0:
                    continue

                lw = packed * order["Weight kg/pc"]
                lv = packed * order["Unit Space m3"]

                total_qty += packed
                total_weight += lw
                total_space += lv
                orders.at[oi, "Qty To Plan"] -= packed

                floor_ids = sorted({a["floor"] + 1 for a in allocations})
                modes = sorted({a["mode"] for a in allocations})
                detail_lines.append({
                    "Order Index": oi,
                    "Qty": packed,
                    "Weight": lw,
                    "Remaining Before Load": remaining_before_this_load,
                    "Remaining After Load": int(orders.at[oi, "Qty To Plan"]),
                    "Floors": ",".join(str(x) for x in floor_ids),
                    "Packing Modes": "; ".join(modes),
                })

                if total_weight >= maxkg - 1e-9:
                    break


            # SECOND FILL PASS:
            # If physical volume occupancy is still low and weight remains,
            # retry all same-program WOs after the floor geometry has changed.
            # Earlier WOs can fit newly created floors/plate zones that did not
            # exist during their first pass.
            if detail_lines and total_weight < maxkg - 1e-9:
                for _fill_pass in range(2):
                    used_height_now = total_height(floors,kiln,settings)
                    usable_h_now = max(float(kiln["H mm"])-settings.top_bottom_clearance_mm,1)
                    occ_env_now=0.0
                    for _f in floors:
                        _pitch=floor_pitch(_f,kiln,settings)
                        _occ=sum(float(_p["w"])*float(_p["h"]) for _p in _f["placements"])
                        occ_env_now += _occ*_pitch/1e9
                    occ_now=occ_env_now/float(kiln["Gross m3"]) if kiln["Gross m3"] else 0

                    if occ_now >= settings.target_volume or total_weight >= maxkg-1e-9:
                        break

                    progress=0
                    # Retry only WOs already considered, plus a small next block.
                    # This avoids rescanning hundreds of later WOs against every
                    # existing physical placement. If the kiln remains underfilled,
                    # the next fill pass progressively widens the window.
                    current=orders.loc[
                        orders.index.isin(stage4_used_indices) &
                        (orders["Qty To Plan"]>0) & (orders["Program"]==program)
                    ].copy()
                    current["_nest_host"]=current["_nest_host_static"]
                    current=current.sort_values(["Due Date","Priority Rank","_nest_host","D"],ascending=[True,True,False,False],na_position="last",kind="stable")
                    latest_all=orders[(orders["Qty To Plan"]>0)&(orders["Program"]==program)].copy()
                    latest_all["_nest_host"]=latest_all["_nest_host_static"]
                    latest_all=latest_all.sort_values(["Due Date","Priority Rank","_nest_host","D"],ascending=[True,True,False,False],na_position="last",kind="stable")
                    extra=_stage4_extra_window(latest_all, stage4_used_indices, block=12, max_total=72)
                    if extra is not None and not extra.empty:
                        stage4_used_indices.extend([i for i in extra.index if i not in stage4_used_indices])
                        retry=pd.concat([current,extra],axis=0)
                    else:
                        retry=current

                    for oi,order in retry.iterrows():
                        weight_cap=math.floor(max(maxkg-total_weight,0)/order["Weight kg/pc"]) if order["Weight kg/pc"]>0 else 0
                        if weight_cap<=0:
                            continue
                        requested=int(order["Qty To Plan"])
                        packed,allocations=pack_order(
                            floors,order,requested,weight_cap,requested,kiln,settings
                        )
                        if packed<=0:
                            continue

                        lw=packed*order["Weight kg/pc"]
                        lv=packed*order["Unit Space m3"]
                        total_qty += packed
                        total_weight += lw
                        total_space += lv
                        orders.at[oi,"Qty To Plan"] -= packed
                        progress += packed

                        floor_ids=sorted({a["floor"]+1 for a in allocations})
                        modes=sorted({a["mode"] for a in allocations})
                        existing=next((x for x in detail_lines if x["Order Index"]==oi),None)
                        if existing:
                            existing["Qty"] += packed
                            existing["Weight"] += lw
                            existing["Remaining After Load"]=int(orders.at[oi,"Qty To Plan"])
                            oldflo=set(filter(None,existing["Floors"].split(",")))
                            existing["Floors"]=",".join(sorted(oldflo|{str(x) for x in floor_ids},key=lambda z:int(z)))
                            existing["Packing Modes"]="; ".join(sorted(set(existing["Packing Modes"].split("; "))|set(modes)))
                        else:
                            detail_lines.append({
                                "Order Index":oi,"Qty":packed,"Weight":lw,
                                "Remaining Before Load":requested,
                                "Remaining After Load":int(orders.at[oi,"Qty To Plan"]),
                                "Floors":",".join(str(x) for x in floor_ids),
                                "Packing Modes":"; ".join(modes),
                            })

                        if total_weight >= maxkg-1e-9:
                            break

                    if progress<=0:
                        break

            if STAGE4_PROGRESS_CALLBACK is not None:
                try:
                    STAGE4_PROGRESS_CALLBACK({"phase":"4D","day":day,"kiln":kiln["Kiln"],"program":program,"packed_wo":len(detail_lines),"qty":int(total_qty),"weight":round(total_weight,1),"loads":len(loads)})
                except Exception:
                    pass
            if not detail_lines:
                exceptions.append({
                    "Work Order": first["Work Order"],
                    "Program": program,
                    "Issue": "No verified geometric/furniture loading solution in currently available compatible kiln. Check dimensions, furniture availability, kiln availability, or manual loading pattern."
                })
                orders.at[first_idx, "Qty To Plan"] = 0
                continue

            load_no += 1
            load_id = f"LOAD-{load_no:03d}"
            fp = pd.DataFrame(flatten_floor_plan(load_id, floors))

            cycle = int(rule["cycle"])
            complete = day + timedelta(days=cycle)

            dues = [orders.loc[x["Order Index"], "Due Date"] for x in detail_lines if orders.loc[x["Order Index"], "Due Date"] is not None]
            earliest_due = min(dues) if dues else None

            if earliest_due is None:
                risk = "DUE DATE MISSING"
            elif complete > earliest_due:
                risk = "LATE"
            elif complete >= earliest_due - timedelta(days=settings.risk_days):
                risk = "AT RISK"
            else:
                risk = "ON TRACK"

            used_height = total_height(floors, kiln, settings)
            usable_height = max(float(kiln["H mm"]) - settings.top_bottom_clearance_mm, 1)

            # Solid/product volume is useful for material sanity checking, but it
            # does NOT represent how full the kiln looks. A visually full kiln
            # contains shelves/frames, air gaps, and stacked product envelopes.
            solid_product_volume = sum(
                float(orders.loc[x["Order Index"], "Unit Volume m3"]) * x["Qty"]
                for x in detail_lines
            )
            solid_volume_util = (
                solid_product_volume / float(kiln["Gross m3"])
                if kiln["Gross m3"] else 0
            )

            # Geometric/furniture occupancy:
            # each occupied footprint is extended through that floor's actual pitch.
            # This approximates the 3D envelope that appears occupied in the kiln,
            # including the vertical zone consumed by stacked parts/furniture.
            occupied_envelope_m3 = 0.0
            usable_floor_area_mm2 = max(
                (float(kiln["L mm"]) - 2 * settings.edge_mm)
                * (float(kiln["W mm"]) - 2 * settings.edge_mm),
                1.0,
            )
            floor_area_utils = []

            for floor in floors:
                pitch = floor_pitch(floor, kiln, settings)
                occupied_area = sum(
                    float(p["w"]) * float(p["h"])
                    for p in floor["placements"]
                )
                occupied_envelope_m3 += occupied_area * pitch / 1e9
                floor_area_utils.append(
                    min(occupied_area / usable_floor_area_mm2, 1.0)
                )

            geometric_occupancy_util = (
                occupied_envelope_m3 / float(kiln["Gross m3"])
                if kiln["Gross m3"] else 0
            )
            average_floor_area_util = (
                sum(floor_area_utils) / len(floor_area_utils)
                if floor_area_utils else 0
            )

            # Supported-plate open area is more useful for visual airflow/spacing
            # verification than gross kiln area. This is a proxy, not CFD.
            supported_area_total = 0.0
            occupied_area_total = 0.0
            for floor in floors:
                if floor.get("plate_name") == "METAL FRAME":
                    supported = usable_floor_area_mm2
                else:
                    supported = (
                        float(floor.get("plate_l",0))
                        * float(floor.get("plate_w",0))
                        * float(floor.get("plate_count",0))
                    )
                occupied = sum(float(p["w"])*float(p["h"]) for p in floor["placements"])
                supported_area_total += max(supported,0)
                occupied_area_total += max(occupied,0)

            supported_area_util = (
                min(occupied_area_total/supported_area_total,1.0)
                if supported_area_total > 0 else 0
            )
            open_supported_area_pct = max(1-supported_area_util,0)

            weight_util = total_weight / maxkg if maxkg else 0
            height_util = min(used_height / usable_height, 1)

            # For management, use the binding/visible constraints rather than raw
            # solid abrasive volume. Weight-limited loads can legitimately have
            # low solid-volume percentage.
            # V6.8 DIRECT PLAN 2026 management rule:
            # PRIMARY = physical/geometric kiln occupancy.
            # SECONDARY = weight utilization.
            # Height is diagnostic; it must not make a visibly half-empty kiln
            # appear "100% utilized".
            effective_util = geometric_occupancy_util

            # Furniture summary for this actual load.
            plate_counts = {}
            iblock_counts = {}
            for _f in floors:
                _pn = txt(_f.get("plate_name",""))
                if _pn and _pn != "METAL FRAME":
                    plate_counts[_pn] = plate_counts.get(_pn,0) + int(_f.get("plate_count",0))
                    _ib = select_iblock(_f["stack_zone_height"], settings)
                    if _ib:
                        _in = txt(_ib["I-block"])
                        iblock_counts[_in] = iblock_counts.get(_in,0) + int(_f.get("support_nodes",0))

            furniture_status = "PASS" if furniture_feasible(floors, settings) else "FAIL"

            mixed_floors = 0
            mixed_stacks = 0
            if not fp.empty:
                mixed_floors = int((fp.groupby("Floor")["Work Order"].nunique() > 1).sum())
                mixed_stacks = int((fp.groupby("Stack ID")["Work Order"].nunique() > 1).sum())

            expedite = sum(day < orders.loc[x["Order Index"], "Earliest Normal Firing"] for x in detail_lines)

            if weight_util >= 0.999:
                limiting_constraint = "WEIGHT CAPACITY"
            elif used_height >= usable_height - 1e-6:
                limiting_constraint = "PHYSICAL HEIGHT / FURNITURE"
            elif not furniture_feasible(floors, settings):
                limiting_constraint = "FURNITURE AVAILABILITY"
            elif geometric_occupancy_util < settings.target_volume:
                limiting_constraint = "INSUFFICIENT SAME-PROGRAM DEMAND / PHYSICAL FIT"
            else:
                limiting_constraint = "TARGET VOLUME OCCUPANCY REACHED"

            preferred_min_status = (
                "BELOW PREFERRED PROGRAM WEIGHT"
                if minkg > 0 and total_weight < minkg
                else "WITHIN / ABOVE PREFERRED MIN"
            )

            t14_fit_status = ""
            if kiln["Kiln"]=="T14":
                if geometric_occupancy_util < settings.target_volume or (minkg>0 and total_weight<minkg):
                    t14_fit_status = "T14 UNDER-FILLED - SHOULD USE SMALLER KILN / WAIT-COMBINE"
                else:
                    t14_fit_status = "T14 JUSTIFIED"


            # ------------------------------------------------------
            # RELEASE GATE / EXPLICIT REASON
            # ------------------------------------------------------
            remaining_same = remaining_same_program_summary(orders, program)

            volume_ok = geometric_occupancy_util >= settings.target_volume
            weight_near_limit = weight_util >= 0.90
            weight_at_limit = weight_util >= 0.98
            urgent_due = (
                risk in {"LATE","AT RISK"}
                or any(
                    txt(orders.loc[x["Order Index"],"Priority"]).upper() in {"HIGH","OVERDUE"}
                    for x in detail_lines
                )
            )

            no_more_same_program = remaining_same["qty"] <= 0
            physical_stop = limiting_constraint in {
                "WEIGHT CAPACITY",
                "PHYSICAL HEIGHT / FURNITURE",
                "FURNITURE AVAILABILITY"
            }

            # A low-volume VITRIFIED load should normally WAIT.
            # Resin kilns use fixed metal-frame levels and their 1,000 kg hard limit;
            # the vitrified 80% geometric-occupancy gate is not applicable.
            release_reason = ""
            alternative_action = ""
            release_gate = "HOLD / COMBINE"

            if txt(kiln.get("Type","")).upper() == "RESINOID":
                release_gate = "RELEASE - RESIN KILN"
                release_reason = (
                    f"PB/resinoid load on {kiln['Kiln']}; resin fixed-level packing "
                    f"and {maxkg:.0f} kg hard load limit applied."
                )
                alternative_action = "Continue due-date-first resin sequence on R4/R5/R6."
            elif volume_ok:
                release_gate = "RELEASE"
                release_reason = (
                    f"Physical volume target achieved: "
                    f"{geometric_occupancy_util:.1%} >= {settings.target_volume:.0%}."
                )
                alternative_action = "No combination required."
            elif weight_at_limit:
                release_gate = "RELEASE"
                release_reason = (
                    f"Weight is the binding constraint: {total_weight:.0f} kg "
                    f"({weight_util:.1%} of {maxkg:.0f} kg)."
                )
                alternative_action = "Cannot add significant weight safely; use current load."
            elif physical_stop and no_more_same_program:
                release_gate = "RELEASE"
                release_reason = (
                    f"Physical/furniture constraint prevents further packing and "
                    f"no additional same-program demand remains. Constraint: {limiting_constraint}."
                )
                alternative_action = "Release current load; no compatible quantity remains to combine."
            elif urgent_due and settings.allow_urgent_partial and no_more_same_program:
                release_gate = "RELEASE - DELIVERY EXCEPTION"
                release_reason = (
                    f"Under target ({geometric_occupancy_util:.1%}) but delivery is {risk}; "
                    f"no additional same-program demand remains."
                )
                alternative_action = "Release as documented delivery exception."
            elif urgent_due and settings.allow_urgent_partial and remaining_same["qty"]>0 and physical_stop:
                release_gate = "RELEASE - DELIVERY EXCEPTION"
                release_reason = (
                    f"Delivery is {risk}; compatible demand remains, but current load cannot "
                    f"accept more because of {limiting_constraint}."
                )
                alternative_action = (
                    f"Release current load for delivery protection; plan remaining "
                    f"{remaining_same['qty']} pcs / {remaining_same['kg']:.0f} kg in next compatible load."
                )
            elif settings.allow_partial:
                release_gate = "RELEASE - MANUAL PARTIAL POLICY"
                release_reason = (
                    f"Below primary volume target ({geometric_occupancy_util:.1%}), "
                    f"but manual partial-load policy is enabled."
                )
                alternative_action = (
                    f"Better option: wait/combine with remaining same-program demand "
                    f"{remaining_same['qty']} pcs / {remaining_same['kg']:.0f} kg."
                )
            else:
                release_gate = "HOLD / COMBINE"
                release_reason = (
                    f"Do not release: physical occupancy {geometric_occupancy_util:.1%} "
                    f"is below {settings.target_volume:.0%}, and weight is only {weight_util:.1%}."
                )
                if remaining_same["qty"]>0:
                    alternative_action = (
                        f"Combine with remaining same-program demand: "
                        f"{remaining_same['wo']} WO(s), {remaining_same['qty']} pcs, "
                        f"{remaining_same['kg']:.0f} kg. Repack before creating another load."
                    )
                else:
                    alternative_action = (
                        "No same-program demand remains. Wait for compatible demand unless "
                        "delivery risk requires an approved partial-load exception."
                    )

            decision = release_gate

            # T14 has an additional protection.
            if kiln["Kiln"]=="T14" and t14_fit_status.startswith("T14 UNDER-FILLED"):
                if not (urgent_due and settings.allow_urgent_partial):
                    decision = "HOLD / MOVE TO SMALLER KILN"
                    release_reason = (
                        f"T14 is under-filled: volume {geometric_occupancy_util:.1%}, "
                        f"weight {weight_util:.1%}. T14 is not justified."
                    )
                    alternative_action = "Repack same-program demand into a smaller compatible kiln or wait-combine."


            loads.append({
                "Load ID": load_id, "Load Date": day, "Kiln": kiln["Kiln"],
                "Program": program, "Furniture": kiln["Furniture"],
                "WO Lines": len(detail_lines), "Qty pcs": total_qty,
                "Weight kg": round(total_weight, 2),
                "Program Preferred Min kg": minkg,
                "Weight Limit kg": maxkg,
                "Weight Util": weight_util,
                "Solid Product Volume m3": solid_product_volume,
                "Kiln m3": float(kiln["Gross m3"]),
                "Solid Volume Util": solid_volume_util,
                "Occupied Envelope m3": occupied_envelope_m3,
                "Geometric Occupancy Util": geometric_occupancy_util,
                "Primary Volume Target": settings.target_volume,
                "Volume Target Status": (
                    "ACHIEVED" if geometric_occupancy_util >= settings.target_volume
                    else "BELOW TARGET"
                ),
                "Avg Floor Area Util": average_floor_area_util,
                "Supported Area Util": supported_area_util,
                "Open Supported Area %": open_supported_area_pct,
                "Floors / Levels": len(floors),
                "Floor Count Check": (
                    "REVIEW - FEW FLOORS / LARGE HEIGHT REMAINS"
                    if kiln["Type"] == "VITRIFIED"
                    and len(floors) < settings.preferred_min_vitrified_floors
                    and max(usable_height-used_height,0) > usable_height*0.25
                    else "OK"
                ),
                "Used Height mm": used_height,
                "Remaining Height mm": max(usable_height-used_height,0),
                "Plate Usage": "; ".join(f"{k}:{v}" for k,v in plate_counts.items()),
                "I-block Usage": "; ".join(f"{k}:{v}" for k,v in iblock_counts.items()),
                "Furniture Feasibility": furniture_status,
                "Usable Height mm": usable_height, "Height Util": height_util,
                "Effective Util": effective_util, "Mixed-WO Floors": mixed_floors,
                "Mixed-WO Stacks": mixed_stacks, "Earliest Due": earliest_due,
                "Running Days": cycle,
                "Program Finish Date": complete,
                "Unload / Take-Out Date": complete,
                "Firing Complete": complete,
                "Risk": risk,
                "Upstream Expedite WOs": expedite,
                "Limiting Constraint": limiting_constraint,
                "Kiln Selection Note": (
                    "T14 selected only after rectangular volume + weight gate"
                    if kiln["Kiln"]=="T14"
                    else ""
                ),
                "Preferred Min Weight Status": preferred_min_status,
                "T14 Fit Status": t14_fit_status,
                "Readiness Basis": (
                    "READY NOW"
                    if all(orders.loc[x["Order Index"],"Readiness"]=="READY / FIRING PREPARATION" for x in detail_lines)
                    else "LEAD-TIME FEASIBLE BY LOAD DATE"
                ),
                "Operational Priority Reason": (
                    "Selected to maintain feasible firing workload; ready/lead-time-feasible WOs ranked before non-ready work, then due date and priority."
                ),
                "Release Gate": decision,
                "Release Reason": release_reason,
                "Alternative Combination Action": alternative_action,
                "Remaining Same-Program WOs": remaining_same["wo"],
                "Remaining Same-Program Qty": remaining_same["qty"],
                "Remaining Same-Program kg": round(remaining_same["kg"],2),
                "Decision": decision,
            })

            for line_no, x in enumerate(detail_lines, 1):
                o = orders.loc[x["Order Index"]]
                details.append({
                    "Load ID": load_id, "Load Date": day, "Kiln": kiln["Kiln"],
                    "Program": program, "Line": line_no, "Work Order": o["Work Order"],
                    "Customer": o["Customer"], "Specification": o["Specification"],
                    "Priority": o["Priority"], "Due Date": o["Due Date"],
                    "Order Qty": o["Order Qty"],
                    "Remaining Qty at Plan Start": o["Remaining Qty"],
                    "Remaining Before This Load": x["Remaining Before Load"],
                    "Planned Firing Qty": x["Qty"],
                    "Remaining After This Load": x["Remaining After Load"],
                    "kg/pc": o["Weight kg/pc"],
                    "Weight kg": round(x["Weight"], 2), "Geometry": o["Geometry"],
                    "Shape": o.get("Shape",""),
                    "Loading Family": o.get("Loading Family",""),
                    "Loading Orientation": o.get("Loading Orientation",""),
                    "Stack Allowed": o.get("Stack Allowed",True),
                    "Hollow Nesting Preferred": o.get("Hollow Nesting Preferred",False),
                    "Verified Ready for Firing Qty": o.get("Verified Ready for Firing Qty",None),
                    "Firing Ready Basis": o.get("Firing Ready Basis",""),
                    "Firing Ready Trace": o.get("Firing Ready Trace",""),
                    "D/Length mm": o["D"], "T/Width mm": o["T"], "H/Hole mm": o["H"],
                    "Floors Used": x["Floors"], "Packing Modes": x["Packing Modes"],
                    "Preparation Target": add_workdays(day, -settings.prep_lead, settings.working_days),
                    "Mixing Target": add_workdays(day, -settings.mix_lead, settings.working_days),
                    "Forming Target": add_workdays(day, -settings.form_lead, settings.working_days),
                    "Readiness": o["Readiness"], "Earliest Normal Firing": o["Earliest Normal Firing"],
                    "Expedite Required": "YES" if day < o["Earliest Normal Firing"] else "NO",
                    "Calculated Current Process": o.get("Calculated Current Process",""),
                    "Qty at Current Process / Ready Next": o.get("Qty at Current Process / Ready Next",None),
                    "Required Action": o.get("Required Action",""),
                    "Plan2026 Actual Trace": o.get("Plan2026 Actual Trace",""),
                    "Running Days": cycle,
                    "Program Finish Date": complete,
                    "Unload / Take-Out Date": complete,
                    "Firing Complete": complete,
                    "Risk": risk,
                    "Data Check": o["Data Check"],
                })

            # If release gate says HOLD, this candidate load is shown for review
            # but must NOT consume order demand or kiln availability.
            if str(decision).startswith("HOLD"):
                for x in detail_lines:
                    orders.at[x["Order Index"],"Qty To Plan"] += int(x["Qty"])
                # HOLD is a review result, not a kiln start. Do not consume kiln
                # availability or daily start count. Remember this exact
                # kiln/program/demand signature so the identical expensive
                # physical arrangement is not recalculated again. If another
                # load changes same-program demand, the signature changes and
                # this kiln is reconsidered automatically.
                STAGE4_HOLD_SIGNATURES.add((int(kiln_idx),txt(program),_stage4_program_signature(orders,program)))
                exceptions.append({
                    "Work Order": first["Work Order"],
                    "Program": program,
                    "Issue": release_reason,
                    "Recommended Action": alternative_action,
                })
                floor_rows.extend(fp.to_dict("records"))
            else:
                floor_rows.extend(fp.to_dict("records"))
                kilns.at[kiln_idx, "Next Available"] = complete
                if txt(kiln.get("Type","")).upper()=="VITRIFIED":
                    if txt(kiln.get("Kiln","")).upper() != "T0":
                        vitrified_starts += 1
                    vitrified_programs_started.add(program)
                else:
                    resin_starts += 1
                    resin_programs_started.add(program)

        day += timedelta(days=1)
        # FAST RELEASE MODE: for immediate daily release, stop after N planning days.
        # This does NOT change allocation logic within those days; it only avoids
        # calculating future loads that are not needed for today's release.
        max_days = getattr(settings, "max_planning_days", None)
        if max_days is not None and guard >= int(max_days):
            break

    return pd.DataFrame(loads), pd.DataFrame(details), pd.DataFrame(floor_rows), pd.DataFrame(exceptions), kilns



def floor_space_metrics(stack_plan, load_id, kiln):
    """
    Per-floor physical space indicators.

    Open-area % is an AIR-SPACE PROXY only; it is not a CFD airflow result.
    """
    x=stack_plan[stack_plan["Load ID"]==load_id].copy()
    if x.empty:
        return pd.DataFrame()

    rows=[]
    for fno in sorted(x["Floor"].unique()):
        f=x[x["Floor"]==fno].copy()
        first=f.iloc[0]

        # Count each physical stack footprint once.
        stacks=f.sort_values(["Stack ID","Stack Segment"]).groupby("Stack ID",as_index=False).first()
        occupied=sum(float(r["Footprint W mm"])*float(r["Footprint H mm"]) for _,r in stacks.iterrows())

        if txt(first.get("Plate",""))=="METAL FRAME":
            supported=max(
                (float(kiln["L mm"])-2*float(CURRENT_SETTINGS.edge_mm))
                *(float(kiln["W mm"])-2*float(CURRENT_SETTINGS.edge_mm)),1
            )
            clear_h=float(kiln.get("Level Clear Height mm",0) or 0)
        else:
            supported=max(
                num(first.get("Plate L mm",0))
                *num(first.get("Plate W mm",0))
                *num(first.get("Plates / Floor",0)),1
            )
            clear_h=num(first.get("I-block Height mm",0),0)

        used_pct=min(occupied/supported,1.0)
        open_pct=max(1-used_pct,0)
        max_stack=num(first.get("Floor Stack Zone Height mm",0),0)
        vertical_remaining=max(clear_h-max_stack,0)

        rows.append({
            "Floor":int(fno),
            "Plate":txt(first.get("Plate","")),
            "I-block":txt(first.get("I-block","")),
            "Supported Area mm²":supported,
            "Occupied Footprint mm²":occupied,
            "Remaining Supported Area mm²":max(supported-occupied,0),
            "Floor Area Util %":used_pct*100,
            "Open Area Proxy %":open_pct*100,
            "Tallest Stack mm":max_stack,
            "Clear Height mm":clear_h,
            "Remaining Vertical Clearance mm":vertical_remaining,
            "Stacks / Positions":int(stacks["Stack ID"].nunique()),
            "WO Count":int(f["Work Order"].nunique()),
            "Qty pcs":int(f["Qty"].sum()),
        })
    return pd.DataFrame(rows)


# -------------------------
# Visuals
# -------------------------

def floor_chart(stack_plan, load_id):
    x = stack_plan[stack_plan["Load ID"] == load_id]
    if x.empty:
        return go.Figure()

    q = x.groupby(["Floor", "Work Order"], as_index=False)["Qty"].sum()
    q["Floor Label"] = q["Floor"].apply(lambda f: f"Floor {int(f)}")
    order = [f"Floor {int(v)}" for v in sorted(q["Floor"].unique(), reverse=True)]
    fig = px.bar(
        q, x="Qty", y="Floor Label", color="Work Order", orientation="h",
        title=f"{load_id} — quantity by floor and work order",
        category_orders={"Floor Label": order}
    )
    totals = q.groupby("Floor Label", as_index=False)["Qty"].sum()
    fig.add_scatter(x=totals["Qty"], y=totals["Floor Label"], mode="text",
                    text=[f"{v:,.0f}" for v in totals["Qty"]],
                    textposition="middle right", showlegend=False, hoverinfo="skip")
    fig.update_layout(barmode="stack", height=max(420, 38 * q["Floor"].nunique()),
                      uniformtext_minsize=11, uniformtext_mode="show")
    return fig


def floor_top_view(stack_plan, load_id, floor_no, kiln):
    x = stack_plan[(stack_plan["Load ID"] == load_id) & (stack_plan["Floor"] == floor_no)].copy()
    fig = go.Figure()
    if x.empty:
        return fig

    first = x.iloc[0]

    # Draw refractory plates and shared support nodes before drawing products.
    if txt(first.get("Plate","")) and txt(first.get("Plate","")) != "METAL FRAME":
        pl = num(first.get("Plate L mm",0))
        pw = num(first.get("Plate W mm",0))
        cols = int(num(first.get("Plate Cols",0)))
        rows = int(num(first.get("Plate Rows",0)))
        edge = float(CURRENT_SETTINGS.edge_mm) if CURRENT_SETTINGS is not None else 25
        pgap = float(CURRENT_SETTINGS.plate_gap_mm) if CURRENT_SETTINGS is not None else 10

        for rr in range(rows):
            for cc in range(cols):
                x0 = edge + cc * (pl + pgap)
                y0 = edge + rr * (pw + pgap)
                fig.add_shape(
                    type="rect", x0=x0, x1=x0+pl, y0=y0, y1=y0+pw,
                    line=dict(width=1, dash="dot"),
                    fillcolor="rgba(180,180,180,0.05)"
                )

        # I-block/support positions at grid corner/junction points.
        sx = [edge + cc * (pl + pgap) for cc in range(cols+1)]
        sy = [edge + rr * (pw + pgap) for rr in range(rows+1)]
        xx=[]; yy=[]
        for xv in sx:
            for yv in sy:
                xx.append(xv); yy.append(yv)
        fig.add_trace(go.Scatter(
            x=xx, y=yy, mode="markers",
            marker=dict(symbol="square", size=8),
            name=f"I-block/support ({first.get('I-block','')})",
            hovertemplate="I-block/support position<extra></extra>"
        ))

    base_x=x[~x["Placement Mode"].astype(str).str.contains("NESTED IN",na=False)] if "Placement Mode" in x.columns else x
    placements = base_x.sort_values(["Stack ID", "Stack Segment"]).groupby("Stack ID", as_index=False).first()
    comp = x.groupby(["Stack ID", "Work Order"], as_index=False)["Qty"].sum()

    comp_map = {}
    for sid, g in comp.groupby("Stack ID"):
        comp_map[sid] = "<br>".join(
            f"{r['Work Order']}: {int(r['Qty'])} pcs" for _, r in g.iterrows()
        )

    for _, p in placements.iterrows():
        x0, y0 = float(p["x mm"]), float(p["y mm"])
        w, h = float(p["Footprint W mm"]), float(p["Footprint H mm"])
        typ = "circle" if p["Base Geometry"] == "CIRCULAR" else "rect"
        fig.add_shape(
            type=typ, x0=x0, x1=x0+w, y0=y0, y1=y0+h,
            line=dict(width=1.5), fillcolor="rgba(100,100,100,0.2)"
        )
        if p["Base Geometry"]=="CIRCULAR":
            hd=max(num(p.get("Hole Diameter mm",0)),0)
            if 0 < hd < w:
                cx=x0+w/2;cy=y0+h/2
                fig.add_shape(type="circle",x0=cx-hd/2,x1=cx+hd/2,y0=cy-hd/2,y1=cy+hd/2,
                              line=dict(width=1.4,dash="dot"),fillcolor="rgba(255,255,255,0.80)")
        fig.add_trace(go.Scatter(
            x=[x0+w/2], y=[y0+h/2], mode="markers",
            hovertemplate=(
                f"<b>{p['Stack ID']}</b><br>"
                f"Plate zone: {p.get('Plate Zone','')}<br>"
                f"{comp_map.get(p['Stack ID'],'')}<br>"
                f"Stack height {p['Stack Total Height mm']:.0f} mm<extra></extra>"
            ),
            showlegend=False
        ))

    if "Placement Mode" in x.columns:
        nested=x[x["Placement Mode"].astype(str).str.contains("NESTED IN",na=False)]
        for _,n in nested.iterrows():
            host=placements[placements["Stack ID"]==n["Stack ID"]]
            if host.empty:continue
            hp=host.iloc[0]
            cx=float(hp["x mm"])+float(hp["Footprint W mm"])/2
            cy=float(hp["y mm"])+float(hp["Footprint H mm"])/2
            ngeom=txt(n.get("Geometry","CIRCULAR")).upper()
            if ngeom=="RECTANGULAR":
                nw=max(num(n.get("D mm",0)),1)
                nh=max(num(n.get("H mm",0)),1)
                fig.add_shape(type="rect",x0=cx-nw/2,x1=cx+nw/2,y0=cy-nh/2,y1=cy+nh/2,
                              line=dict(width=1.5,dash="dash"),fillcolor="rgba(120,120,120,0.25)")
                _dim=f"L={nw:g} mm; W={nh:g} mm; T={num(n.get('T mm',0)):g} mm"
            else:
                nd=max(num(n.get("D mm",0)),1)
                fig.add_shape(type="circle",x0=cx-nd/2,x1=cx+nd/2,y0=cy-nd/2,y1=cy+nd/2,
                              line=dict(width=1.5,dash="dash"),fillcolor="rgba(120,120,120,0.25)")
                _dim=f"D={nd:g} mm; T={num(n.get('T mm',0)):g} mm"
            fig.add_trace(go.Scatter(x=[cx],y=[cy],mode="markers",showlegend=False,
                hovertemplate=f"<b>{n['Work Order']}</b><br>{ngeom} nested in circular host hole<br>{_dim}<extra></extra>"))

    fig.update_layout(
        title=f"{load_id} · Floor {floor_no} — D/T/H pattern (circular holes shown)",
        xaxis=dict(range=[0, float(kiln["L mm"])], title="Kiln length mm"),
        yaxis=dict(
            range=[0, float(kiln["W mm"])],
            title="Kiln width mm", scaleanchor="x", scaleratio=1
        ),
        height=650
    )
    return fig


def load_side_view(stack_plan, load_id, kiln):
    """
    Lightweight side elevation.
    One product envelope per floor; no per-stack labels.
    """
    x=stack_plan[stack_plan["Load ID"]==load_id]
    fig=go.Figure()
    if x.empty:
        return fig

    depth=float(kiln["W mm"]); kh=float(kiln["H mm"])
    fig.add_shape(type="rect",x0=0,x1=depth,y0=0,y1=kh,line=dict(width=2))

    ybase=0.0
    for fno in sorted(x["Floor"].unique()):
        f=x[x["Floor"]==fno]
        first=f.iloc[0]
        pitch=max(num(first.get("Floor Pitch mm",0)),1)
        plate_t=max(num(first.get("Plate T mm",0)),1)
        clear_h=max(num(first.get("I-block Height mm",0)),0)
        stack_h=max(num(first.get("Floor Stack Zone Height mm",0)),0)

        if txt(first.get("Plate",""))=="METAL FRAME":
            clear_h=max(float(kiln.get("Level Clear Height mm",0) or 0),stack_h)
            plate_t=float(CURRENT_SETTINGS.shelf_mm)
            pitch=clear_h+plate_t

        fig.add_shape(type="line",x0=0,x1=depth,y0=ybase,y1=ybase,line=dict(width=1))
        py=ybase+plate_t
        fig.add_shape(type="rect",x0=depth*0.15,x1=depth*0.85,
                      y0=py,y1=min(py+stack_h,kh),line=dict(width=1))
        ybase += pitch

    fig.update_layout(
        title=f"{load_id} — SIDE VIEW / มุมมองด้านข้าง",
        xaxis=dict(range=[0,depth],title="Depth mm",fixedrange=True),
        yaxis=dict(range=[0,kh],title="Height mm",fixedrange=True),
        height=380,showlegend=False,
        margin=dict(l=40,r=20,t=50,b=40)
    )
    return fig


def load_front_view(stack_plan, load_id, kiln):
    """
    Lightweight front elevation.
    Shows one occupied envelope per floor instead of every stack rectangle.
    """
    x=stack_plan[stack_plan["Load ID"]==load_id]
    fig=go.Figure()
    if x.empty:
        return fig

    width=float(kiln["L mm"]); kh=float(kiln["H mm"])
    fig.add_shape(type="rect",x0=0,x1=width,y0=0,y1=kh,line=dict(width=2))

    ybase=0.0
    for fno in sorted(x["Floor"].unique()):
        f=x[x["Floor"]==fno]
        first=f.iloc[0]
        pitch=max(num(first.get("Floor Pitch mm",0)),1)
        plate_t=max(num(first.get("Plate T mm",0)),1)

        if txt(first.get("Plate",""))=="METAL FRAME":
            pitch=max(float(kiln.get("Level Clear Height mm",0) or 1)+float(CURRENT_SETTINGS.shelf_mm),1)
            plate_t=float(CURRENT_SETTINGS.shelf_mm)

        stacks=f.sort_values(["Stack ID","Stack Segment"]).groupby("Stack ID",as_index=False).first()
        if not stacks.empty:
            xmin=max(float(stacks["x mm"].min()),0)
            xmax=min(float((stacks["x mm"]+stacks["Footprint W mm"]).max()),width)
            stack_h=float(stacks["Stack Total Height mm"].max())
            py=ybase+plate_t
            fig.add_shape(type="rect",x0=xmin,x1=xmax,y0=py,y1=min(py+stack_h,kh),line=dict(width=1))

        fig.add_shape(type="line",x0=0,x1=width,y0=ybase,y1=ybase,line=dict(width=1))
        ybase += pitch

    fig.update_layout(
        title=f"{load_id} — FRONT VIEW / มุมมองด้านหน้า",
        xaxis=dict(range=[0,width],title="Width mm",fixedrange=True),
        yaxis=dict(range=[0,kh],title="Height mm",fixedrange=True),
        height=380,showlegend=False,
        margin=dict(l=40,r=20,t=50,b=40)
    )
    return fig


def stack_vertical_chart(stack_plan, load_id, stack_id):
    x = stack_plan[(stack_plan["Load ID"] == load_id) & (stack_plan["Stack ID"] == stack_id)].sort_values("Stack Segment")
    fig = go.Figure()
    if x.empty:
        return fig

    for _, r in x.iterrows():
        fig.add_trace(go.Bar(
            x=[stack_id],
            y=[float(r["Segment Top mm"]) - float(r["Segment Bottom mm"])],
            base=[float(r["Segment Bottom mm"])],
            name=r["Work Order"],
            text=f"{r['Work Order']}<br>{int(r['Qty'])} pcs",
            textposition="inside"
        ))
    fig.update_layout(barmode="overlay", title=f"{load_id} · {stack_id} — bottom-to-top mixed stack",
                      yaxis_title="Stack height mm", height=520)
    return fig


def period_summary(loads, period):
    x = loads.copy()
    x["Load Date"] = pd.to_datetime(x["Load Date"])
    if period == "Daily":
        x["Period"] = x["Load Date"].dt.strftime("%d-%b-%Y")
        x["_sort"] = x["Load Date"]
    elif period == "Weekly":
        iso = x["Load Date"].dt.isocalendar()
        x["Period"] = iso["year"].astype(str) + "-W" + iso["week"].astype(str).str.zfill(2)
        x["_sort"] = x["Load Date"].dt.to_period("W").apply(lambda p:p.start_time)
    else:
        x["Period"] = x["Load Date"].dt.strftime("%b-%Y")
        x["_sort"] = x["Load Date"].dt.to_period("M").apply(lambda p:p.start_time)

    return x.groupby("Period", as_index=False).agg(
        Starts=("Load ID","count"), Pcs=("Qty pcs","sum"), Weight_kg=("Weight kg","sum"),
        Weight_Util=("Weight Util","mean"),
        Solid_Volume_Util=("Solid Volume Util","mean"),
        Geometric_Occupancy=("Geometric Occupancy Util","mean"),
        Floor_Area_Util=("Avg Floor Area Util","mean"),
        Height_Util=("Height Util","mean"),
        Effective_Util=("Effective Util","mean"),
        Mixed_Floors=("Mixed-WO Floors","sum"), Mixed_Stacks=("Mixed-WO Stacks","sum"),
        Late=("Risk",lambda s:int((s=="LATE").sum())),
        At_Risk=("Risk",lambda s:int((s=="AT RISK").sum())),
        Expedite=("Upstream Expedite WOs","sum"),
        _sort=("_sort","min")
    ).sort_values("_sort").drop(columns="_sort")



# -------------------------
# Planner release control / manual operational adjustment
# -------------------------
def _kiln_row(kiln_master, kiln_name):
    x=kiln_master[kiln_master["Kiln"].astype(str)==str(kiln_name)]
    return None if x.empty else x.iloc[0]


def _is_vitrified_kiln_name(k):
    return not txt(k).upper().startswith("R")


def _finish_for_manual_load(program, kiln, load_date):
    rule=program_rule(program,kiln)
    return load_date + timedelta(days=int(rule.get("cycle", rule.get("days", 0)))) if load_date and rule else None


def build_release_controls(loads, details):
    lc=loads[[
        c for c in [
            "Load ID","Load Date","Kiln","Program","Decision","Release Gate",
            "Geometric Occupancy Util","Weight Util","Risk","Floors / Levels"
        ] if c in loads.columns
    ]].copy()
    lc["Planner Status"]="RECOMMENDED"
    lc["Planner Remark"]=""
    lc["Original Kiln"]=lc["Kiln"]
    lc["Original Load Date"]=lc["Load Date"]

    wc=details[[
        c for c in [
            "Load ID","Work Order","Customer","Specification","Program","Priority",
            "Due Date","Planned Firing Qty","kg/pc","Readiness",
            "Earliest Normal Firing","Program Finish Date"
        ] if c in details.columns
    ]].copy()
    wc["Include in Released Load"]=True
    wc["Planner Remark"]=""
    return lc,wc


def apply_release_controls(loads, details, load_control, wo_control, kiln_master, settings):
    """
    Apply planner/production edits without destroying the recommendation.

    Manual kiln/date/quantity edits are allowed, but every released load is
    revalidated. If kiln changes, the original detailed floor pattern is NOT
    silently claimed to remain valid; projected occupancy is calculated and
    Pattern Recheck Required is shown.
    """
    lbase=loads.copy()
    dbase=details.copy()

    # Keep only included WO rows and apply editable quantity/priority.
    wc=wo_control.copy()
    wc["Planned Firing Qty"]=pd.to_numeric(wc["Planned Firing Qty"],errors="coerce").fillna(0).clip(lower=0)
    wc=wc[wc["Include in Released Load"].fillna(True)].copy()

    released=dbase.merge(
        wc[["Load ID","Work Order","Planned Firing Qty","Priority","Planner Remark"]],
        on=["Load ID","Work Order"],how="inner",suffixes=("_Auto","")
    )
    # Replace editable fields.
    if "Planned Firing Qty_Auto" in released.columns:
        released=released.drop(columns=["Planned Firing Qty_Auto"])
    if "Priority_Auto" in released.columns:
        released=released.drop(columns=["Priority_Auto"])
    released["Weight kg"]=released["Planned Firing Qty"]*pd.to_numeric(released["kg/pc"],errors="coerce").fillna(0)

    lc=load_control.copy()
    lc["Load Date"]=lc["Load Date"].apply(pdate)
    lc["Kiln"]=lc["Kiln"].apply(normalize_kiln_name)

    # Apply load-level edits to WO rows.
    released=released.drop(columns=[c for c in ["Load Date","Kiln"] if c in released.columns])
    released=released.merge(
        lc[["Load ID","Load Date","Kiln","Planner Status","Planner Remark","Original Kiln","Original Load Date"]],
        on="Load ID",how="left",suffixes=("","_Load")
    )
    if "Planner Remark_Load" in released.columns:
        released["Planner Remark"]=released["Planner Remark"].fillna("").astype(str)
        released.loc[
            released["Planner Remark"].eq(""),
            "Planner Remark"
        ]=released["Planner Remark_Load"].fillna("").astype(str)
        released=released.drop(columns=["Planner Remark_Load"])

    # Recalculate finish date after manual kiln/date changes.
    released["Program Finish Date"]=released.apply(
        lambda r:_finish_for_manual_load(r["Program"],r["Kiln"],r["Load Date"]),axis=1
    )
    released["Unload / Take-Out Date"]=released["Program Finish Date"]
    released["Firing Complete"]=released["Program Finish Date"]

    validations=[]
    release_loads=[]

    # Daily vitrified start count is a hard operational constraint.
    vit_counts=(
        lc[lc["Kiln"].apply(_is_vitrified_kiln_name)]
        .groupby("Load Date")["Load ID"].count().to_dict()
    )
    resin_counts=(
        lc[~lc["Kiln"].apply(_is_vitrified_kiln_name)]
        .groupby("Load Date")["Load ID"].count().to_dict()
    )

    # Build chronological kiln assignments to detect overlaps.
    kiln_sched={}
    for _,r in lc.sort_values("Load Date").iterrows():
        kiln_sched.setdefault(r["Kiln"],[]).append((r["Load ID"],r["Load Date"],r["Program"]))

    # Original gross occupancy envelope for projected occupancy if kiln changes.
    orig_by_id=lbase.set_index("Load ID").to_dict("index")

    for _,ctrl in lc.iterrows():
        lid=ctrl["Load ID"]
        x=released[released["Load ID"]==lid].copy()
        if x.empty:
            validations.append({
                "Load ID":lid,"Validation":"HOLD","Reason":"No WO quantity remains in released load.",
                "Recommended Action":"Add/restore WO quantity or cancel this load."
            })
            continue

        kiln=ctrl["Kiln"]; day=ctrl["Load Date"]; program=txt(x.iloc[0]["Program"])
        krow=_kiln_row(kiln_master,kiln)
        reasons=[]; warnings=[]

        if krow is None:
            reasons.append("Selected kiln not found in Kiln Availability master.")
        else:
            if not bool(krow.get("Use?",True)):
                reasons.append("Selected kiln is disabled.")
            status=txt(krow.get("Status","AVAILABLE")).upper()
            if status!="AVAILABLE":
                reasons.append(f"Selected kiln status is {status}.")
            av=pdate(krow.get("Available From"))
            if av and day and day<av:
                reasons.append(f"Kiln available from {av}, later than edited load date {day}.")

        # Program/kiln compatibility.
        if krow is not None:
            typ=txt(krow.get("Type",""))
            if program.startswith("KM") or program.startswith("BK"):
                if typ!="RESINOID": reasons.append("Resinoid program assigned to vitrified kiln.")
            else:
                if typ=="RESINOID": reasons.append("Vitrified program assigned to resin kiln.")

        # Maximum two vitrified starts/day.
        if _is_vitrified_kiln_name(kiln) and vit_counts.get(day,0)>2:
            reasons.append(f"{vit_counts.get(day)} vitrified starts on {day}; maximum is 2.")

        # Kiln overlap based on program running days.
        sched=kiln_sched.get(kiln,[])
        for j,(other_id,other_day,other_prog) in enumerate(sched):
            if other_id!=lid or other_day!=day:
                continue
            if j>0:
                prev_id,prev_day,prev_prog=sched[j-1]
                prev_finish=_finish_for_manual_load(prev_prog,kiln,prev_day)
                if prev_finish and day<prev_finish:
                    reasons.append(f"Kiln overlaps {prev_id}; previous cycle finishes {prev_finish}.")
            break

        # Readiness / lead-time feasibility for every WO.
        not_ready=[]
        for _,r in x.iterrows():
            if txt(r.get("Readiness",""))=="READY / FIRING PREPARATION":
                continue
            ef=pdate(r.get("Earliest Normal Firing"))
            if ef and day and day<ef:
                not_ready.append(f"{r['Work Order']} earliest {ef}")
        if not_ready:
            reasons.append("Upstream lead-time not feasible: "+", ".join(not_ready[:6]))

        qty=float(x["Planned Firing Qty"].sum())
        kg=float(x["Weight kg"].sum())

        # Weight capacity using the edited kiln/program.
        weight_util=0.0; maxkg=0.0; minkg=0.0
        if krow is not None:
            rule=program_rule(program,kiln)
            maxkg=min(float(krow.get("Physical kg",rule["maxkg"])),float(rule["maxkg"]))
            minkg=float(rule.get("minkg",0))
            if program=="P3" and kiln=="T14":
                maxkg=min(float(krow.get("Physical kg",4000)),4000)
                minkg=3800
            weight_util=kg/maxkg if maxkg else 0
            if maxkg and kg>maxkg+1e-6:
                reasons.append(f"Weight {kg:.0f} kg exceeds {maxkg:.0f} kg capacity.")

        # Project physical occupancy after kiln edit.
        orig=orig_by_id.get(lid,{})
        orig_kiln=txt(orig.get("Kiln",""))
        orig_occ=float(orig.get("Geometric Occupancy Util",0) or 0)
        projected_occ=orig_occ
        pattern_recheck="NO"
        if kiln!=orig_kiln and krow is not None:
            okrow=_kiln_row(kiln_master,orig_kiln)
            if okrow is not None:
                original_env=orig_occ*float(okrow.get("Gross m3",1) or 1)
                projected_occ=original_env/max(float(krow.get("Gross m3",1) or 1),1e-9)
            pattern_recheck="YES - KILN CHANGED"
            warnings.append("Kiln changed: detailed floor pattern must be operator/planner rechecked.")

        # Quantity edit also requires physical pattern review.
        auto_qty=float(dbase[dbase["Load ID"]==lid]["Planned Firing Qty"].sum())
        if abs(qty-auto_qty)>1e-6:
            pattern_recheck="YES - QTY CHANGED"
            warnings.append("WO quantity changed: detailed floor/stack pattern must be rechecked.")

        if projected_occ < settings.target_volume:
            warnings.append(
                f"Projected physical occupancy {projected_occ:.1%} is below target {settings.target_volume:.0%}."
            )
        if minkg>0 and kg<minkg:
            warnings.append(f"Weight {kg:.0f} kg is below preferred program minimum {minkg:.0f} kg.")

        # Customer delivery risk after manual date.
        due_dates=[pdate(v) for v in x["Due Date"]] if "Due Date" in x.columns else []
        due_dates=[v for v in due_dates if v]
        finish=_finish_for_manual_load(program,kiln,day)
        delivery_risk="OK"
        if due_dates and finish:
            earliest_due=min(due_dates)
            if finish>earliest_due: delivery_risk="LATE / AT RISK"

        validation="PASS" if not reasons else "HOLD"
        action=(
            "Release after pattern/operator verification." if validation=="PASS"
            else "Correct kiln/date/WO quantity or move load to another feasible slot."
        )

        validations.append({
            "Load ID":lid,"Load Date":day,"Kiln":kiln,"Program":program,
            "Released Qty":qty,"Released kg":kg,
            "Projected Volume Occupancy":projected_occ,
            "Weight Util":weight_util,
            "Pattern Recheck Required":pattern_recheck,
            "Delivery Risk":delivery_risk,
            "Validation":validation,
            "Hard Constraint Reason":" | ".join(reasons),
            "Warnings":" | ".join(warnings),
            "Recommended Action":action,
            "Planner Status":ctrl.get("Planner Status","RECOMMENDED"),
            "Planner Remark":ctrl.get("Planner Remark",""),
        })

        release_loads.append({
            "Load ID":lid,"Load Date":day,"Kiln":kiln,"Program":program,
            "Qty pcs":qty,"Weight kg":kg,
            "Projected Volume Occupancy":projected_occ,
            "Weight Util":weight_util,
            "Program Finish Date":finish,
            "Validation":validation,
            "Pattern Recheck Required":pattern_recheck,
            "Delivery Risk":delivery_risk,
            "Planner Status":ctrl.get("Planner Status","RECOMMENDED"),
            "Planner Remark":ctrl.get("Planner Remark",""),
        })

    return pd.DataFrame(release_loads), released, pd.DataFrame(validations)


def released_operator_print(released_details):
    op=released_details.copy()
    if op.empty:
        return op
    op["Firing Date"]=op["Load Date"]
    op["__LOAD_DATE_SORT__"]=pd.to_datetime(op["Load Date"],errors="coerce")
    op=op.sort_values(["__LOAD_DATE_SORT__"] + (["Kiln"] if "Kiln" in op.columns else []) + (["Load ID"] if "Load ID" in op.columns else []),kind="stable",na_position="last").drop(columns=["__LOAD_DATE_SORT__"]).reset_index(drop=True)
    op["Operator Instruction"]=(
        "Load "+op["Planned Firing Qty"].round(0).astype(int).astype(str)
        +" pcs in "+op["Kiln"].astype(str)
        +" / "+op["Program"].astype(str)
        +"; PROGRAM FINISH / TAKE-OUT: "+op["Program Finish Date"].astype(str)
        +". Follow verified same-program compact loading; operator may adjust physical position while preserving released WO/qty unless Planning approves a change."
    )
    preferred=[
        "Load ID","Firing Date","Load Date","Kiln","Program","Work Order","Customer","Specification",
        "Priority","Due Date","Planned Firing Qty","kg/pc","Weight kg","Readiness",
        "Earliest Normal Firing","Program Finish Date","Unload / Take-Out Date","Firing Complete",
        "Planner Status","Planner Remark","Operator Instruction"
    ]
    return op[[c for c in preferred if c in op.columns]]

def export_excel(prepared, kiln_editor, loads, details, floor_plan, exceptions, released_loads=None, released_details=None, release_validation=None):
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        prepared.drop(columns=["_due"], errors="ignore").to_excel(writer, index=False, sheet_name="Input Audit")
        kiln_editor.to_excel(writer, index=False, sheet_name="Kiln Availability")
        pd.DataFrame(PLATE_MASTER).to_excel(writer,index=False,sheet_name="Plate Furniture Master")
        pd.DataFrame(IBLOCK_MASTER).to_excel(writer,index=False,sheet_name="IBlock Furniture Master")
        loads.to_excel(writer, index=False, sheet_name="Auto Firing Plan")
        if released_loads is not None and not released_loads.empty:
            released_loads.to_excel(writer,index=False,sheet_name="Released Firing Plan")
        if release_validation is not None and not release_validation.empty:
            release_validation.to_excel(writer,index=False,sheet_name="Release Validation")
        if released_details is not None and not released_details.empty:
            released_operator_print(released_details).to_excel(writer,index=False,sheet_name="Released Operator Print")

        operator = details.copy()
        if not operator.empty:
            operator["__LOAD_DATE_SORT__"]=pd.to_datetime(operator.get("Load Date"),errors="coerce")
            operator=operator.sort_values(["__LOAD_DATE_SORT__"] + (["Kiln"] if "Kiln" in operator.columns else []) + (["Load ID"] if "Load ID" in operator.columns else []),kind="stable",na_position="last").drop(columns=["__LOAD_DATE_SORT__"]).reset_index(drop=True)
            operator["Operator Instruction"] = (
                "Load " + operator["Planned Firing Qty"].round(0).astype(int).astype(str)
                + " pcs in " + operator["Kiln"].astype(str)
                + " / " + operator["Program"].astype(str)
                + "; Floors: " + operator["Floors Used"].astype(str)
                + "; " + operator["Packing Modes"].astype(str)
                + "; PROGRAM FINISH / TAKE-OUT: "
                + operator["Program Finish Date"].astype(str)
                + ". Verify floor/stack pattern before loading and unload on the finish date."
            )
            preferred_cols = [
                "Load ID","Load Date","Kiln","Program","Work Order","Customer","Specification",
                "Priority","Due Date",
                "Order Qty","Remaining Qty at Plan Start","Remaining Before This Load",
                "Planned Firing Qty","Remaining After This Load",
                "kg/pc","Weight kg","Geometry","Shape","Loading Family","Loading Orientation","Stack Allowed","Hollow Nesting Preferred",
                "D/Length mm","T/Width mm","H/Hole mm",
                "Floors Used","Packing Modes",
                "Preparation Target","Mixing Target","Forming Target",
                "Readiness","Calculated Current Process","Qty at Current Process / Ready Next","Required Action","Plan2026 Actual Trace","Expedite Required",
                "Running Days","Program Finish Date","Unload / Take-Out Date",
                "Firing Complete","Risk",
                "Operator Instruction",
            ]
            preferred_cols = [c for c in preferred_cols if c in operator.columns]
            operator = operator[preferred_cols]
            _bi_op={
                "Load ID":"Load ID / รหัสโหลด","Load Date":"Loading Date / วันที่เข้าเตา","Kiln":"Kiln / เตา","Program":"Program / โปรแกรม",
                "Work Order":"Work Order / ใบสั่งผลิต","Customer":"Customer / ลูกค้า","Specification":"Specification / รายละเอียด",
                "Priority":"Priority / ลำดับความสำคัญ","Due Date":"Due Date / กำหนดส่ง","Planned Firing Qty":"Planned Qty / จำนวนแผน",
                "Readiness":"Readiness / ความพร้อม","Calculated Current Process":"Current Process / กระบวนการปัจจุบัน",
                "Required Action":"Required Action / การดำเนินการที่ต้องทำ","Program Finish Date":"Firing Finish / วันที่เผาเสร็จ",
                "Risk":"Risk / ความเสี่ยง","Operator Instruction":"Operator Instruction / คำแนะนำพนักงาน"}
            operator=operator.rename(columns={k:v for k,v in _bi_op.items() if k in operator.columns})
        operator.to_excel(writer, index=False, sheet_name="Operator Print")
        floor_plan.to_excel(writer, index=False, sheet_name="Floor Stack Plan")
        exceptions.to_excel(writer, index=False, sheet_name="Exceptions")
        pd.DataFrame([
            ["Furniture floor", "Vitrified parts are placed only on actual refractory plate zones, not on an unsupported whole-kiln rectangle."],
            ["I-block support", "I-blocks are modeled at shared plate corner/junction support nodes: (plate columns+1) × (plate rows+1)."],
            ["I-block height", "Choose the smallest enabled I-block whose height can clear the actual tallest stack on that floor plus vertical clearance."],
            ["Mixed floor", "Different same-program WOs may share unused positions on one floor and on the same plate zone when physically suitable."],
            ["Mixed stack", "Different same-program WOs may share one vertical stack when the upper footprint fits within the lower supporting footprint and stack height is available."],
            ["Packing priority", "Use existing stack height → unused floor footprint → new floor → new kiln load."],
            ["Capacity", "No 1,500 pcs rule. Furniture/geometry, usable height and weight determine quantity; raw solid volume is only a sanity indicator."],
            ["Volume KPI", "Solid Volume Util = abrasive/product solid volume ÷ gross kiln chamber. It may look low even for a visually full load."],
            ["Occupancy KPI", "Geometric Occupancy Util = occupied floor footprint × actual floor pitch ÷ gross kiln volume; use this for visual/fullness interpretation."],
            ["Limiting Constraint", "Management should see whether WEIGHT, GEOMETRIC OCCUPANCY or HEIGHT is controlling the load."],
            ["Priority", "STRICT: revised Due Date from Plan 2026 column E first. Blank due date is always last. Manual priority is only a secondary tie-breaker."],
            ["Previous processes", "Unfinished Preparation/Mixing/Forming remain plannable; firing date creates upstream target and expedite flag."],
            ["Kiln availability", "Use?/Status/Available From edited in the UI are authoritative."],
            ["P1/P2", "Preferred 1.2–1.8 t; running period 7 days."],
            ["P3", "Preferred 1.3–2.0 t; running period 6 days."],
            ["P3 on T14", "Preferred 3.8–4.0 t; running period 6 days."],
            ["P6", "Preferred 1.6–1.8 t; running period 5 days."],
            ["Resin R4/R5/R6", "Maximum 1.0 t; running period 3 days."],
            ["Kiln 4", "Prefer T4 for small vitrified parts when available and suitable, emphasizing volume utilization because running cost is high."],
            ["Program finish", "Operator Print shows Program Finish / Take-Out Date."],
            ["Verification", "Every floor and stack is visualized. Final operator verification is still mandatory."],
        ], columns=["Rule","Logic"]).to_excel(writer, index=False, sheet_name="Decision Logic")
    return bio.getvalue()


# -------------------------
# Input
# -------------------------



def auto_due_priority(due_value, planning_start):
    """Human-readable priority label derived from revised due date.
    Scheduling itself remains STRICT due-date-first.
    """
    d = pdate(due_value)
    if d is None:
        return "LAST"
    if planning_start is None:
        planning_start = date.today()
    days = (d - planning_start).days
    if days < 0:
        return "OVERDUE"
    if days <= 7:
        return "HIGH"
    if days <= 14:
        return "MEDIUM"
    return "LOW"

def _parse_plan2026_main_sheet(uploaded):
    """Read legacy Plan 2026 / PLAN_INPUT_ACTIVE directly without changing formulas.
    Source sheet: แผนการเผา. The old WIP sheet is ignored.
    Confirmed controls for this version:
      - Revised Due Date = column E (strict primary scheduling priority; blank dates sort last).
      - Overall WO closure = column LH (agreed master closure status).
      - Gross firing weight = AH grams/pc; net reference weight = AF grams/pc.
    Process transaction/actual columns remain supporting quantitative evidence.
    """
    import openpyxl
    from openpyxl.utils import column_index_from_string
    if hasattr(uploaded, "seek"):
        uploaded.seek(0)
    wb = openpyxl.load_workbook(uploaded, data_only=True, read_only=True, keep_links=False)
    if "แผนการเผา" not in wb.sheetnames:
        wb.close()
        raise ValueError("No Plan Input sheet and no legacy `แผนการเผา` sheet found.")
    ws = wb["แผนการเผา"]
    cols = {
        "Work Order":"A", "Due Date":"E", "Customer":"F", "Specification":"H",
        "Order Qty":"J", "Product Code":"K", "Product Type":"L",
        "D / Length mm":"M", "T / Width mm":"N", "H / Hole mm":"O",
        "Program":"BB", "Category":"BF", "Shape":"BW", "Net Weight g/pc":"AF", "Weight g/pc":"AH",
        "Preparation Actual Qty":"CX", "Preparation Status":"CY",
        "Mixing Actual Qty":"DG", "Mixing Status":"DH",
        "Forming Actual Qty":"DQ", "Forming Status":"DR",
        "Firing Actual Qty":"EA", "Firing Status":"EC",
        "Grinding Actual Qty":"EK", "Packing Actual Qty":"ET", "Packing Status":"KZ",
        "WO Closure Status":"FC",
    }
    idx = {k: column_index_from_string(v)-1 for k,v in cols.items()}
    max_col = max(idx.values())+1
    rows=[]
    for excel_row, values in enumerate(ws.iter_rows(min_row=4, max_col=max_col, values_only=True), start=4):
        def v(name):
            i=idx[name]
            return values[i] if i < len(values) else None
        wo=txt(v("Work Order"))
        if not wo:
            continue
        order_qty=num(v("Order Qty"),0)
        wt_g=num(v("Weight g/pc"),0); net_wt_g=num(v("Net Weight g/pc"),0)
        prep=num(v("Preparation Actual Qty"),0); mix=num(v("Mixing Actual Qty"),0)
        form=num(v("Forming Actual Qty"),0); fire=num(v("Firing Actual Qty"),0)
        # remaining demand for firing must not be more than order qty - fired qty.
        remaining=max(order_qty-fire,0)
        rows.append({
            "Work Order":wo,
            "Category":txt(v("Category")).upper(),
            "Customer":txt(v("Customer")),
            "Specification":txt(v("Specification")),
            "Product Type":txt(v("Product Type")),
            "Shape":txt(v("Shape")),
            "D / Length mm":v("D / Length mm"),
            "T / Width mm":v("T / Width mm"),
            "H / Hole mm":v("H / Hole mm"),
            "Order Qty":order_qty,
            "Remaining Qty":remaining,
            "Weight kg/pc":wt_g/1000 if wt_g>0 else 0,
            "Net Weight kg/pc":net_wt_g/1000 if net_wt_g>0 else 0,
            "Program":v("Program"),
            "Due Date":v("Due Date"),
            "Priority":auto_due_priority(v("Due Date"), CURRENT_SETTINGS.planning_start if CURRENT_SETTINGS is not None else date.today()),
            "Compatible?":"YES",
            "Notes":f"Imported from Plan 2026 row {excel_row}; gross weight AH converted g/pc to kg/pc; net weight AF retained for audit",
            "Order Status":v("WO Closure Status"),
            "Preparation Status":v("Preparation Status"),
            "Mixing Status":v("Mixing Status"),
            "Forming Status":v("Forming Status"),
            "Firing Status":v("Firing Status"),
            "Geometry Override":"",
            "Preparation Actual Qty":prep,
            "Mixing Actual Qty":mix,
            "Forming Actual Qty":form,
            "Firing Actual Qty":fire,
            "Grinding Actual Qty":num(v("Grinding Actual Qty"),0),
            "Packing Actual Qty":num(v("Packing Actual Qty"),0),
            "Product Code":txt(v("Product Code")),
        })
    wb.close()
    if not rows:
        raise ValueError("Legacy `แผนการเผา` was found, but no WO rows could be read.")
    return pd.DataFrame(rows), "แผนการเผา (legacy Plan 2026 main sheet)"

def read_orders(uploaded):
    xls = pd.ExcelFile(uploaded)

    # IMPORTANT DATA-SOURCE RULE:
    # The old WIP worksheet in Plan 2026 is intentionally excluded because it
    # is not maintained/current. Never use a sheet whose name is WIP (including
    # common Thai/English variants) as planning demand or readiness evidence.
    ignored_wip = [s for s in xls.sheet_names if "WIP" in str(s).upper()]
    # Direct Plan 2026 is preferred. Plan Input remains backward-compatible only.
    if "แผนการเผา" in xls.sheet_names:
        return _parse_plan2026_main_sheet(uploaded)
    sheet = next((s for s in ["Plan Input","Plan Input Corrected"] if s in xls.sheet_names), None)
    if sheet is None:
        raise ValueError("Upload Plan 2026 containing sheet `แผนการเผา`.")
    df = pd.read_excel(uploaded, sheet_name=sheet)
    if "Work Order" not in df.columns:
        df = pd.read_excel(uploaded, sheet_name=sheet, header=1)
    if "Work Order" not in df.columns:
        raise ValueError("Header `Work Order` not found.")
    return df, sheet


# ==========================================================
# Streamlit UI
# ==========================================================



def load_firing_capacity_master(path_or_file):
    import openpyxl
    wb=openpyxl.load_workbook(path_or_file,data_only=True,read_only=True,keep_links=False)
    if "Cap เตา" not in wb.sheetnames:
        wb.close(); raise ValueError("Capacity Database does not contain sheet `Cap เตา`.")
    ws=wb["Cap เตา"]
    loaded=[]
    for row in ws.iter_rows(min_row=2, values_only=True):
        prog=txt(row[0]) if len(row)>0 else ""
        ton=row[1] if len(row)>1 else None
        days=int(num(row[2],0)) if len(row)>2 else 0
        if not prog: continue
        key=prog.upper().strip()
        nums=[float(x) for x in re.findall(r"\d+(?:\.\d+)?", txt(ton))]
        if isinstance(ton,(int,float)):
            minkg,maxkg=0.0,float(ton)*1000
        elif len(nums)>=2:
            minkg,maxkg=nums[0]*1000,nums[1]*1000
        elif len(nums)==1:
            minkg,maxkg=0.0,nums[0]*1000
        else:
            minkg,maxkg=0.0,0.0
        if "T14" in key:
            # program_rule already contains a special T14 P3 branch; retain established logic there.
            loaded.append((key,minkg,maxkg,days))
            continue
        if key.startswith("P3"):
            key="P3"
        PROGRAM_RULES[key]={"cycle":days or PROGRAM_RULES.get(key,{}).get("cycle",1),"minkg":minkg,"maxkg":maxkg}
        loaded.append((key,minkg,maxkg,days))
    wb.close()
    return loaded
