from __future__ import annotations
import math
from datetime import date, timedelta
import pandas as pd
import firing_engine_desktop_v2 as fire


def _num(v, default=0.0):
    try:
        x=float(v)
        return default if math.isnan(x) else x
    except Exception:
        return default


def _txt(v):
    return "" if v is None else str(v).strip()


def _workday(d, working_days):
    x=d
    while x.weekday() not in working_days:
        x += timedelta(days=1)
    return x



def _exact_reconcile_selected(selected, orders, kiln, maxkg, settings, refill_pool=None):
    """Run exact furniture packing and then refill any capacity released by trimming.

    The refill step is important for pull planning: the fast screen can request a
    quantity that the exact furniture model trims. Previously the unused physical
    space was simply lost until the next day, even when another compatible WO was
    available. The exact packer now pulls the next same-program demand into that
    freed capacity, preserving due-date order.
    """
    if not selected:
        return [], {"floors":0,"height":0.0,"plate_usage":"","iblock_usage":"","used_weight":0.0,"refill_qty":0}

    original_pos={oi:i for i,(oi,_,_) in enumerate(selected)}
    requested={oi:int(q) for oi,q,_ in selected}
    reason={oi:r for oi,_,r in selected}

    # Host-hole physical sequence only; due-date selection itself is unchanged.
    phys_order=sorted(
        [oi for oi,_,_ in selected],
        key=lambda oi:(-float(fire.nesting_host_score(orders.loc[oi])), original_pos[oi])
    )

    floors=[]
    used_weight=0.0
    packed={}
    for oi in phys_order:
        o=orders.loc[oi].copy()
        rq=requested[oi]
        kgpc=max(_num(o.get("Weight kg/pc")),0.0)
        if rq<=0 or kgpc<=0:
            packed[oi]=0
            continue
        weight_cap=max(int(math.floor(max(maxkg-used_weight,0.0)/kgpc)),0)
        if weight_cap<=0:
            packed[oi]=0
            continue
        pq,_=fire.pack_order(floors,o,rq,weight_cap,rq,kiln,settings)
        packed[oi]=int(pq)
        used_weight += int(pq)*kgpc

    reconciled=[]
    for oi,q,_ in selected:
        pq=int(packed.get(oi,0))
        if pq<=0:
            continue
        note=reason.get(oi,"")
        note += " | EXACT PHYSICAL/FURNITURE PASS"
        if pq<int(q):
            note += f" / TRIMMED {int(q)}->{pq}"
        reconciled.append((oi,pq,note.strip(" |")))

    # PULL REFILL: exact packing may have freed space. Use the same downstream
    # firing capacity to pull additional compatible same-program demand instead
    # of accepting an avoidably small load. Only demand not already selected is
    # eligible; due date remains the first sort key.
    refill_qty=0
    if refill_pool is not None and len(floors)>0 and used_weight < maxkg-1e-9:
        selected_ids={oi for oi,_,_ in selected}
        pool=refill_pool.copy()
        # A trimmed selected WO may still have unplanned balance. It is eligible
        # for refill before moving to another WO; this prevents an exact-pack trim
        # from creating an artificial small load.
        pool["_pull_rem"] = pd.to_numeric(pool.get("Qty To Plan",0),errors="coerce").fillna(0).clip(lower=0)
        for _oi,_q,_ in selected:
            if _oi in pool.index:
                pool.at[_oi,"_pull_rem"] = max(float(pool.at[_oi,"_pull_rem"]) - float(packed.get(_oi,0)), 0.0)
        pool=pool[pool["_pull_rem"]>0].copy()
        if not pool.empty:
            if "_due2" in pool.columns:
                pool=pool.sort_values(["_due2","Priority Rank","Source Row"],na_position="last",kind="stable")
            else:
                pool=pool.sort_values(["Due Date","Priority Rank","Source Row"],na_position="last",kind="stable")
            for oi,o in pool.iterrows():
                rem=max(int(_num(o.get("_pull_rem", o.get("Qty To Plan")))),0)
                kgpc=max(_num(o.get("Weight kg/pc")),0.0)
                if rem<=0 or kgpc<=0:
                    continue
                weight_cap=max(int(math.floor(max(maxkg-used_weight,0.0)/kgpc)),0)
                if weight_cap<=0:
                    break
                # Keep the refill bounded by remaining weight and the exact furniture model.
                pq,_=fire.pack_order(floors,o,rem,weight_cap,weight_cap,kiln,settings)
                pq=int(pq)
                if pq<=0:
                    continue
                used_weight += pq*kgpc
                refill_qty += pq
                reconciled.append((oi,pq,"PULL REFILL | EXACT PHYSICAL/FURNITURE PASS"))
                if used_weight >= maxkg-1e-9:
                    break


    try:
        height=float(fire.total_height(floors,kiln,settings) if floors else 0.0)
    except Exception:
        height=0.0
    try:
        pu=", ".join(f"{k}:{v}" for k,v in fire.plate_usage(floors).items())
    except Exception:
        pu=""
    try:
        iu=", ".join(f"{k}:{v}" for k,v in fire.iblock_usage(floors,settings).items() if k!="__NO_IBLOCK__")
    except Exception:
        iu=""

    return reconciled, {
        "floors":len(floors),"height":height,
        "plate_usage":pu,"iblock_usage":iu,"used_weight":used_weight,
        "refill_qty":refill_qty
    }


