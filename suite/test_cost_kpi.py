"""Focused tests for the new cost/KPI analysis (synthetic workbooks only)."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from openpyxl import Workbook

from suite.cost_kpi import material_exposure, replacement_diagnostics


class CostKpiTests(unittest.TestCase):
    def test_material_shortage_keeps_on_hand_inbound_and_lab_hold_separate(self):
        with TemporaryDirectory() as td:
            td = Path(td)
            stock = Workbook(); ws = stock.active; ws.title = "Abrasive"
            ws.append(["รหัสสินค้า", None, None, None, "รายละเอียดสินค้า", None, None, None, None,
                       "ใบงานเปิดผลิต", "วัตถุดิบคงคลัง", "รอวัถุดิบเข้า", "รอผลLAB", "BalanceStock"])
            ws.append(["MAT01", None, None, None, "test", None, None, None, None, 1000, 400, 300, 100, -500])
            stock_path = td / "stock.xlsx"; stock.save(stock_path)
            cost = Workbook(); ps = cost.active; ps.title = "ราคาวัตถุดิบ NEW"
            ps.append(["SUPPLIER", "รหัส", "รายละเอียด", "น้ำหนัก", "USD", "THB/t", "CNY", "THB/t", "ราคาบาท/กรัม"])
            ps.append([None] * 9)
            ps.append([None, "MAT01", "test", 1_000_000, None, None, None, None, 0.05])
            cost_path = td / "resin.xlsx"; cost.save(cost_path)
            rows = material_exposure(stock_path, [("Resin", cost_path)])
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["Gap vs on hand (g)"], 600)
            self.assertEqual(rows[0]["Workbook shortage (g)"], 500)
            self.assertEqual(rows[0]["Inbound waiting (g)"], 300)
            self.assertEqual(rows[0]["Lab hold (g)"], 100)
            self.assertAlmostEqual(rows[0]["Costed workbook gap (THB)"], 25)

    def test_replacement_cost_diagnostic_maps_wo_and_flags_formula_and_qty(self):
        with TemporaryDirectory() as td:
            td = Path(td)
            repl = Workbook(); summary = repl.active; summary.title = "สรุปต้นทุนการผลิต"
            summary.cell(6, 3, 2); summary.cell(6, 4, 10)
            s = repl.create_sheet("SAINT-GOBAIN")
            headers = ["WO", "Spec", "GW", "Reject", "Raw", "Bond"] + [None] * 4 + ["Mat"] + [None] * 8
            s.append(headers); s.append([None] * 19)
            s.cell(2, 12, 1); s.cell(2, 13, 2); s.cell(2, 14, 3); s.cell(2, 15, 4); s.cell(2, 16, 5); s.cell(2, 17, 6)
            s.cell(3, 1, "P001-010126"); s.cell(3, 2, "sample"); s.cell(3, 3, 2); s.cell(3, 4, 2); s.cell(3, 5, 10); s.cell(3, 6, 5)
            s.cell(3, 11, 20); s.cell(3, 18, 30); s.cell(3, 19, 60)
            for c in range(12, 18): s.cell(3, c, 1)
            s.cell(3, 11, "=E3*C3")
            rp = td / "replacement.xlsx"; repl.save(rp)
            plan = Workbook(); p = plan.active; p.title = "แผนการเผา"
            p.cell(3, 1, "ProductionCode"); p.cell(3, 164, "REJECT")
            p.cell(4, 1, "P001-010126"); p.cell(4, 164, 1)
            pp = td / "plan.xlsx"; plan.save(pp)
            result = replacement_diagnostics(rp, pp)
            self.assertEqual(result["wo_plan_matches"], 1)
            self.assertEqual(result["quantity_mismatches"], 1)
            self.assertEqual(result["material_formula_issue_rows"], 1)
            self.assertEqual(result["reported_rejects"], 2)
            self.assertAlmostEqual(result["diagnostic_cost"], 2 * (2 * (0.8 * 10 + 0.2 * 5) + 2 * 21))


if __name__ == "__main__":
    unittest.main()
