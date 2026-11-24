"""Optional legacy verification states stay compatible; strict input errors are structured."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ui_delivery import validate

class ModalPlanNullTests(unittest.TestCase):
    def test_missing_and_null_verification_states_do_not_raise_in_legacy_mode(self):
        for fields in [{},{'verification_states':None}]:
            with self.subTest(fields=fields):
                result=validate(Path.cwd(),{'schema_version':2,'units':[],**fields})
                codes={row['code'] for row in result['validation']['errors']}
                self.assertNotIn('verification_states_invalid',codes)
                self.assertNotIn('runtime_verification_states_missing',codes)

    def test_missing_null_and_non_list_have_structured_strict_errors(self):
        for fields in [{},{'verification_states':None},{'verification_states':12},
                       {'verification_states':'bad'},{'verification_states':{}}]:
            with self.subTest(fields=fields):
                result=validate(Path.cwd(),{'schema_version':2,'units':[],**fields},require_runtime_plan=True)
                self.assertIn('runtime_verification_states_missing',{row['code'] for row in result['validation']['errors']})

    def test_non_list_legacy_input_reports_type_error_without_iteration(self):
        for value in [False,42,'not-a-list',{}]:
            result=validate(Path.cwd(),{'schema_version':2,'units':[],'verification_states':value})
            self.assertIn('verification_states_invalid',{row['code'] for row in result['validation']['errors']})

if __name__=='__main__':unittest.main()
