import unittest
import pandas as pd
from suite.daily_capacity_view import collapse_capacities, capacity_validation


class DailyCapacityViewTests(unittest.TestCase):
    def test_collapse_preserves_pcs_capacity_and_mixing_mill_values(self):
        src=pd.DataFrame([
            {'Plan Date':'2026-10-22','Section':'Forming','Plan pcs':80,'Capacity pcs':100,'Plan ton':0,'Capacity ton':0,'Mixing Plan MO':None,'Mixing Capacity MO':None},
            {'Plan Date':'2026-10-22','Section':'Mixing','Plan pcs':0,'Capacity pcs':0,'Plan ton':0,'Capacity ton':0,'Mixing Plan MO':4,'Mixing Capacity MO':5},
        ])
        out=collapse_capacities(src)
        forming=out[out.Section.eq('Forming')].iloc[0]
        mixing=out[out.Section.eq('Mixing')].iloc[0]
        self.assertEqual(forming['Capacity pcs'],100)
        self.assertEqual(mixing['Mixing Plan MO'],4)
        self.assertEqual(mixing['Mixing Capacity MO'],5)

    def test_capacity_graph_basis_uses_pcs_when_tonnage_unavailable(self):
        plan=pd.DataFrame([{'Plan Date':'2026-10-22','Section':'Forming','Plan Qty':80,'Plan ton':0}])
        caps=pd.DataFrame([{'Plan Date':'2026-10-22','Section':'Forming','Capacity pcs':100,'Capacity ton':0}])
        out=capacity_validation(plan,caps).iloc[0]
        self.assertEqual(out['Basis'],'pcs')
        self.assertEqual(out['Load %'],80)
        self.assertEqual(out['Result'],'PASS')


if __name__ == '__main__':
    unittest.main()
