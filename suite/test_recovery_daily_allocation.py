import unittest

import pandas as pd

from suite.recovery_actions import build_recovery_daily_allocation


class RecoveryDailyAllocationTests(unittest.TestCase):
    def setUp(self):
        self.master = pd.DataFrame([{
            'Work Order': 'BO-001', 'Due Date': '2026-10-08',
            'Overall Closed': False, '_open_qty': 100,
            'Product Code': 'P123', 'Category': 'P', 'Customer': 'Customer A',
        }])
        self.risk = pd.DataFrame([{
            'Work Order': 'BO-001', 'Delivery Risk': 'HIGH',
            'Bottleneck Process': 'Forming', 'Current Status / WIP': 'Forming',
        }])
        self.schedule = pd.DataFrame([
            {'Work Order': 'BO-001', 'Section': 'Forming', 'Plan Date': '2026-10-06', 'Plan Qty': 100},
            {'Work Order': 'BO-001', 'Section': 'Packing', 'Plan Date': '2026-10-07', 'Plan Qty': 100},
        ])

    def test_reconciles_backorder_inside_existing_daily_plan_and_capacity(self):
        capacity = pd.DataFrame([
            {'Section': 'Forming', 'Plan Date': '2026-10-06', 'Plan ton': 2, 'Capacity ton': 4,
             'Utilization %': 50, 'Reason / Limiting Factor': 'Matched forming resource'},
            {'Section': 'Packing', 'Plan Date': '2026-10-07', 'Plan ton': 2, 'Capacity ton': 3,
             'Utilization %': 66.7, 'Reason / Limiting Factor': 'Matched packing resource'},
        ])
        summary, detail = build_recovery_daily_allocation(self.master, self.risk, self.schedule, capacity, '2026-10-06')
        row = summary.iloc[0]
        self.assertEqual(row['Plan Coverage %'], 100)
        self.assertTrue(str(row['Due Date Result']).startswith('ON TIME'))
        self.assertTrue(str(row['Capacity Result']).startswith('ALL SCHEDULED'))
        self.assertIn('no duplicate', row['Daily Plan Treatment'])
        self.assertEqual(len(detail), 2)

    def test_over_capacity_and_late_finish_are_explicit(self):
        capacity = pd.DataFrame([
            {'Section': 'Forming', 'Plan Date': '2026-10-06', 'Plan ton': 5, 'Capacity ton': 4,
             'Utilization %': 125},
            {'Section': 'Packing', 'Plan Date': '2026-10-10', 'Plan ton': 2, 'Capacity ton': 3,
             'Utilization %': 66.7},
        ])
        self.schedule.loc[self.schedule['Section'].eq('Packing'), 'Plan Date'] = '2026-10-10'
        summary, _ = build_recovery_daily_allocation(self.master, self.risk, self.schedule, capacity, '2026-10-06')
        row = summary.iloc[0]
        self.assertIn('HARD GATE', row['Capacity Result'])
        self.assertIn('LATE', row['Due Date Result'])

    def test_absent_schedule_is_not_claimed_feasible(self):
        summary, detail = build_recovery_daily_allocation(self.master, self.risk, pd.DataFrame(), pd.DataFrame(), '2026-10-06')
        self.assertIn('NOT SCHEDULED', summary.iloc[0]['Due Date Result'])
        self.assertTrue(detail.empty)

    def test_partial_packing_allocation_is_not_treated_as_fully_recovered(self):
        capacity = pd.DataFrame([
            {'Section': 'Forming', 'Plan Date': '2026-10-06', 'Plan ton': 2, 'Capacity ton': 4, 'Utilization %': 50},
            {'Section': 'Packing', 'Plan Date': '2026-10-07', 'Plan ton': 1.6, 'Capacity ton': 3, 'Utilization %': 53.3},
        ])
        self.schedule.loc[self.schedule['Section'].eq('Packing'), 'Plan Qty'] = 80
        summary, _ = build_recovery_daily_allocation(self.master, self.risk, self.schedule, capacity, '2026-10-06')
        self.assertEqual(summary.iloc[0]['Plan Coverage %'], 80)
        self.assertIn('INCOMPLETE', summary.iloc[0]['Due Date Result'])

    def test_exposes_recovery_share_and_capacity_headroom_without_double_loading(self):
        schedule = pd.DataFrame([{
            'Work Order':'BO-001','Section':'Forming','Plan Date':'2026-10-06',
            'Plan Qty':100,'Plan ton':0.10,
        }])
        capacity = pd.DataFrame([{
            'Section':'Forming','Plan Date':'2026-10-06','Plan pcs':300,
            'Plan ton':0.30,'Capacity ton':0.50,'Utilization %':60,
        }])
        _, detail = build_recovery_daily_allocation(
            self.master, self.risk, schedule, capacity, '2026-10-06')
        row = detail.iloc[0]
        self.assertAlmostEqual(row['Recovery allocation ton this day/section'], 0.10)
        self.assertAlmostEqual(row['Whole-day plan ton (includes listed recovery WOs)'], 0.30)
        self.assertAlmostEqual(row['Implied headroom before listed recovery ton'], 0.30)
        self.assertAlmostEqual(row['Headroom after current plan ton'], 0.20)


if __name__ == '__main__':
    unittest.main()
