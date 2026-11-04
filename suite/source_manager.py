"""Shared Source Manager: every source file is imported ONCE into a named slot and reused by all modules.

* identical content (sha256) imported again into the same slot is a no-op ("DUPLICATE_UNCHANGED"); identical content already active in a DIFFERENT slot
  is refused ("DUPLICATE_OTHER_SLOT") because it is almost always the wrong file in the wrong box;
* the original bytes are kept forever under SOURCE_COPIES/<slot>/..., never overwritten; every import is a numbered revision;
* the active revision is also copied to COMPANY_DATA/<legacy target> so the existing modules (which call hub.fp(...)) read the same file;
* the sheet roles of the workbook are classified from headers (suite.sheet_roles); a slot that needs a master plan is rejected when the workbook has none;
* TWO separate production KPI slots, one Planning KPI reference slot and one Daily Status slot PER SECTION are kept;
* the registry is SQLite (WAL); the legacy JSON registry used by hub.py is kept in step.
Dated evidence: each revision stores its import time (Asia/Bangkok); nothing is treated as a permanent constant.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from . import sheet_roles as SR
from .common import bkk_now, sha256_bytes, REPO_ROOT

MODULES = {
    "hub": "Hub dashboard / Sources / Capacity tabs",
    "daily": "Daily Planner (8511)",
    "firing": "Firing Planner (8512)",
    "shared": "Shared Analysis (8513)",
    "suite": "Planning Suite (bond / material / backorder / MPS-MRP / new part)",
    "material": "Material status and stock analysis",
    "mobile": "Mobile WIP audit and part status",
    "help": "Bilingual help (F1)",
}


@dataclass(frozen=True)
class Slot:
    slot_id: str
    label: str
    legacy_target: Optional[str]          # file name modules already read from COMPANY_DATA
    modules: tuple
    require_role: Optional[str] = None    # at least one sheet with this role must exist
    section: Optional[str] = None
    note: str = ""
    knowledge_only: bool = False  # training / product-code register — already in Knowledge; do not ask operators to upload


SECTIONS = ("Preparation", "Mixing", "Forming", "Firing", "Grinding", "Packing")

SLOTS: dict = {s.slot_id: s for s in [
    Slot("PLAN_2026", "Plan workbook (Plan 2026)", "Plan-2026-LATEST.xlsx", ("hub", "daily", "firing", "shared", "suite", "mobile", "help"), SR.MASTER_PLAN,
         note="Master order sheet is found by header, not position."),
    Slot("FIRING_PLAN", "Firing plan", "Firing-Plan-LATEST.xlsx", ("hub", "firing", "daily")),
    Slot("SALES_FORECAST", "Sales forecast (forecast, NOT firm demand)", "Sales-Forecast-LATEST.xlsx", ("hub", "suite", "shared")),
    Slot("STOCK_ON_HAND", "Stock on hand (dated evidence)", "Stock-on-Hand-LATEST.xlsx", ("hub", "material", "suite", "daily", "firing")),
    Slot("SD_RECIPE_MASTER", "P280526 / SD recipe master", "P280526-LATEST.xlsx", ("hub", "suite")),
    Slot("PACKAGING_STANDARD", "Packaging standard", "Packaging-Standard-LATEST.xlsx", ("hub", "daily", "suite")),
    Slot("SALES_PRODUCT_REGISTER", "Sales registered product master (revision dated by Sales)", "Sales-Product-Register-LATEST.xlsx", ("hub", "suite"), note="Sales product registration/codes and registered description/pack quantity; compared with Production's packaging standard, never silently substituted."),
    Slot("RECOVERY_PLAN", "Production recovery plan (dated snapshot)", "Recovery-Plan-LATEST.xlsx", ("hub", "daily", "suite"), note="Dated recovery snapshot; original due date remains separate from internal recovery date. Import time and source rows are retained."),
    Slot("NEW_REQUEST_REFERENCE", "Test / new-request reference", "New-Request-Reference-LATEST.xlsx", ("hub", "suite")),
    Slot("BOND_MRP", "Bond MRP workbook", "Bond-MRP-LATEST.xlsx", ("suite",)),
    Slot("CAPACITY_DATABASE", "Capacity database (units and time basis preserved)", "CAPACITY_DATABASE.xlsx", ("hub", "suite", "daily", "firing"), SR.CAPACITY,
         note="Bundled copy apps/daily/CAPACITY_DATABASE.xlsx is the initial revision."),
    Slot("COST_RESIN", "Costing source - Resin cost and material rates", "COSTING/Resin-Cost-Template-LATEST.xlsx", ("hub", "suite"), note="Effective-dated rates; conflicting values remain flagged until approved."),
    Slot("COST_VITIFILE", "Costing source - Vitifile cost and material rates", "COSTING/Vitifile-Cost-Template-LATEST.xlsx", ("hub", "suite"), note="Effective-dated rates; unresolved lookups remain flagged."),
    Slot("COST_REPLACEMENT", "Costing source - Replacement / reject costing", "COSTING/Replacement-Cost-LATEST.xlsx", ("hub", "suite"), note="Reconciled with Plan FH only as a diagnostic."),
    Slot("KPI_SECTION_PLAN_VS_ACTUAL", "KPI source 1 - section plan vs actual", "KPI/Section-Performance-KPI-LATEST.xlsx", ("daily", "hub", "shared"), note="Same file the Daily Planner reads."),
    Slot("KPI_DELIVERY_WAREHOUSE", "KPI source 2 - delivery / warehouse receipt", "KPI/Warehouse-Delivery-KPI-LATEST.xlsx", ("daily", "hub", "shared"), note="Same file the Daily Planner reads."),
    Slot("KPI_PLANNING_REFERENCE", "Retired nine-measure Planning KPI reference", "KPI/Planning-KPI-Evidence-LATEST.xlsx", ("hub", "suite"), note="Historical only. Use Department KPI retained evidence for the owner-confirmed three measures.", knowledge_only=True),
    Slot("KPI_PLANNING_DAILY_EXECUTION", "Legacy Planning KPI execution slot — archived", "KPI/Planning-KPI-Daily-Execution-LATEST.xlsx", ("hub", "suite"), note="Import revised opening/issuance evidence once on Department KPI; originals persist there.", knowledge_only=True),
    Slot("KPI_PLANNING_JOB_CLOSURE", "Legacy Planning KPI closure slot — archived", "KPI/Planning-KPI-Job-Closure-LATEST.xlsx", ("hub", "suite"), note="Use the revised separate closure workbook on Department KPI.", knowledge_only=True),
    Slot("KPI_EMPLOYEE_REFERENCE", "Legacy employee appraisal reference — archived", "KPI/Employee-KPI-Reference-LATEST.xlsx", ("hub", "suite"), note="Historical reference only; revised staff KPI evidence is retained on Department KPI.", knowledge_only=True),
    *[Slot(f"DAILY_STATUS_{s.upper()}", f"Daily Status - {s}", None, ("daily", "hub", "suite"), section=s, note="Published to DAILY_STATUS/<Section>__<period>__LATEST.xlsx, the folder the Daily Planner reads.") for s in SECTIONS],
    Slot("SEPT_OPEN_CLOSED", "Retired combined Open/Close Job format", "Job-Register-LATEST.xlsx", ("hub", "daily", "shared"), SR.OPEN_JOB, knowledge_only=True),
    Slot("PROCESS_CLOSE", "Process-wise closing (all sections)", "Process-Close-LATEST.xlsx", ("hub", "daily", "shared"),
         note="One process-close workbook uploaded on Home; Daily and reports read this same file. No format is invented."),
    *[Slot(f"PROCESS_CLOSE_{s.upper()}", f"Process-wise closing - {s}", None, ("hub", "daily", "shared"), section=s,
           note="Published to PROCESS_CLOSE/<Section>__LATEST.xlsx") for s in SECTIONS],
    Slot("PRODUCT_REGISTER", "Registered product codes (11 / 18 digit)", "Product-Register-LATEST.xlsx", ("hub", "suite", "help"),
         note="Product codification is in Knowledge / F1. Operators do not upload this slot.", knowledge_only=True),
]}

def _validate_special_workbook(path: str, slot_id: str) -> str:
    """Reject an obviously wrong workbook before it replaces an active source."""
    if slot_id not in {"RECOVERY_PLAN", "SALES_PRODUCT_REGISTER", "PACKAGING_STANDARD"}:
        return ""
    from openpyxl import load_workbook
    wb=load_workbook(path,read_only=True,data_only=True)
    try:
        names={n.strip().lower():n for n in wb.sheetnames}
        if slot_id=="RECOVERY_PLAN":
            n=names.get("แผน recovery")
            if not n: return "Recovery workbook must contain the sheet แผน Recovery."
            ws=wb[n]; ws.reset_dimensions()
            row=next(ws.iter_rows(min_row=3,max_row=3,max_col=8,values_only=True),())
            if not {"Fac No","กำหนดส่งมอบเดิม","กำหนดส่งใหม่"}.issubset({str(v).strip() for v in row if v is not None}):
                return "Recovery sheet is missing required row-3 fields: Fac No, กำหนดส่งมอบเดิม, กำหนดส่งใหม่."
        elif slot_id=="SALES_PRODUCT_REGISTER":
            candidates=[n for n in wb.sheetnames if n.strip().lower().startswith("สินค้าขึ้นทะเบียน รหัส")]
            if not candidates: return "Sales product register needs a sheet beginning สินค้าขึ้นทะเบียน รหัส."
            ok=False
            for n in candidates:
                ws=wb[n]; ws.reset_dimensions()
                row=next(ws.iter_rows(min_row=2,max_row=2,max_col=18,values_only=True),())
                if len(row)>11 and "Codeสินค้าส่งขึ้น" in str(row[11] or ""): ok=True; break
            if not ok: return "Sales product register is missing the registered product code field in column L, row 2."
        else:
            n=names.get("มาตรฐานการบรรจุ") or names.get("packaging standard")
            if not n: return "Production workbook needs มาตรฐานการบรรจุ or Packaging standard sheet."
            ws=wb[n]; ws.reset_dimensions()
            valid=False
            for rn in range(1,6):
                row=next(ws.iter_rows(min_row=rn,max_row=rn,max_col=18,values_only=True),())
                texts={str(v).strip() for v in row if v is not None}
                if "จำนวนบรรจุต่อกล่อง" in texts and ("รหัสสินค้า" in texts or "Product Code" in texts): valid=True;break
            if not valid:return "Packaging standard needs Product Code / รหัสสินค้า and Pcs/Box / จำนวนบรรจุต่อกล่อง headers."
    finally:
        wb.close()
    return ""

_SCHEMA = """
CREATE TABLE IF NOT EXISTS revisions(
  id INTEGER PRIMARY KEY AUTOINCREMENT, slot_id TEXT NOT NULL, revision_no INTEGER NOT NULL, sha256 TEXT NOT NULL,
  original_name TEXT NOT NULL, stored_path TEXT NOT NULL, size_bytes INTEGER NOT NULL, imported_at TEXT NOT NULL, imported_by TEXT,
  section TEXT, note TEXT, source_folder TEXT, sheet_roles TEXT, active INTEGER NOT NULL DEFAULT 0, UNIQUE(slot_id, revision_no));
