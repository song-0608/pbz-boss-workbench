import ast
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import boss_skill_player_workflow as workflow


class PlayerSkillWorkflowTests(unittest.TestCase):
    def test_render_preserves_historical_sources_and_registers_four_names(self):
        before={name:workflow.sha(workflow.ROOT/'tools'/name) for name in workflow.historical.FROZEN}
        files=workflow.render()
        self.assertEqual(set(files),{'player_settings.py','test_player_skill_batch.py',
            'ahua_practice.py','run_control_lifecycle_probe.py'})
        for name,data in files.items():ast.parse(data.decode('utf-8'),filename=name)
        self.assertIn("'056_youlong':'发狂的水行帮主：游龙'",files['player_settings.py'].decode('utf-8'))
        self.assertIn('Path(__file__).with_name(name)',files['ahua_practice.py'].decode('utf-8'))
        self.assertEqual(before,{name:workflow.sha(workflow.ROOT/'tools'/name) for name in before})


if __name__=='__main__':unittest.main()
