import ast
import copy
import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import prepare_boss_native_combo_workflow as workflow
from tests.test_boss_native_combo_candidate import fixture


class NativeComboWorkflowTests(unittest.TestCase):
    def test_generated_controller_preserves_stage_input_and_cleanup_gates(self):
        files=workflow.render()
        self.assertEqual(set(files),{'stage_candidate.py','boss_candidate_gate.py','combo_ui_controller.py','combo_skill_gate.py'})
        for name,raw in files.items():ast.parse(raw.decode('utf-8'),filename=name)
        runner=files['stage_candidate.py'].decode('utf-8')
        self.assertIn("choices=('044_pengmeng',)",runner)
        self.assertIn('module_overrides.update(overrides(args.boss_candidate_bundle))',runner)
        self.assertNotIn('menu.click',runner)
        self.assertNotIn('import research_game_menu',runner)
        self.assertIn('import combo_ui_controller as controller',runner)
        controller=files['combo_ui_controller.py'].decode('utf-8')
        self.assertIn('import prepare_boss_native_combo_workflow as previous',controller)
        self.assertIn('expected_modules = previous.expected_modules(recorded)',controller)
        self.assertIn("kind='native_combo_ui_stage'",controller)
        self.assertIn("'native-combo-ui-' + parent['id']",controller)
        self.assertIn('idle_guard(owner, state, time.time())',controller)
        self.assertIn('exact foreground research window required',controller)
        self.assertIn('gate_expires_at',controller)
        gate=files['combo_skill_gate.py'].decode('utf-8')
        self.assertIn('import combo_ui_controller as flow',gate)
        self.assertIn('previous skill still active or unconfirmed',gate)
        self.assertIn("purpose == 'cast-cancel'",gate)
        self.assertIn('max_action_count=2',gate)
        self.assertIn('gate_expires_at=issued + 10',gate)
        self.assertIn("path.open('x', encoding='utf-8')",gate)
        self.assertNotIn('sky.press_key',gate)

    def test_four_overrides_are_checked_and_every_other_accepted_module_retained(self):
        report,characters=fixture();definition=workflow.bundle.select('044_pengmeng',report,characters)
        definition['dependency_report_sha256']='fixture'
        overrides=workflow.bundle.modules(definition)
        hashes={n:hashlib.sha256(raw).hexdigest() for n,raw in overrides.items()}
        record=dict(definition=definition,overrides=hashes,module_sha256=hashes['boss_candidate.lua'])
        modules=workflow.expected_modules(record)
        release=workflow.bundle.read(workflow.ROOT/'releases'/workflow.bundle.spawn.BASE/'pbz-release.json')
        prefix='PBZBossControl/Scripts/'
        for name,digest in modules.items():
            self.assertEqual(digest,hashes.get(name,release['files'][prefix+name]))
        bad=copy.deepcopy(record);bad['overrides']['combo_scheduler.lua']='changed'
        with self.assertRaises(AssertionError):workflow.expected_modules(bad)

    def test_sources_bind_adapter_tests_and_inherited_protected_workflow(self):
        sources=workflow.source_hashes()
        for name in (*workflow.SOURCES,*workflow.bundle.SOURCES):
            self.assertEqual(sources[name],workflow.sha(workflow.ROOT/name))
        self.assertIn('tools/native_grant_skill_gate.py',sources)
        self.assertIn('tools/boss_inventory_spawn_repair.py',sources)


if __name__=='__main__':unittest.main()
