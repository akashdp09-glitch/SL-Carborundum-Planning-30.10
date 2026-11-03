import unittest
import pandas as pd
from suite.recovery_product_review import recovery_unique_orders


class RecoveryUniqueOrderTests(unittest.TestCase):
    def test_distinct_wo_rollup_keeps_conflict_and_reason_evidence(self):
        source = pd.DataFrame([
            {"Fac No": "WO-1", "_key": "WO1", "Recovery Source Row": 4, "Recovery Result": "ตกแผน",
             "Wip": 10, "QTY": 20, "Recovery reason (source)": "รอแกน KVT", "Recovery note (source)": "NCR"},
            {"Fac No": "WO-1", "_key": "WO1", "Recovery Source Row": 5, "Recovery Result": "ตามแผน",
             "Wip": 8, "QTY": 20, "Recovery reason (source)": "รอแกน KVT", "Recovery note (source)": "NCR"},
            {"Fac No": "WO-2", "_key": "WO2", "Recovery Source Row": 6, "Recovery Result": "ตามแผน",
             "Wip": 3, "QTY": 6, "Recovery reason (source)": "", "Recovery note (source)": ""},
        ])
        result = recovery_unique_orders(source).set_index("_key")
        self.assertEqual(len(result), 2)
        self.assertTrue(result.loc["WO1", "Recovery status (source)"].startswith("CONFLICT"))
        self.assertAlmostEqual(result.loc["WO1", "Recovery source WIP (unit not specified)"], 10)
        self.assertIn("รอแกน KVT", result.loc["WO1", "Recovery reason / note"])
        self.assertEqual(result.loc["WO2", "Recovery reason / note"], "No reason recorded in source")


if __name__ == "__main__":
    unittest.main()
