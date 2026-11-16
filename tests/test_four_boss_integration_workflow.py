import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import four_boss_integration_workflow as workflow
from mod_installation import validate_package


class IntegrationWorkflowTests(unittest.TestCase):
    def test_exact_candidate_and_old_eight_skills_reparsed(self):
        root=workflow.ROOT/'runtime/release-candidates'/workflow.CANDIDATE
        current=workflow.modules(validate_package(root))
        proofs,sources=workflow.verify_current(current)
        self.assertEqual(len(proofs),8);self.assertEqual(len(sources),2)
        for name in ('owned_arena.lua','ue_host.lua','profiles/youlong.lua'):
            changed=dict(current);changed[name]='0'*64
            with self.subTest(name=name),self.assertRaises(AssertionError):workflow.verify_current(changed)

    def test_versioned_settings_and_skill_tool_keep_originals(self):
        files=workflow.render()
        settings={};exec(compile(files['player_settings.py'],'versioned-settings','exec'),settings)
        self.assertEqual(settings['editor_skill_labels']('056_youlong')['skill_02'],'游龙左闪攻击')
        self.assertEqual(len(settings['BOSSES']),4)
        self.assertIn('sys.dont_write_bytecode=True',files['test_player_skill_batch.py'].decode())
        for name,digest in workflow.FROZEN.items():self.assertEqual(workflow.sha(workflow.ROOT/'tools'/name),digest)

    def test_frozen_source_change_refused(self):
        with patch.dict(workflow.FROZEN,{'player_settings.py':'0'*64}):
            with self.assertRaises(AssertionError):workflow.render()


if __name__=='__main__':unittest.main()
