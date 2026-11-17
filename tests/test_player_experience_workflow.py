import ast
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import player_experience_workflow as workflow
import player_keymap


class WorkflowTests(unittest.TestCase):
    def test_local_sources_parse_and_only_candidate_root_is_substituted(self):
        directory=workflow.ROOT/'runtime/release-candidates/example'
        files=workflow.render(directory)
        self.assertEqual(set(files),{'ahua_practice.py','run_control_lifecycle_probe.py',
            'player_settings.py','test_player_skill_batch.py','player_keymap.py'})
        for name,data in files.items():ast.parse(data.decode('utf-8'),filename=name)
        self.assertIn(b'candidate_mod_root',files['run_control_lifecycle_probe.py'])
        original=workflow.previous.render()['run_control_lifecycle_probe.py']
        replacement=(b'from player_experience_workflow import candidate_mod_root\n'
            +b'def active_mod_root():\n    return candidate_mod_root(Path('+repr(str(directory)).encode('utf-8')+b'))')
        self.assertEqual(files['run_control_lifecycle_probe.py'],original.replace(
            b'from mod_installation import active_mod_root',replacement))

    def test_legacy_keymap_gains_lock_without_mutating_input(self):
        source=workflow.render(workflow.ROOT/'runtime/release-candidates/example')['player_keymap.py']
        namespace={'__name__':'keymap_trial','__file__':'unused'}
        exec(compile(source,'keymap_trial','exec'),namespace)
        data=json.loads((workflow.ROOT/'玩家键位.json').read_text(encoding='utf-8-sig'))
        before=json.dumps(data,sort_keys=True)
        effective=namespace['effective'](data)
        self.assertEqual(effective['controls']['lock_target'],'MIDDLE_MOUSE_BUTTON')
        self.assertEqual(json.dumps(data,sort_keys=True),before)
        effective['controls']['lock_target']=effective['skills']['slot1']
        with self.assertRaisesRegex(ValueError,'重复按键'):namespace['validate'](effective)
        for key in ('W','INS','F11'):
            effective['controls']['lock_target']=key
            with self.assertRaises(ValueError):namespace['validate'](effective)


if __name__=='__main__':unittest.main()
