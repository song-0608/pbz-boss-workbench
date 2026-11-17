import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import build_expanded_boss_candidate as candidate
import expanded_boss_integration_workflow as workflow


class ExpandedBossIntegrationTests(unittest.TestCase):
    def addition(self):
        manifest = dict(id='071_xianzhe', display_name='弦儿', profile_module='profiles.xianzhe',
            bindings_module='profiles.xianzhe_bindings', base_control_accepted=True,
            playable=False, ordinary_switching_accepted=False, player_registry_modified=False,
            accepted_skills=['skill_01', 'heavy_01'])
        return manifest, {'xianzhe.lua': 'return {}\n', 'xianzhe_bindings.lua': 'return {}\n'}

    def test_overlay_keeps_experience_modules_and_adds_exact_profile(self):
        files = {candidate.PREFIX + 'boss_catalog.lua': b"local entries = {\n    {id='ahua_guitoudao'},\n}\nlocal bindings = {\n}\n",
                 candidate.PREFIX + 'player_target_lock.lua': b'unchanged lock',
                 candidate.PREFIX + 'input_driver.lua': b'unchanged movement'}
        result = candidate.overlay(files, [self.addition()])
        self.assertEqual(result[candidate.PREFIX + 'player_target_lock.lua'], b'unchanged lock')
        self.assertEqual(result[candidate.PREFIX + 'input_driver.lua'], b'unchanged movement')
        self.assertEqual(result[candidate.PREFIX + 'profiles/xianzhe.lua'], b'return {}\n')
        self.assertIn('弦儿', result[candidate.PREFIX + 'boss_catalog.lua'].decode())
        self.assertEqual(len(files), 3)

    def test_rejects_duplicate_or_premature_promotion(self):
        files = {candidate.PREFIX + 'boss_catalog.lua': b'local entries = {\n}\nlocal bindings = {\n}\n'}
        with self.assertRaises(AssertionError): candidate.overlay(files, [self.addition(), self.addition()])
        for field in ('playable', 'ordinary_switching_accepted', 'player_registry_modified'):
            addition = copy.deepcopy(self.addition()); addition[0][field] = True
            with self.subTest(field=field), self.assertRaises(AssertionError): candidate.overlay(files, [addition])

    def test_ordinary_workflow_changes_only_candidate_routing(self):
        target = candidate.ROOT / 'runtime/release-candidates/ahua-expanded-test'
        files = workflow.render(target, additions=[dict(id='071_xianzhe', display_name='弦儿',
            skill_labels={'slot1': '弦儿·技能05'})])
        source = files['run_control_lifecycle_probe.py'].decode()
        self.assertIn('from expanded_boss_integration_workflow import candidate_mod_root', source)
        self.assertIn(repr(str(target)), source)
        gate = files['player_experience_trial.py'].decode()
        for token in ('Research game must already be foreground', 'check_policy', 'formal_files()',
                      'gate_expires_at=time.time()+10', "min(state['deadline_unix']"):
            self.assertIn(token, gate)
        self.assertIn('from player_experience_trial import gate', files['test_player_experience_inputs.py'].decode())
        settings = files['player_settings.py'].decode()
        self.assertIn("BOSSES.update({'071_xianzhe': '弦儿'})", settings)
        self.assertIn('弦儿·技能05', settings)


if __name__ == '__main__': unittest.main()
