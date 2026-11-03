import tempfile
import unittest
from pathlib import Path

import pandas as pd

from suite.firing_pattern_view import load_existing_firing


class ExistingFiringViewTests(unittest.TestCase):
    def test_operator_print_is_read_without_replanning(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "operator.xlsx"
            with pd.ExcelWriter(path) as writer:
                pd.DataFrame([
                    {"Load ID / รหัสโหลด": "L-1", "Loading Date / วันที่เข้าเตา": "2026-10-14", "Kiln / เตา": "K1", "Program / โปรแกรม": "P1", "Work Order / ใบสั่งผลิต": "WO-01", "Planned Qty (pcs) / จำนวนแผน (ชิ้น)": 100},
                    {"Load ID / รหัสโหลด": "L-1", "Loading Date / วันที่เข้าเตา": "2026-10-14", "Kiln / เตา": "K1", "Program / โปรแกรม": "P1", "Work Order / ใบสั่งผลิต": "WO-02", "Planned Qty (pcs) / จำนวนแผน (ชิ้น)": 50},
                ]).to_excel(writer, index=False, sheet_name="Operator Print")
            result = load_existing_firing(path)
            self.assertEqual(len(result["schedule"]), 1)
            row = result["schedule"].iloc[0]
            self.assertEqual(row["Qty"], 150)
            self.assertEqual(row["WO Count"], 2)
            self.assertFalse(result["pattern_sheet"])
            self.assertTrue({"WO-01", "WO-02"}.issubset(set(row["WO"].split(", "))))

    def test_existing_full_plan_pattern_rows_are_loaded_as_saved(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "full.xlsx"
            floor = pd.DataFrame([{"Load ID": "L-2", "Floor": 1, "Work Order": "WO-03", "Qty": 25, "x mm": 0, "y mm": 0,
                                   "Footprint W mm": 100, "Footprint H mm": 100, "Placement Mode": "BASE/TOP", "Base Geometry": "CIRCULAR"}])
            with pd.ExcelWriter(path) as writer:
                pd.DataFrame([{"Load ID": "L-2", "Load Date": "2026-10-15", "Kiln": "K2", "Program": "P2", "Qty pcs": 25}]).to_excel(writer, index=False, sheet_name="Firing Loads")
                pd.DataFrame([{"Load ID": "L-2", "Load Date": "2026-10-15", "Kiln": "K2", "Program": "P2", "Work Order": "WO-03", "Planned Firing Qty": 25}]).to_excel(writer, index=False, sheet_name="Operator Print")
                floor.to_excel(writer, index=False, sheet_name="Floor Pattern Data")
            result = load_existing_firing(path)
            self.assertEqual(result["pattern_sheet"], "Floor Pattern Data")
            self.assertEqual(result["floor"].iloc[0]["Work Order"], "WO-03")


if __name__ == "__main__":
    unittest.main()
