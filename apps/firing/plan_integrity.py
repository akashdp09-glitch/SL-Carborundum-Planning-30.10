"""Plan integrity checker (added in RC29.50).
Checks a firing result BEFORE it is shown, so capacity errors are visible instead of silent.
Returns a DataFrame: Check | Status (PASS/WARN/FAIL) | Detail.  Never raises."""
import pandas as pd
from datetime import timedelta

def check_firing_result(fr, start, starts_per_day=2, target_volume=0.80, max_volume=0.95):
    rows = []
    def add(c, s, d): rows.append({"Check": c, "Status": s, "Detail": d})
    try:
        L = fr.get("loads") if isinstance(fr, dict) else None
        if L is None or len(L) == 0:
            add("Loads produced", "WARN", "No firing loads were produced for this plan.")
            return pd.DataFrame(rows)
        L = L.copy(); L["_d"] = pd.to_datetime(L["Load Date"], errors="coerce")
        first = L["_d"].min().date()
        n_on_start = int((L["_d"].dt.date == start).sum())
        ex = day1_explanation(fr, start)
        if n_on_start == 0:
            add("Firing on the selected start date", "WARN",
                f"No kiln load on {start}. {len(ex)} load(s) were moved later because upstream (Preparation/Mixing/Forming) cannot release product in time - see 'Day-1 explanation'. Kilns are idle that day unless already-formed WIP is loaded manually.")
        else:
            add("Firing on the selected start date", "PASS", f"{n_on_start} load(s) on {start}; {len(ex)} other load(s) were moved later by upstream limits.")
        add("Plan starts on selected date", "PASS" if first == start else "WARN",
            f"Selected {start}; first load {first}." + ("" if first == start else
            " Later start is only acceptable for a physical reason (kiln busy, cycle, material not ready) - see Release Reason."))
        if "Weight kg" in L and "Weight Limit kg" in L:
            n = int((pd.to_numeric(L["Weight kg"], errors="coerce") > pd.to_numeric(L["Weight Limit kg"], errors="coerce") * 1.0001).sum())
            add("Overcapacity - weight", "FAIL" if n else "PASS", f"{n} load(s) exceed the kiln weight limit.")
        if "Geometric Occupancy Util" in L:
            o = pd.to_numeric(L["Geometric Occupancy Util"], errors="coerce")
            n = int((o > max_volume + 1e-6).sum())
            add("Overcapacity - volume", "FAIL" if n else "PASS", f"{n} load(s) above {max_volume:.0%} occupancy.")
            u = int((o < target_volume - 1e-6).sum())
            add("Undercapacity - volume", "WARN" if u else "PASS",
                f"{u} of {len(L)} load(s) below the {target_volume:.0%} target (average {o.mean():.0%}). Review before issuing.")
        if "Weight Util" in L:
            w = pd.to_numeric(L["Weight Util"], errors="coerce")
            add("Undercapacity - weight", "WARN" if (w < 0.5).any() else "PASS",
                f"{int((w < 0.5).sum())} load(s) under 50% of weight limit (lowest {w.min():.0%}).")
        # kiln overlap: same kiln loaded again before previous cycle finished
        bad = 0
        if "Kiln" in L and "Firing Complete" in L:
            L["_f"] = pd.to_datetime(L["Firing Complete"], errors="coerce")
            for _, g in L.sort_values("_d").groupby("Kiln"):
                prev = None
                for _, r in g.iterrows():
                    if prev is not None and pd.notna(prev) and r["_d"] < prev: bad += 1
                    prev = r["_f"]
        add("Kiln double-booking", "FAIL" if bad else "PASS", f"{bad} overlapping load(s) on the same kiln.")
        if "Kiln" in L:
            nv = L[~L["Kiln"].astype(str).str.upper().isin(["T0", "R4", "R5", "R6"])]
            m = int(nv.groupby("_d").size().max()) if len(nv) else 0
            add("Vitrified starts per day", "FAIL" if m > starts_per_day else "PASS", f"Maximum {m} normal vitrified starts in one day (limit {starts_per_day}).")
        if "Risk" in L:
            late = int((L["Risk"].astype(str) == "LATE").sum())
            add("Due-date risk", "WARN" if late else "PASS", f"{late} load(s) finish after the earliest due date - capacity or upstream readiness is short.")
    except Exception as e:
        add("Integrity checker", "WARN", f"Could not complete: {e}")
    return pd.DataFrame(rows)


def day1_explanation(fr, start):
    """Why is (or is not) the selected start date used?  Lists every load that was originally proposed
    on the start date (or earlier) but moved later, with the reason recorded by the planner.
    Never raises; returns a DataFrame."""
    cols = ["Load ID", "Kiln", "Originally proposed", "Final load date", "Work orders in load", "Reason recorded by planner"]
    try:
        L = fr.get("loads"); D = fr.get("details")
        if L is None or len(L) == 0 or "Original Proposed Load Date" not in L.columns:
            return pd.DataFrame(columns=cols)
        L = L.copy()
        L["_o"] = pd.to_datetime(L["Original Proposed Load Date"], errors="coerce").dt.date
        L["_f"] = pd.to_datetime(L["Load Date"], errors="coerce").dt.date
        m = L[(L["_o"].notna()) & (L["_o"] <= start) & (L["_f"] > start)]
        rows = []
        for _, r in m.iterrows():
            wos = ""
            if D is not None and len(D) and "Load ID" in D.columns and "Work Order" in D.columns:
                w = D[D["Load ID"].astype(str) == str(r.get("Load ID"))]["Work Order"].astype(str).unique().tolist()
                wos = ", ".join(w[:6]) + (" ..." if len(w) > 6 else "")
            rows.append({"Load ID": r.get("Load ID"), "Kiln": r.get("Kiln"), "Originally proposed": r["_o"],
                         "Final load date": r["_f"], "Work orders in load": wos,
                         "Reason recorded by planner": r.get("Capacity Date Validation", "")})
        return pd.DataFrame(rows, columns=cols)
    except Exception as e:
        return pd.DataFrame([{"Load ID": "", "Kiln": "", "Originally proposed": "", "Final load date": "",
                              "Work orders in load": "", "Reason recorded by planner": f"Could not analyse: {e}"}])
