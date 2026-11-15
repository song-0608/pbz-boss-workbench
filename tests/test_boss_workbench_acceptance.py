"""Check acceptance against preserved real actions and regressions of duplicate callbacks."""
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from collect_boss_workbench_acceptance import proof


class WorkbenchAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=ROOT/'evidence/official-validation/20261115-094534/boss-workbench-runtime-actions.json'
        actions=json.loads(path.read_text(encoding='utf-8'))
        cls.segment='\n'.join(actions['lines'])

    def test_actual_completed_interactions(self):
        self.assertTrue(proof(self.segment)['passed'])

    def test_repeated_release_callback_is_rejected(self):
        changed=self.segment+'\n[PBZBossControl] workbench_close success=true state=OFF reason=\n'
        self.assertFalse(proof(changed)['passed'])

    def test_unretired_input_layer_is_rejected(self):
        changed=self.segment.replace('WORKBENCH_INPUT_RESTORED=true','REMOVED',1)
        self.assertFalse(proof(changed)['passed'])

    def test_escape_leaking_to_original_menu_is_rejected(self):
        self.assertFalse(proof(self.segment+'\npause menu opened\n')['passed'])


if __name__=='__main__':unittest.main()
