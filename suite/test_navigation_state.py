import unittest

import pandas as pd

from suite.navigation_state import preserve_navigation_values, restore_editor_draft, save_editor_draft


class NavigationStateTests(unittest.TestCase):
    def test_safe_input_values_restore_but_passwords_do_not(self):
        state = {'search_wo': 'P005-110826', 'password': 'secret', 'capacity': 5}
        preserve_navigation_values(state)
        state.pop('search_wo')
        state.pop('capacity')
        state.pop('password')
        preserve_navigation_values(state)
        self.assertEqual(state['search_wo'], 'P005-110826')
        self.assertEqual(state['capacity'], 5)
        self.assertNotIn('password', state)

    def test_editor_draft_restores_only_for_unchanged_source(self):
        state = {}
        source = pd.DataFrame([{'Work Order': 'WO-1', 'Qty': 10}])
        edited = pd.DataFrame([{'Work Order': 'WO-1', 'Qty': 8}])
        save_editor_draft(state, 'qty_editor', source, edited)
        restored = restore_editor_draft(state, 'qty_editor', source)
        self.assertEqual(int(restored.iloc[0]['Qty']), 8)
        new_source = pd.DataFrame([{'Work Order': 'WO-1', 'Qty': 12}])
        self.assertIsNone(restore_editor_draft(state, 'qty_editor', new_source))


if __name__ == '__main__':
    unittest.main()