CREATE INDEX IF NOT EXISTS ix_rev_sha ON revisions(sha256);
CREATE INDEX IF NOT EXISTS ix_rev_slot ON revisions(slot_id, active);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, slot_id TEXT, sha256 TEXT, outcome TEXT NOT NULL, message TEXT, by_user TEXT);
"""


@dataclass
class ImportResult:
    status: str                       # IMPORTED | DUPLICATE_UNCHANGED | DUPLICATE_OTHER_SLOT | REJECTED | REACTIVATED
    slot_id: str
    message: str
    revision_no: Optional[int] = None
    sha256: str = ""
    affected_modules: list = field(default_factory=list)
    sheet_roles: list = field(default_factory=list)

    @property
    def ok(self):
        return self.status in ("IMPORTED", "REACTIVATED", "DUPLICATE_UNCHANGED")


class SourceManager:
    def __init__(self, shared_root, company_data=None, source_copies=None, legacy_registry: Optional[Path] = None, bundled_capacity: Optional[Path] = None):
        self.root = Path(shared_root)
        self.data = Path(company_data) if company_data else self.root / "COMPANY_DATA"
        self.copies = Path(source_copies) if source_copies else self.root / "SOURCE_COPIES"
        self.legacy_registry = Path(legacy_registry) if legacy_registry else self.root / "source_registry.json"
        for d in (self.root, self.data, self.copies):
            d.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "source_manager.sqlite"
        with self._con() as c:
            c.executescript(_SCHEMA)
        bundled = bundled_capacity or (REPO_ROOT / "apps" / "daily" / "CAPACITY_DATABASE.xlsx")
        if bundled.exists() and not self.active("CAPACITY_DATABASE"):
            self.import_bytes("CAPACITY_DATABASE", bundled.name, bundled.read_bytes(), "system", note="Bundled with the release (initial revision)")
        planning_kpi = REPO_ROOT / "knowledge" / "Planning_KPI_Reference_Q4_2026.xlsx"
        if not SLOTS["KPI_PLANNING_REFERENCE"].knowledge_only and planning_kpi.exists() and not self.active("KPI_PLANNING_REFERENCE"):
            self.import_bytes("KPI_PLANNING_REFERENCE", planning_kpi.name, planning_kpi.read_bytes(), "system", note="Owner-supplied Planning KPI reference; result cells remain blank until evidence is recorded")

    def _con(self):
        c = sqlite3.connect(self.db_path, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        return c

    def active(self, slot_id) -> Optional[dict]:
        with self._con() as c:
            r = c.execute("SELECT * FROM revisions WHERE slot_id=? AND active=1", (slot_id,)).fetchone()
        return dict(r) if r else None

    def history(self, slot_id=None) -> list:
        with self._con() as c:
            q = "SELECT * FROM revisions" + (" WHERE slot_id=?" if slot_id else "") + " ORDER BY slot_id, revision_no DESC"
            return [dict(r) for r in c.execute(q, (slot_id,) if slot_id else ())]

    def events(self, limit=200) -> list:
        with self._con() as c:
            return [dict(r) for r in c.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))]

    def active_path(self, slot_id) -> Optional[Path]:
        a = self.active(slot_id)
        return Path(a["stored_path"]) if a else None

    def _log(self, c, outcome, slot_id, sha, msg, user):
        c.execute("INSERT INTO events(at,slot_id,sha256,outcome,message,by_user) VALUES(?,?,?,?,?,?)", (bkk_now().isoformat(timespec="seconds"), slot_id, sha, outcome, msg, user))

    def import_bytes(self, slot_id, original_name, data: bytes, user="", section="", note="", source_folder="") -> ImportResult:
        slot = SLOTS.get(slot_id)
        if slot is None:
            return ImportResult("REJECTED", slot_id, f"Unknown slot {slot_id}")
        if slot.knowledge_only:
            return ImportResult("REJECTED", slot_id,
                                "This source is archived/reference-only. Use Department KPI for revised KPI evidence; training references stay in Knowledge / F1.")
        from .month_register import is_xls, prepare_upload_bytes
        stored_name = Path(original_name).name
        if is_xls(original_name):
            try:
                data = prepare_upload_bytes(original_name, data)
            except ValueError as e:
                return ImportResult("REJECTED", slot_id, str(e))
            stored_name = Path(original_name).stem + ".xlsx"
        sha = sha256_bytes(data)
        affected = [MODULES[m] for m in slot.modules]
        with self._con() as c:
            c.execute("BEGIN IMMEDIATE")
            act = c.execute("SELECT * FROM revisions WHERE slot_id=? AND active=1", (slot_id,)).fetchone()
            if act and act["sha256"] == sha:
                msg = f"Identical to active revision {act['revision_no']} (imported {act['imported_at']}); nothing changed."
                self._log(c, "DUPLICATE_UNCHANGED", slot_id, sha, msg, user)
                return ImportResult("DUPLICATE_UNCHANGED", slot_id, msg, act["revision_no"], sha, affected, json.loads(act["sheet_roles"] or "[]"))
            other = c.execute("SELECT slot_id, revision_no FROM revisions WHERE sha256=? AND active=1 AND slot_id<>?", (sha, slot_id)).fetchone()
            if other:
                msg = f"This exact file is already the active source of slot {other['slot_id']} (revision {other['revision_no']}). Import it once and reuse it; not added to {slot_id}."
                self._log(c, "DUPLICATE_OTHER_SLOT", slot_id, sha, msg, user)
                return ImportResult("DUPLICATE_OTHER_SLOT", slot_id, msg, None, sha, [])
            roles = []
            if stored_name.lower().endswith((".xlsx", ".xlsm")):
                with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as t:
                    t.write(data)
                    tmp = t.name
                try:
                    roles = [r.as_dict() for r in SR.classify_workbook(tmp)]
                    _special_error=_validate_special_workbook(tmp,slot_id)
                    if _special_error:
                        msg=f"Rejected: {_special_error}"
                        self._log(c,"REJECTED",slot_id,sha,msg,user)
                        return ImportResult("REJECTED",slot_id,msg,None,sha,[],roles)
                except Exception as e:
                    msg = f"Not a readable Excel workbook: {e}"
                    self._log(c, "REJECTED", slot_id, sha, msg, user)
                    return ImportResult("REJECTED", slot_id, msg, None, sha)
                finally:
                    os.unlink(tmp)
            if slot_id == "FIRING_PLAN":
                from apps.firing.previous_issued import validate_firing_source
                _firing_ok, _firing_msg = validate_firing_source(data)
                if not _firing_ok:
                    msg = f"Rejected firing source: {_firing_msg}"
                    self._log(c, "REJECTED", slot_id, sha, msg, user)
                    return ImportResult("REJECTED", slot_id, msg, None, sha, [], roles)
                roles.append({"sheet": "Detected firing table", "role": "FIRING_PLAN", "evidence": _firing_msg,
                              "rows": 0, "cols": 0, "confidence": "HEADER"})
            if slot.require_role and not any(r["role"] == slot.require_role for r in roles):
                if not (slot_id == "SEPT_OPEN_CLOSED" and any(r["role"] == SR.CLOSE_JOB for r in roles)):
                    msg = (f"Rejected: slot '{slot.label}' needs a sheet with role {slot.require_role}; found roles: "
                           + ", ".join(sorted({r['role'] for r in roles})) + ". Wrong file for this slot?")
                    self._log(c, "REJECTED", slot_id, sha, msg, user)
                    return ImportResult("REJECTED", slot_id, msg, None, sha, [], roles)
            prior = c.execute("SELECT * FROM revisions WHERE slot_id=? AND sha256=? ORDER BY revision_no DESC LIMIT 1", (slot_id, sha)).fetchone()
            nxt = (c.execute("SELECT COALESCE(MAX(revision_no),0)+1 FROM revisions WHERE slot_id=?", (slot_id,)).fetchone()[0])
            if prior:
                stored = Path(prior["stored_path"])
            else:
                folder = self.copies / slot_id
                folder.mkdir(parents=True, exist_ok=True)
                stored = folder / f"r{nxt:03d}_{bkk_now():%Y%m%d_%H%M%S}_{sha[:8]}_{stored_name}"
                stored.write_bytes(data)
            c.execute("UPDATE revisions SET active=0 WHERE slot_id=?", (slot_id,))
            c.execute("INSERT INTO revisions(slot_id,revision_no,sha256,original_name,stored_path,size_bytes,imported_at,imported_by,section,note,source_folder,sheet_roles,active)"
                      " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1)",
                      (slot_id, nxt, sha, Path(original_name).name, str(stored), len(data), bkk_now().isoformat(timespec="seconds"), user, section or slot.section or "", note,
                       source_folder, json.dumps(roles, ensure_ascii=False)))
            status = "REACTIVATED" if prior else "IMPORTED"
            msg = f"{'Re-activated earlier content as' if prior else 'Imported as'} revision {nxt}; original kept at {stored}"
            self._log(c, status, slot_id, sha, msg, user)
        self._publish(slot, stored, original_name, user, section, sha, len(data))
        return ImportResult(status, slot_id, msg, nxt, sha, affected, roles)

    def _publish(self, slot: Slot, stored: Path, original_name, user, section, sha, size):
        """Copy the ACTIVE revision where the existing modules look for it, and keep the legacy JSON registry in step."""
        if slot.section and slot.slot_id.startswith("DAILY_STATUS_"):
            self._publish_daily_status(slot, stored, original_name, user, sha)
        elif slot.section and slot.slot_id.startswith("PROCESS_CLOSE_"):
            self._publish_section_latest("PROCESS_CLOSE", slot, stored, original_name, user, sha)
        elif slot.legacy_target and slot.legacy_target.startswith("KPI/"):
            dest = self.root / slot.legacy_target
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_name(dest.name + ".tmp")
            shutil.copyfile(stored, tmp)
            os.replace(tmp, dest)
        elif slot.legacy_target:
            dest = self.data / slot.legacy_target
            tmp = dest.with_name(dest.name + ".tmp")
            shutil.copyfile(stored, tmp)
            os.replace(tmp, dest)
        if not slot.legacy_target or slot.legacy_target.startswith("KPI/"):
            return
        try:
            reg = json.loads(self.legacy_registry.read_text(encoding="utf-8")) if self.legacy_registry.exists() else {}
        except Exception:
            reg = {}
        key = slot.legacy_target or slot.slot_id
        prior = reg.get(key, {})
        reg[key] = {**prior, "active_path": str(self.data / slot.legacy_target) if slot.legacy_target else str(stored), "original_name": original_name,
                    "registered_at": bkk_now().isoformat(timespec="seconds"), "updated_by": user, "section": section, "sha256": sha, "size_bytes": size,
                    "archive_copy_path": str(stored), "uploaded_through": "Source Manager", "slot_id": slot.slot_id}
        self.legacy_registry.parent.mkdir(parents=True, exist_ok=True)
        self.legacy_registry.write_text(json.dumps(reg, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    def _publish_section_latest(self, folder_name: str, slot: Slot, stored: Path, original_name, user, sha):
        folder = self.root / folder_name
        hist = folder / "history"
        hist.mkdir(parents=True, exist_ok=True)
        dest = folder / f"{slot.section}__LATEST.xlsx"
        if dest.exists():
            (hist / f"{bkk_now():%Y%m%d_%H%M%S}_{dest.name}").write_bytes(dest.read_bytes())
        shutil.copyfile(stored, dest)
        reg_path = folder / "source_registry.json"
        try:
            reg = json.loads(reg_path.read_text(encoding="utf-8")) if reg_path.exists() else {"records": []}
        except Exception:
            reg = {"records": []}
        reg.setdefault("records", [])
        for e in reg["records"]:
            if e.get("active") and e.get("section") == slot.section:
                e["active"] = False
        reg["records"].append({"section": slot.section, "original_filename": original_name, "stored_filename": dest.name,
                               "stored_path": str(dest.resolve()), "sha256": sha, "size_bytes": dest.stat().st_size,
                               "uploaded_by": user, "uploaded_at": bkk_now().isoformat(timespec="seconds"),
                               "active": True, "via": "Source Manager"})
        reg_path.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")

    def _publish_daily_status(self, slot: Slot, stored: Path, original_name, user, sha):
        import re, zipfile
        import openpyxl
        folder = self.root / "DAILY_STATUS"
        hist = folder / "history"
        hist.mkdir(parents=True, exist_ok=True)
        counts: dict = {}
        wb = openpyxl.load_workbook(stored, read_only=True)
        try:
            for name in wb.sheetnames:
                m = re.fullmatch(r"\s*(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\s*", name)
                if m:
                    yr = int(m.group(3)); yr = yr - 543 if yr > 2400 else yr
                    counts[(yr, int(m.group(2)))] = counts.get((yr, int(m.group(2))), 0) + 1
        finally:
            wb.close()
        period = ""
        if counts:
            top = max(counts, key=counts.get)
            period = f"{top[0]}-{top[1]:02d}" if counts[top] / sum(counts.values()) >= 0.75 else ""
        name = f"{slot.section}__{period}__LATEST.xlsx" if period else f"{slot.section}__MANAGER__LATEST.xlsx"
        dest = folder / name
        reg_path = folder / "source_registry.json"
        try:
            reg = json.loads(reg_path.read_text(encoding="utf-8")) if reg_path.exists() else {"records": []}
        except Exception:
            reg = {"records": []}
        reg.setdefault("records", [])
        for e in reg["records"]:
            if e.get("active") and e.get("section") == slot.section and e.get("report_period") == (period or None):
                e["active"] = False
        if dest.exists():
            (hist / f"{bkk_now():%Y%m%d_%H%M%S}_{name}").write_bytes(dest.read_bytes())
        shutil.copyfile(stored, dest)
        reg["records"].append({"section": slot.section, "report_period": period or None, "original_filename": original_name, "stored_filename": name,
                               "stored_path": str(dest.resolve()), "sha256": sha, "size_bytes": dest.stat().st_size, "uploaded_by": user,
                               "uploaded_at": bkk_now().isoformat(timespec="seconds"), "active": True, "via": "Source Manager"})
        reg_path.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")

    def adopt_existing(self, user="adopt") -> list:
        """Register files that the Daily Planner already stored (KPI x2, Daily Status per section) as slot revisions without re-importing duplicates."""
        out = []
        for slot_id, rel in (("KPI_SECTION_PLAN_VS_ACTUAL", "KPI/Section-Performance-KPI-LATEST.xlsx"), ("KPI_DELIVERY_WAREHOUSE", "KPI/Warehouse-Delivery-KPI-LATEST.xlsx")):
            p = self.root / rel
            if p.exists() and not self.active(slot_id):
                out.append(self._adopt(slot_id, p, user))
        # Adopt bundled owner-supplied October Planning KPI evidence on first start.
        bundled_kpi = self.root / "knowledge" / "kpi" / "inputs"
        for slot_id, pattern in (
            ("KPI_PLANNING_DAILY_EXECUTION", "*in*out*.xlsx"),
            ("KPI_PLANNING_JOB_CLOSURE", "*closure*.xlsx"),
        ):
            if not SLOTS[slot_id].knowledge_only and not self.active(slot_id):
                matches = sorted(bundled_kpi.glob(pattern), key=lambda x: x.stat().st_mtime)
                if matches:
                    out.append(self._adopt(slot_id, matches[-1], user, note="bundled owner-supplied Planning KPI evidence"))
        for slot in SLOTS.values():
            if slot.knowledge_only:
                continue
            if slot.legacy_target and "/" not in slot.legacy_target and not self.active(slot.slot_id):
                p = self.data / slot.legacy_target
                if p.exists() and p.stat().st_size > 0:
                    out.append(self._adopt(slot.slot_id, p, user, note="adopted from existing COMPANY_DATA file"))
        reg_path = self.root / "DAILY_STATUS" / "source_registry.json"
        if reg_path.exists():
            try:
                recs = json.loads(reg_path.read_text(encoding="utf-8")).get("records", [])
            except Exception:
                recs = []
            latest: dict = {}
            for r in recs:
                if r.get("active") and Path(r.get("stored_path", "")).exists():
                    k = r.get("section")
                    if k not in latest or r.get("uploaded_at", "") > latest[k].get("uploaded_at", ""):
                        latest[k] = r
            for sec, r in latest.items():
                sid = f"DAILY_STATUS_{str(sec).upper()}"
                if sid in SLOTS and not self.active(sid):
                    out.append(self._adopt(sid, Path(r["stored_path"]), user, name=r.get("original_filename"), note=f"adopted from Daily Planner (period {r.get('report_period')})"))
        pc_folder = self.root / "PROCESS_CLOSE"
        if pc_folder.exists():
            for p in sorted(pc_folder.glob("*__LATEST.xlsx")):
                sec = p.name.split("__", 1)[0]
                sid = f"PROCESS_CLOSE_{sec.upper()}"
                if sid in SLOTS and not self.active(sid):
                    out.append(self._adopt(sid, p, user, note="adopted from existing PROCESS_CLOSE folder"))
        return out

    def _adopt(self, slot_id, path: Path, user, name=None, note="adopted from existing installation") -> ImportResult:
        slot = SLOTS[slot_id]
        data = path.read_bytes()
        res = self.import_bytes(slot_id, name or path.name, data, user, note=note)
        return res

    def import_file(self, slot_id, path, user="", **kw) -> ImportResult:
        p = Path(path)
        return self.import_bytes(slot_id, p.name, p.read_bytes(), user, **kw)

    def rollback(self, slot_id, revision_no, user="") -> ImportResult:
        """Make an earlier revision active again (original bytes are still on disk)."""
        with self._con() as c:
            r = c.execute("SELECT * FROM revisions WHERE slot_id=? AND revision_no=?", (slot_id, revision_no)).fetchone()
        if not r:
            return ImportResult("REJECTED", slot_id, f"No revision {revision_no}")
        return self.import_bytes(slot_id, r["original_name"], Path(r["stored_path"]).read_bytes(), user, note=f"rollback to revision {revision_no}")

    def status_table(self) -> list:
        rows = []
        for s in SLOTS.values():
            a = self.active(s.slot_id)
            rows.append({"slot": s.slot_id, "label": s.label, "section": s.section or "",
                         "state": ("KNOWLEDGE" if s.knowledge_only else ("ACTIVE" if a else "MISSING")),
                         "revision": a["revision_no"] if a else None, "file": a["original_name"] if a else "", "imported_at": a["imported_at"] if a else "",
                         "imported_by": a["imported_by"] if a else "", "sha256": a["sha256"][:12] if a else "", "stored": a["stored_path"] if a else "",
                         "affects": "; ".join(MODULES[m] for m in s.modules)})
        return rows

    def missing(self) -> list:
        return [s.slot_id for s in SLOTS.values() if not s.knowledge_only and not self.active(s.slot_id)]

    def consistency_report(self) -> list:
        """Every module reads COMPANY_DATA/<legacy target>; verify that file is byte-identical to the active revision."""
        out = []
        for s in SLOTS.values():
            a = self.active(s.slot_id)
            if not a or not s.legacy_target:
                continue
            # Match _publish: shared KPI files live under shared_root/KPI,
            # while ordinary legacy sources live under COMPANY_DATA.
            base = self.root if s.legacy_target.startswith("KPI/") else self.data
            d = base / s.legacy_target
            ok = d.exists() and sha256_bytes(d.read_bytes()) == a["sha256"]
            out.append({"slot": s.slot_id, "published_file": str(d), "matches_active_revision": ok})
        return out
