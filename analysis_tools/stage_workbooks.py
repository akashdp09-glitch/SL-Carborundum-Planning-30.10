"""Read-only evidence intake while the full application source is unavailable.

This is a staging database, not the application's operational database. No
workbook formulas are executed. Raw rows, errors and duplicates are retained.
Recovery intake deliberately reads only the owner's named second worksheet.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

PLAN_SHEETS = {
    "แผนการเผา": 220,
    "เตรียมจ่าย": 20,
    "ผสมจ่าย": 10,
    "ขึ้นรูปจ่าย": 12,
    "เตาจ่าย": 14,
    "เข้าเผา": 30,
    "เจียร": 13,
    "PACK": 15,
}


def encode(value):
    if isinstance(value, datetime):
        return {"type": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"type": "date", "value": value.isoformat()}
    if isinstance(value, time):
        return {"type": "time", "value": value.isoformat()}
    if isinstance(value, timedelta):
        return {"type": "timedelta", "seconds": value.total_seconds()}
    raise TypeError(f"Unsupported evidence type: {type(value).__name__}")


def json_text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=encode)


def selected_sheets(workbook, filename):
    if filename.startswith("Plan "):
        missing = set(PLAN_SHEETS) - set(workbook.sheetnames)
        if missing:
            raise ValueError(f"Missing production sheets: {sorted(missing)}")
        return PLAN_SHEETS
    if filename.startswith("แผนผลิต Recovery"):
        if len(workbook.sheetnames) < 2 or workbook.sheetnames[1] != "แผน Recovery":
            raise ValueError("Expected second worksheet named แผน Recovery")
        return {"แผน Recovery": 176}
    if filename in {
        "KPI_Sirinun_monthly.xlsx", "KPI_Chosita_completed.xlsx",
        "October_in out.xlsx", "October-2026_job closure.xlsx",
    }:
        return {s.title: s.max_column for s in workbook}
    raise ValueError(f"Unrecognised source: {filename}; inspect before importing")


def connect(database):
    database.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(database)
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS imports (
            sha256 TEXT PRIMARY KEY, original_filename TEXT NOT NULL,
            imported_at_utc TEXT NOT NULL, size_bytes INTEGER NOT NULL,
            purpose TEXT NOT NULL DEFAULT 'STAGING_ONLY_NOT_OPERATIONAL'
        );
        CREATE TABLE IF NOT EXISTS sheets (
            source_sha256 TEXT NOT NULL REFERENCES imports(sha256),
            sheet_name TEXT NOT NULL, reported_rows INTEGER,
            reported_columns INTEGER, retained_columns INTEGER NOT NULL,
            PRIMARY KEY(source_sha256, sheet_name)
        );
        CREATE TABLE IF NOT EXISTS evidence_rows (
            source_sha256 TEXT NOT NULL, sheet_name TEXT NOT NULL,
            excel_row INTEGER NOT NULL, cells_json TEXT NOT NULL,
            PRIMARY KEY(source_sha256, sheet_name, excel_row),
            FOREIGN KEY(source_sha256, sheet_name)
                REFERENCES sheets(source_sha256, sheet_name)
        );
        CREATE TABLE IF NOT EXISTS formula_cells (
            source_sha256 TEXT NOT NULL, sheet_name TEXT NOT NULL,
            cell TEXT NOT NULL, formula TEXT NOT NULL,
            PRIMARY KEY(source_sha256, sheet_name, cell),
            FOREIGN KEY(source_sha256, sheet_name)
                REFERENCES sheets(source_sha256, sheet_name)
        );
    """)
    return con


def stage(con, source):
    with source.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    existing = con.execute(
        "SELECT 1 FROM imports WHERE sha256=?", (digest,)
    ).fetchone()
    if existing:
        return {"filename": source.name, "sha256": digest, "status": "unchanged"}
    workbook = load_workbook(source, read_only=True, data_only=True, keep_links=False)
    try:
        chosen = selected_sheets(workbook, source.name)
        count = 0
        with con:
            con.execute("INSERT INTO imports(sha256,original_filename,imported_at_utc,size_bytes) VALUES(?,?,?,?)",
                        (digest, source.name, datetime.now(timezone.utc).isoformat(), source.stat().st_size))
            for title, width in chosen.items():
                sheet = workbook[title]
                con.execute("INSERT INTO sheets VALUES(?,?,?,?,?)",
                            (digest, title, sheet.max_row, sheet.max_column, width))
                batch = []
                for row_number, row in enumerate(sheet.iter_rows(max_col=width, values_only=True), 1):
                    cells = {get_column_letter(i): value for i, value in enumerate(row, 1) if value is not None}
                    if not cells:
                        continue
                    batch.append((digest, title, row_number, json_text(cells)))
                    if len(batch) >= 1000:
                        con.executemany("INSERT INTO evidence_rows VALUES(?,?,?,?)", batch)
                        count += len(batch)
                        batch.clear()
                con.executemany("INSERT INTO evidence_rows VALUES(?,?,?,?)", batch)
                count += len(batch)
            # Preserve exact KPI formulas as evidence; cached values are not recalculated.
            if source.name.startswith("KPI_"):
                formulas = load_workbook(source, read_only=True, data_only=False, keep_links=False)
                try:
                    for sheet in formulas:
                        for row in sheet.iter_rows():
                            for cell in row:
                                if cell.data_type == "f":
                                    con.execute("INSERT INTO formula_cells VALUES(?,?,?,?)",
                                                (digest, sheet.title, cell.coordinate, cell.value))
                finally:
                    formulas.close()
        return {"filename": source.name, "sha256": digest, "status": "staged",
                "retained_rows": count, "sheets": list(chosen)}
    finally:
        workbook.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attachments", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    args = parser.parse_args()
    with connect(args.database) as con:
        for path in sorted(args.attachments.rglob("*.xlsx")):
            print(json_text(stage(con, path)), flush=True)
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


if __name__ == "__main__":
    main()