def _quick_fit(order, kiln, settings):
    """Conservative footprint + furniture support screen; no combinatorial packing."""
    fx=max(_num(order.get("Footprint X"),0),0)
    fy=max(_num(order.get("Footprint Y"),0),0)
    if fx<=0 or fy<=0:
        return False, "DIMENSION MISSING"
    L=max(_num(kiln.get("L mm"),0)-2*_num(settings.edge_mm,0),1)
    W=max(_num(kiln.get("W mm"),0)-2*_num(settings.edge_mm,0),1)
    if not ((fx<=L and fy<=W) or (fy<=L and fx<=W)):
        return False, "FOOTPRINT > USABLE KILN"
    if _txt(kiln.get("Type")).upper()=="VITRIFIED":
        try:
            layout=fire.choose_plate_layout(kiln,order,[],settings)
            if layout is None:
                return False, "NO VERIFIED REFRACTORY FLOOR SUPPORT"
        except Exception:
            return False, "FURNITURE SCREEN ERROR"
    else:
        ph=max(_num(order.get("Piece Height"),0),1)
        clear=max(_num(kiln.get("Level Clear Height mm"),0),1)
        if ph>clear:
            return False, "PART HEIGHT > RESIN LEVEL CLEARANCE"
    return True, "PASS"


def _env_per_piece(order, settings):
    fx=max(_num(order.get("Footprint X"),0),1)
    fy=max(_num(order.get("Footprint Y"),0),1)
    ph=max(_num(order.get("Piece Height"),0),1)
    if not bool(order.get("Stack Allowed",True)):
        stack=1
    else:
        max_h=max(_num(getattr(settings,"max_stack_height_mm",170),170),ph)
        stack=max(1,min(int(max_h//ph),int(getattr(settings,"max_direct_stack_pieces",999))))
    # Per-piece occupied envelope for a physical vertical stack:
    # product thickness remains for every piece; one vertical clearance is
    # amortized across the stack.
    eff_h=ph + _num(getattr(settings,"vertical_clearance_mm",0),0)/stack
    return fx*fy*eff_h/1e9


def _signature(orders, program):
    x=orders[(orders["Program"]==program)&(orders["Qty To Plan"]>0)]
    if x.empty: return (0,0.0,0)
    q=pd.to_numeric(x["Qty To Plan"],errors="coerce").fillna(0)
    w=pd.to_numeric(x["Weight kg/pc"],errors="coerce").fillna(0)
    return (int(q.sum()),round(float((q*w).sum()),1),len(x))


def build_plan_fast(prepared, kilns, settings):
    """
    V1.8 FAST Stage-4 allocator.

    Keeps the planning controls (WIP, due-date priority, program compatibility,
    kiln calendar/availability, weight limit, occupancy target, T14 gate and
    daily start limit) but replaces exhaustive piece-by-piece furniture search
    with a deterministic physical screen + envelope allocator. Detailed 3-view
    pattern generation is intentionally not run across the whole 30-day queue.
    """
    if prepared is None or prepared.empty:
        return pd.DataFrame(),pd.DataFrame(),pd.DataFrame(),pd.DataFrame(),kilns

    # Factory rule: T0 is the existing small auxiliary vitrified kiln, normally urgent/test work.
    # It does not consume the three normal vitrified loading slots. R4/R5/R6 are separate resin resources.
    # Every kiln still obeys its own firing cycle and next-working-day reload buffer.
    kilns = kilns.copy()

    # F7 POSITIVE CORE: build the best daily firing plan from ALL open demand; upstream sections PUSH parts to this firing rhythm.
    # Current readiness is a production signal, not a reason to omit the load: missing pcs become Preparation/Mixing/Forming PUSH requirements.
    orders=prepared[prepared["Include"].fillna(False)].copy().reset_index(drop=True)
    orders["Qty To Plan"]=pd.to_numeric(orders.get("Effective Qty",0),errors="coerce").fillna(0).clip(lower=0)
    orders["Ready Remaining"]=pd.to_numeric(orders.get("Verified Ready for Firing Qty",0),errors="coerce").fillna(0).clip(lower=0)
    orders["_envpc"]=orders.apply(lambda r:_env_per_piece(r,settings),axis=1)
    orders["_due2"]=orders.get("_due",pd.Series([date(2099,12,31)]*len(orders)))

    loads=[]; details=[]; exceptions=[]
    day=settings.planning_start  # USER-SELECTED START DATE IS ALWAYS DAY 1 (even Sunday/holiday)
    # Plan through the complete open-demand due-date horizon. 30 days is only a minimum view, not a planning stop.
    _dues=pd.to_datetime(orders.get("Due Date"),errors="coerce").dropna()
    _due_days=max((max(_dues).date()-day).days+45,30) if len(_dues) else 90
    max_days=min(max(int(getattr(settings,"max_planning_days",30) or 30),_due_days),730)
    load_no=0

    for horizon_idx in range(max_days):
        if day.weekday() not in settings.working_days and day!=settings.planning_start:
            day += timedelta(days=1); continue
        normal_vitrified_starts=0
        t0_starts=0
        resin_started=set()
        programs_started=set()
        daily_hold_signatures=set()
        attempts=0
        # Continue until there is no feasible demand or all independent daily resources are exhausted.
        while attempts<30:
            attempts += 1
            cand=orders[orders["Qty To Plan"]>0].copy()
            if cand.empty: break
            cand["_readyrank"]=cand["Readiness"].map(lambda x:0 if x=="READY / FIRING PREPARATION" else 1)
            # Due-date protection first. ReleaseCandidate already applies the physical/readiness gate,
            # so an overdue executable WO must never be pushed behind a future-due WO by a label.
            # DUE DATE FIRST is non-negotiable. The scan continues down this ordered
            # queue only when earlier-due executable work cannot consume another feasible
            # daily resource slot. Therefore farther-due/lower-priority work acts only as
            # BALANCE-PULL work to prevent avoidable under-utilization.
            cand=cand.sort_values(["_due2","Priority Rank","_readyrank","Earliest Normal Firing","Source Row"],na_position="last",kind="stable")
            first_idx=None; kiln_idx=None
            # Bounded due-date scan: normally the earliest 120 candidates are enough;
            # if no kiln is feasible, the remaining queue is checked once before the day is left idle.
            _scan=cand.head(120)
            for oi,o in _scan.iterrows():
                program=o["Program"]
                sig=_signature(orders,program)
                if (program,sig) in daily_hold_signatures:
                    continue
                try:
                    ki=fire.choose_kiln(kilns,program,day,o,settings,orders)
                except Exception:
                    ki=None
                if ki is None: continue

                kname=_txt(kilns.loc[ki].get("Kiln","")).upper()
                ktype=_txt(kilns.loc[ki].get("Type","")).upper()

                # T1-T12/T14: manpower capacity = max two normal vitrified starts/day.
                if ktype=="VITRIFIED" and kname!="T0" and normal_vitrified_starts>=int(getattr(settings,"vitrified_starts_per_day",2)):
                    # The three normal slots are full. T0 remains an independent small auxiliary kiln.
                    try:
                        _t0=[j for j in fire.candidate_kilns(kilns,program,day) if _txt(kilns.loc[j].get("Kiln","")).upper()=="T0"]
                    except Exception:
                        _t0=[]
                    if _t0:
                        ki=_t0[0]; kname="T0"; ktype="VITRIFIED"
                    else:
                        continue

                # If T0 was preferred but already used today, do not lose the WO.
                if kname=="T0" and t0_starts>=1:
                    if normal_vitrified_starts<int(getattr(settings,"vitrified_starts_per_day",2)):
                        try:
                            _normal=[j for j in fire.candidate_kilns(kilns,program,day)
                                     if _txt(kilns.loc[j].get("Type","")).upper()=="VITRIFIED"
                                     and _txt(kilns.loc[j].get("Kiln","")).upper()!="T0"]
                        except Exception:
                            _normal=[]
                        if _normal:
                            ki=_normal[0]; kname=_txt(kilns.loc[ki].get("Kiln","")).upper(); ktype="VITRIFIED"
                        else:
                            continue
                    else:
                        continue

                # R4/R5/R6 are independent resin kiln resources.
                if ktype=="RESINOID" and kname in resin_started:
                    continue

                # Same-program second load is allowed when it is the feasible way to protect due date and use capacity.
                first_idx=oi; kiln_idx=ki; break
            if first_idx is None and len(cand) > len(_scan):
                for oi,o in cand.iloc[len(_scan):].iterrows():
                    program=o["Program"]
                    sig=_signature(orders,program)
                    if (program,sig) in daily_hold_signatures:
                        continue
                    try:
                        ki=fire.choose_kiln(kilns,program,day,o,settings,orders)
                    except Exception:
                        ki=None
                    if ki is None:
                        continue
                    kname=_txt(kilns.loc[ki].get("Kiln","")).upper()
                    ktype=_txt(kilns.loc[ki].get("Type","")).upper()
                    if ktype=="VITRIFIED" and kname!="T0" and normal_vitrified_starts>=int(getattr(settings,"vitrified_starts_per_day",2)):
                        continue
                    if ktype=="RESINOID" and kname in resin_started:
                        continue
                    first_idx=oi; kiln_idx=ki; break
            if first_idx is None: break

            first=orders.loc[first_idx]
            kiln=kilns.loc[kiln_idx]
            program=first["Program"]
            rule=fire.program_rule(program,kiln["Kiln"])
            maxkg=min(_num(kiln["Physical kg"]),_num(rule.get("maxkg"),1800))
            minkg=_num(rule.get("minkg"),0)
            if program=="P3" and kiln["Kiln"]=="T14":
                maxkg=min(_num(kiln["Physical kg"]),4000); minkg=3800
            maxenv=max(_num(kiln["Gross m3"])*float(settings.max_volume),1e-9)
            targetenv=max(_num(kiln["Gross m3"])*float(settings.target_volume),1e-9)

            same=orders[(orders["Qty To Plan"]>0)&(orders["Program"]==program)].copy()
            same=same.sort_values(["_due2","Priority Rank","Source Row"],na_position="last",kind="stable")
            # Performance guard: do not run the expensive furniture screen over
            # hundreds/thousands of same-program WOs. Due-date order is preserved;
            # the window is widened only if the first window cannot approach the
            # kiln target. This is a calculation-time optimization, not a rule change.
            _cand_limit = max(int(getattr(settings, "stage4_candidate_limit", 80) or 80), 160)
            if len(same) > _cand_limit:
                _probe = same.head(_cand_limit)
                _probe_env = float((_probe["Qty To Plan"] * _probe["_envpc"]).sum())
                _probe_kg = float((_probe["Qty To Plan"] * _probe["Weight kg/pc"]).sum())
                if _probe_env < targetenv * 0.90 or _probe_kg < maxkg * 0.90:
                    same = same.head(min(len(same), _cand_limit * 3))
                else:
                    same = _probe
            selected=[]; totalkg=0.0; totalenv=0.0; totalqty=0
            fit_fail=0
            for oi,o in same.iterrows():
                ok,fit_reason=_quick_fit(o,kiln,settings)
                if not ok:
                    fit_fail += 1
                    continue
                rem=max(int(_num(o["Qty To Plan"])),0)
                if rem<=0: continue
                kgpc=max(_num(o["Weight kg/pc"]),0)
                envpc=max(_num(o["_envpc"]),1e-12)
                qkg=rem if kgpc<=0 else int(max(maxkg-totalkg,0)//kgpc)
                qenv=int(max(maxenv-totalenv,0)//envpc)
                q=min(rem,qkg,qenv)
                if q<=0: continue
                selected.append((oi,q,fit_reason))
                totalqty += q; totalkg += q*kgpc; totalenv += q*envpc
                if totalkg >= maxkg*0.995 or totalenv >= maxenv*0.995:
                    break

            if not selected:
                daily_hold_signatures.add((program,_signature(orders,program)))
                exceptions.append({"Work Order":first["Work Order"],"Program":program,"Issue":"No compatible quantity passed fast physical/furniture screen","Recommended Action":"Check dimensions, furniture master, program and kiln availability"})
                continue

            # V1.9.17 exact release gate. The candidate quantity must be reproducible
            # by the same detailed physical/furniture packer used for the A4 pattern.
            # Exact packing is the physical authority. Pass the complete bounded
            # same-program look-ahead so any space lost by furniture trimming can be
            # immediately refilled from the next compatible demand.
            selected, exact_ev = _exact_reconcile_selected(
                selected, orders, kiln, maxkg, settings, refill_pool=same
            )
            if not selected:
                daily_hold_signatures.add((program,_signature(orders,program)))
                exceptions.append({
                    "Work Order":first["Work Order"],"Program":program,
                    "Issue":"Candidate failed exact physical/furniture reconciliation",
                    "Recommended Action":"Check actual loading orientation, dimensions, center hole, support arrangement and furniture master"
                })
                continue

            totalqty=sum(int(q) for _,q,_ in selected)
            totalkg=sum(int(q)*max(_num(orders.loc[oi].get("Weight kg/pc")),0) for oi,q,_ in selected)
            totalenv=sum(int(q)*max(_num(orders.loc[oi].get("_envpc")),1e-12) for oi,q,_ in selected)

            occ=totalenv/max(_num(kiln["Gross m3"]),1e-9)
            wutil=totalkg/max(maxkg,1)
            cycle=int(_num(rule.get("cycle"),7))
            complete=day+timedelta(days=cycle)
            dues=[orders.loc[oi,"Due Date"] for oi,q,_ in selected if orders.loc[oi,"Due Date"] is not None]
            earliest=min(dues) if dues else None
            risk="DUE DATE MISSING" if earliest is None else ("LATE" if complete>earliest else ("AT RISK" if complete>=earliest-timedelta(days=settings.risk_days) else "ON TRACK"))
            remaining_prog=int(sum(max(int(_num(orders.loc[oi,"Qty To Plan"]))-q,0) for oi,q,_ in selected))
            # include untouched same-program demand
            selected_ids={oi for oi,_,_ in selected}
            remaining_prog += int(pd.to_numeric(same.loc[~same.index.isin(selected_ids),"Qty To Plan"],errors="coerce").fillna(0).sum())

            # Readiness is evaluated AFTER the future kiln load has been physically planned.
            _ready_for_load=0
            for _oi,_q,_ in selected:
                _ready_for_load += min(int(_q), max(int(_num(orders.loc[_oi].get("Ready Remaining",0))),0))
            _make_for_load=max(int(totalqty)-int(_ready_for_load),0)
            _physical_target_ok=(occ>=float(settings.target_volume) or wutil>=0.98 or _txt(kiln.get("Type")).upper()=="RESINOID")
            if _physical_target_ok and _make_for_load<=0:
                decision="RELEASE - RESIN KILN" if _txt(kiln.get("Type")).upper()=="RESINOID" else "RELEASE"
                reason=("Current formed/readiness quantity covers the complete physically planned load; "
                        f"occupancy {occ:.1%}, weight {wutil:.1%}.")
            elif _physical_target_ok:
                decision="FUTURE PLANNED - MAKE PARTS"
                reason=(f"Daily kiln slot reserved from open due-date demand. Planned {totalqty} pcs; "
                        f"ready now {_ready_for_load} pcs; MAKE {_make_for_load} pcs upstream before firing. "
                        f"Expected occupancy {occ:.1%}.")
            else:
                decision="FUTURE PLANNED - BELOW TARGET / COMBINE"
                reason=(f"Daily firing opportunity retained, but occupancy {occ:.1%} is below "
                        f"{float(settings.target_volume):.0%}. Planned {totalqty} pcs; ready {_ready_for_load} pcs; "
                        f"MAKE {_make_for_load} pcs for these WOs and combine next compatible due-date demand if available.")

            # T14 additional protection.
            if kiln["Kiln"]=="T14" and (occ<float(settings.target_volume) or (minkg>0 and totalkg<minkg)) and not (risk in {"LATE","AT RISK"} and bool(settings.allow_urgent_partial)):
                decision="FUTURE PLANNED - T14 UNDERFILLED / MOVE OR COMBINE"; reason=f"T14 under-filled: occupancy {occ:.1%}, weight {totalkg:.0f} kg"

            load_no += 1
            lid=f"LOAD-{load_no:03d}"
            def _is_test_order(_oi):
                _pc=str(orders.loc[_oi].get("Product Code","") or "").strip()
                _ov=str(orders.loc[_oi].get("Test Work Override","AUTO") or "AUTO").upper()
                return (True if _ov=="TEST" else (False if _ov=="NORMAL" else _pc[:1]=="1"))
            _test_qty=sum(int(q) for oi,q,_ in selected if _is_test_order(oi))
            _test_wos=[str(orders.loc[oi].get("Work Order","")) for oi,q,_ in selected if _is_test_order(oi)]
            loadrow={
                "Load ID":lid,"Load Date":day,"Kiln":kiln["Kiln"],"Program":program,"Furniture":kiln.get("Furniture",""),
                "Test Work pcs":_test_qty,"Test Work WOs":", ".join(_test_wos),"Contains Test Work":("YES / มีงานทดสอบ" if _test_qty>0 else "NO / ไม่มีงานทดสอบ"),
                "WO Lines":len(selected),"Qty pcs":totalqty,"Weight kg":round(totalkg,2),"Program Preferred Min kg":minkg,
                "Weight Limit kg":maxkg,"Weight Util":wutil,"Solid Product Volume m3":None,"Kiln m3":_num(kiln["Gross m3"]),
                "Solid Volume Util":None,"Occupied Envelope m3":round(totalenv,5),"Geometric Occupancy Util":occ,
                "Primary Volume Target":float(settings.target_volume),"Volume Target Status":"ACHIEVED" if occ>=float(settings.target_volume) else "BELOW TARGET",
                "Avg Floor Area Util":None,"Supported Area Util":None,"Open Supported Area %":None,"Floors / Levels":None,
                "Floor Count Check":"PASS - EXACT PHYSICAL RECONCILIATION BEFORE RELEASE",
                "Used Height mm":round(float(exact_ev.get("height",0)),1),
                "Remaining Height mm":round(max(float(kiln.get("H mm",0))-float(settings.top_bottom_clearance_mm)-float(exact_ev.get("height",0)),0),1),
                "Plate Usage":exact_ev.get("plate_usage",""),
                "I-block Usage":exact_ev.get("iblock_usage",""),
                "Furniture Feasibility":"PASS - EXACT BEFORE RELEASE",
                "Usable Height mm":max(float(kiln.get("H mm",0))-float(settings.top_bottom_clearance_mm),0),
                "Height Util":float(exact_ev.get("height",0))/max(float(kiln.get("H mm",0))-float(settings.top_bottom_clearance_mm),1),
                "Effective Util":max(occ,wutil),"Mixed-WO Floors":None,"Mixed-WO Stacks":None,
                "Earliest Due":earliest,
                "Planning Priority Class":("P4 FILL - NO DUE DATE" if earliest is None else ("P1 OVERDUE / DUE RISK" if earliest<=complete else ("P2 DUE PROTECTED" if (earliest-complete).days<=7 else "P3 BALANCE PULL - FAR DUE"))),
                "Planning Policy":"POSITIVE PLAN: DUE DATE FIRST → BEST COMPATIBLE COMBINATION → HEIGHT/VOLUME/PROGRAM-WEIGHT UTILIZATION → DAILY WORKLOAD BALANCE",
                "Daily Capacity Objective":"2 NORMAL VITRIFIED STARTS/DAY EXCLUDING T0; RESIN BY INDEPENDENT KILN AVAILABILITY",
                "Running Days":cycle,"Program Finish Date":complete,"Unload / Take-Out Date":complete,"Firing Complete":complete,
                "Risk":risk,"Upstream Expedite WOs":0,"Limiting Constraint":"WEIGHT" if wutil>=0.98 else ("OCCUPANCY" if occ<float(settings.target_volume) else "TARGET REACHED"),
                "Kiln Selection Note":"FAST BOUNDED STAGE-4; detailed pattern not searched across whole queue",
                "Preferred Min Weight Status":"BELOW PREFERRED PROGRAM WEIGHT" if minkg>0 and totalkg<minkg else "WITHIN / ABOVE PREFERRED MIN",
                "T14 Fit Status":"T14 UNDER-FILLED" if kiln["Kiln"]=="T14" and (occ<float(settings.target_volume) or totalkg<minkg) else ("T14 JUSTIFIED" if kiln["Kiln"]=="T14" else ""),
                "Readiness Basis":"F7 POSITIVE PLAN; FIRING TARGET DRIVES UPSTREAM PUSH; READY QTY CONTROLS SHOP-FLOOR RELEASE ONLY",
                "Ready Now pcs":int(_ready_for_load),"MAKE Before Firing pcs":int(_make_for_load),
                "Planning Status":("READY / RELEASE" if int(_make_for_load)<=0 else "PLANNED — UPSTREAM CAPACITY COMMITMENT"),
                "Pull Refill pcs":int(exact_ev.get("refill_qty",0)),
                "Upstream / Downstream Method":"DOWNSTREAM FIRING CAPACITY PULLS COMPATIBLE DEMAND; UPSTREAM PREP→MIX→FORM PUSHES TO THE REQUIRED FIRING DATE",
                "Height Util %":round(100*float(exact_ev.get("height",0))/max(float(kiln.get("H mm",0))-float(settings.top_bottom_clearance_mm),1),1),
                "Volume Util %":round(100*occ,1),"Program Weight Util %":round(100*wutil,1),
                "Utilization Gap %":round(max(float(settings.target_volume)-occ,0)*100,1),
                "Utilization Status":("TARGET ACHIEVED" if occ>=float(settings.target_volume) else ("LOW — COMBINE / RIGHT-SIZE" if occ<0.60 else "BELOW TARGET — REVIEW")),
                "Planning Gap Reason":(
                    "No gap" if occ>=float(settings.target_volume)
                    else ("Physical fit/weight/furniture constrained" if fit_fail>0 or wutil>=0.95
                          else "Insufficient compatible same-program demand in bounded look-ahead")
                ),
                "Target Occupancy %":round(100*float(settings.target_volume),1),
                "Release Gate":decision,"Release Reason":reason,
                 "Alternative Action":("PUSH PREPARATION/MIXING/FORMING TO REQUIRED DATES; COMBINE COMPATIBLE DUE-DATE DEMAND; RECHECK HEIGHT/VOLUME/PROGRAM WEIGHT"
                                      if int(_make_for_load)>0 else "RELEASE AFTER SHOP-FLOOR CONFIRMATION"),
                "Physical Method":"V1.9.17 FAST CANDIDATE + EXACT DETAILED FURNITURE RECONCILIATION BEFORE RELEASE"
            }
            loads.append(loadrow)

            # Commit every physically planned future load so the next working day receives the next demand.
            # RELEASE remains a separate shop-floor gate; FUTURE PLANNED loads are capacity reservations/pull signals.
            for oi,q,fit_reason in selected:
                o=orders.loc[oi]
                before=int(_num(orders.at[oi,"Qty To Plan"]))
                orders.at[oi,"Qty To Plan"]=max(before-q,0)
                _wo_ready=min(int(q),max(int(_num(orders.at[oi,"Ready Remaining"])),0))
                _wo_make=max(int(q)-_wo_ready,0)
                orders.at[oi,"Ready Remaining"]=max(int(_num(orders.at[oi,"Ready Remaining"]))-_wo_ready,0)
                def _prev_work(_d):
                    _x=_d-timedelta(days=1)
                    while _x.weekday() not in settings.working_days: _x-=timedelta(days=1)
                    return _x
                _form_req=_prev_work(day); _mix_req=_prev_work(_form_req); _prep_req=_prev_work(_mix_req)
                details.append({
                    "Load ID":lid,"Load Date":day,"Kiln":kiln["Kiln"],"Program":program,"Work Order":o["Work Order"],
                    "Customer":o.get("Customer",""),"Specification":o.get("Specification",""),"Category":o.get("Category",""),
                    "Product Code":o.get("Product Code",""),
                    "Test Work Override":str(o.get("Test Work Override","AUTO") or "AUTO"),
                    "Test Work":("NORMAL / งานปกติ" if str(o.get("Test Work Override","AUTO") or "AUTO").upper()=="NORMAL" else ("TEST / งานทดสอบ" if (str(o.get("Test Work Override","AUTO") or "AUTO").upper()=="TEST" or str(o.get("Product Code","") or "").strip()[:1]=="1") else "NORMAL / งานปกติ")),
                    "Test Work Type":("NORMAL / งานปกติ" if str(o.get("Test Work Override","AUTO") or "AUTO").upper()=="NORMAL" else ("TEST-M / งานทดสอบ M - AXIS GRINDING WHEEL" if str(o.get("Product Code","") or "").strip()[:1]=="4" and str(o.get("Test Work Override","AUTO") or "AUTO").upper()!="TEST" else ("TEST / งานทดสอบ" if (str(o.get("Test Work Override","AUTO") or "AUTO").upper()=="TEST" or str(o.get("Product Code","") or "").strip()[:1]=="1") else "NORMAL / งานปกติ"))),
                    "Due Date":o.get("Due Date"),"Priority":o.get("Priority",""),"Qty pcs":q,"Planned Firing Qty":q,
                    "Ready Now pcs":_wo_ready,"MAKE pcs":_wo_make,
                    "Preparation Required By":_prep_req,"Mixing Required By":_mix_req,"Forming Required By":_form_req,
                    "Upstream PUSH Signal":(f"MAKE {_wo_make} pcs: PREP {_prep_req} → MIX {_mix_req} → FORM {_form_req}" if _wo_make>0 else "READY - NO EXTRA UPSTREAM QTY"),
                    "Planning Method":"PULL FROM DOWNSTREAM FIRING CAPACITY; PUSH UPSTREAM TO SUPPORT THE PULLED FIRING DATE",
                    "Planning Status":("READY / RELEASE" if _wo_make<=0 and str(decision).startswith("RELEASE") else "PLANNED — UPSTREAM CAPACITY COMMITMENT"),
                    "Capacity Assumption":("READY NOW" if _wo_make<=0 else "ASSUME ACHIEVABLE WHEN PREP/MIX/FORM REQUIREMENT IS WITHIN AVAILABLE CAPACITY; KEEP KILN IN PLAN"),
                    "Weight kg/pc":_num(o.get("Weight kg/pc")),"kg/pc":_num(o.get("Weight kg/pc")),"Weight kg":q*_num(o.get("Weight kg/pc")),
                    "Remaining Before Load":before,"Remaining After Load":max(before-q,0),"Geometry":o.get("Geometry",""),
                    "Footprint X mm":o.get("Footprint X"),"Footprint Y mm":o.get("Footprint Y"),"Piece Height mm":o.get("Piece Height"),
                    "Physical Screen":fit_reason,"Packing Modes":"FAST ENVELOPE + FURNITURE SUPPORT SCREEN",
                    "Running Days":cycle,"Program Finish Date":complete,"Unload / Take-Out Date":complete,"Firing Complete":complete,
                    "Delivery Status": ("BACK ORDER / OVERDUE" if (o.get("Due Date") is not None and o.get("Due Date") < settings.planning_start) else ("DUE TODAY" if o.get("Due Date") == settings.planning_start else "FUTURE / NO DATE")),"Risk":risk,"Release Gate":decision,"Release Reason":reason,"Data Check":o.get("Data Check",""),
                    "Readiness":o.get("Readiness",""),"Firing Ready Basis":o.get("Firing Ready Basis",""),"Plan2026 Actual Trace":o.get("Plan2026 Actual Trace","")
                })
            # Program occupies this kiln for its full running cycle. If the program
            # finishes/frees on Day D, the next automatic load is the next WORKING day.
            # Example: P3 load 28-Aug + 6 days = free 03-Sep; next load >= 04-Sep.
            kilns.at[kiln_idx,"Next Available"]=_workday(complete + timedelta(days=1), settings.working_days)
            _kn=_txt(kiln.get("Kiln","")).upper()
            _kt=_txt(kiln.get("Type","")).upper()
            if _kt=="RESINOID":
                resin_started.add(_kn)
            elif _kn=="T0":
                t0_starts += 1
            else:
                normal_vitrified_starts += 1
            programs_started.add(program)

        day += timedelta(days=1)

    floor=pd.DataFrame(columns=["Load ID","Note"])
    if loads:
        floor=pd.DataFrame([{"Load ID":r["Load ID"],"Note":"Detailed floor/3-view pattern intentionally deferred; planning allocation used fast deterministic physical/furniture screen."} for r in loads if not str(r.get("Release Gate","")).startswith("HOLD")])
    return pd.DataFrame(loads),pd.DataFrame(details),floor,pd.DataFrame(exceptions),kilns
