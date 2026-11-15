import ast
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import youlong_developer_workflow as workflow


class WorkflowTests(unittest.TestCase):
    def test_rendered_revision_retains_gates_and_routes_nested_steps(self):
        files=workflow.render()
        for name,data in files.items():ast.parse(data.decode('utf-8'),filename=name)
        practice=files['ahua_practice.py'].decode('utf-8')
        self.assertIn('from boss_adaptation_workflow import ROOT',practice)
        self.assertIn('Path(__file__).with_name(name)',practice)
        self.assertIn("choices=('056_youlong',)",practice)
        self.assertIn("lease_minutes=20",practice)
        self.assertIn("time.time() >= state['deadline_unix']",practice)
        runner=files['run_control_lifecycle_probe.py'].decode('utf-8')
        for required in ("c.baseline.formal_files()!=s['formal_before']",'v.verify_build',
            'Candidate cannot inherit Ahua developer or player acceptance','issue_expiry',
            "time.time()>s['deadline_unix']-120"):
            self.assertIn(required,runner)
        milestone=files['run_boss_candidate_milestone.py'].decode('utf-8')
        self.assertIn("Path(__file__).with_name('test_player_skill_batch.py')",milestone)
        self.assertIn("ready+600",milestone)

    def test_gate_refuses_missing_bundle_or_wrong_boss_without_game_calls(self):
        scope={};exec(workflow.render()['boss_candidate_gate.py'],scope)
        for identifier,bundle in (('056_youlong',None),('073_yanqiansui','unused'),('ahua_guitoudao','unused')):
            with self.subTest(identifier=identifier),self.assertRaises(RuntimeError):scope['validate'](identifier,bundle=bundle)

    def test_historical_source_change_is_refused(self):
        with tempfile.TemporaryDirectory()as temp:
            root=Path(temp);(root/'tools').mkdir()
            for n in workflow.FROZEN:(root/'tools'/n).write_bytes(b'changed')
            with self.assertRaises(AssertionError):workflow.render(root)

    def test_generated_payload_or_extra_file_is_refused(self):
        import json
        for mode in ('payload','extra','manifest'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory()as temp:
                root=Path(temp);target=root/'runtime/developer-workflows/youlong-fixture'
                target.mkdir(parents=True);bundle=root/'bundle';bundle.mkdir()
                manifest={'bundle':str(bundle)};files={'entry.py':b'pass\n'}
                (target/'manifest.json').write_text(json.dumps(manifest))
                (target/'entry.py').write_bytes(files['entry.py'])
                with patch.object(workflow,'expected',return_value=(manifest,files,'fixture')):
                    workflow.verify(target,root)
                    if mode=='payload':(target/'entry.py').write_bytes(b'changed')
                    elif mode=='extra':(target/'extra.py').write_bytes(b'pass')
                    else:(target/'manifest.json').write_text(json.dumps(dict(manifest,playable=True)))
                    with self.assertRaises(AssertionError):workflow.verify(target,root)


if __name__=='__main__':unittest.main()
