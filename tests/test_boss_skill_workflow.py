"""Verify isolated workflow revisions without changing historical acceptance tools."""
import ast
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import boss_skill_expansion as expansion
import boss_skill_workflow as workflow


class SkillWorkflowTests(unittest.TestCase):
    def test_three_workflows_reproduce_and_verify_without_starting_game(self):
        names=set()
        for identifier in ('057_wanjun','073_yanqiansui','056_youlong'):
            target=workflow.build(expansion.build(identifier))
            self.assertEqual(workflow.build(expansion.build(identifier)),target)
            receipt=workflow.verify(target)
            self.assertEqual(receipt['id'],identifier)
            self.assertFalse(receipt['playable'])
            self.assertFalse(receipt['game_started'])
            names.add(target.name)
        self.assertEqual(len(names),3)

    def test_generated_sources_use_exact_expansion_gate(self):
        files=workflow.render()
        for name,data in files.items():
            ast.parse(data.decode('utf-8'),filename=name)
        gate=files['boss_candidate_gate.py'].decode('utf-8')
        self.assertIn('from boss_skill_expansion import validate as verify',gate)
        self.assertIn('if bundle is None:raise RuntimeError',gate)
        collector=files['collect_boss_candidate_acceptance.py'].decode('utf-8')
        self.assertIn('from boss_skill_expansion import validate',collector)
        for name in ('ahua_practice.py','run_control_lifecycle_probe.py'):
            self.assertIn("choices=('057_wanjun','073_yanqiansui','056_youlong')",files[name].decode('utf-8'))

    def test_historical_workflow_is_not_changed(self):
        workflow.render()
        for name,digest in workflow.previous.FROZEN.items():
            self.assertEqual(workflow.sha(workflow.ROOT/'tools'/name),digest)

    def test_generated_gate_rejects_no_bundle_and_checks_requested_boss(self):
        namespace={};exec(workflow.render()['boss_candidate_gate.py'],namespace)
        with self.assertRaises(RuntimeError):namespace['validate']('057_wanjun')
        with patch.object(expansion,'validate',return_value={'verified':True}) as verify:
            bundle=Path('exact-bundle')
            self.assertEqual(namespace['validate']('073_yanqiansui',bundle=bundle),{'verified':True})
            verify.assert_called_once_with('073_yanqiansui',bundle,root=workflow.ROOT)

    def test_workflow_content_edits_are_rejected(self):
        target=workflow.build(expansion.build('056_youlong'))
        original=Path.read_bytes
        def altered(path):
            data=original(path)
            return data+b'\n# altered\n' if path==target/'boss_candidate_gate.py' else data
        with patch.object(Path,'read_bytes',altered):
            with self.assertRaises(AssertionError):workflow.verify(target)

    def test_manifest_cannot_claim_player_release(self):
        target=workflow.build(expansion.build('057_wanjun'))
        original=expansion.read
        def altered(path):
            data=original(path)
            if Path(path)==target/'manifest.json':data=dict(data,playable=True)
            return data
        with patch.object(expansion,'read',side_effect=altered):
            with self.assertRaises(AssertionError):workflow.verify(target)


if __name__=='__main__':unittest.main()
