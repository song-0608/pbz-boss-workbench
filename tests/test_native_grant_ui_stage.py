"""Exercise staging boundaries without a game, Windows input or native writes."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import native_grant_ui_stage as flow
import ahua_practice as practice
import official_validation as validation
import research_storage


class StageTests(unittest.TestCase):
    def test_render_removes_input_and_preserves_native_and_cleanup_checks(self):
        files = flow.render()
        self.assertEqual(set(files), {'stage_candidate.py', 'boss_candidate_gate.py'})
        runner = files['stage_candidate.py'].decode('utf-8')
        for data in files.values(): ast.parse(data.decode('utf-8'))
        self.assertNotIn('research_game_menu', runner)
        self.assertNotIn('menu.click', runner)
        for token in ('v.verify_build', "c.baseline.formal_files()!=s['formal_before']",
                      'issue_expiry', "time.time()>s['deadline_unix']-120",
                      'Fresh remote native contract required', 'Current combat declarations required',
                      'Camera parameter contract mismatch', 'Fresh player protection declarations required',
                      'arena_contract.validate', 'player_ui_contract.validate',
                      'Previous lifecycle cleanup not confirmed', 'controller.begin_stage',
                      'controller.finish_stage', 'preserve linked module path'):
            self.assertIn(token, runner)
        # The generated entry point fixes the complete protected options and
        # replaces caller arguments rather than exposing Ahua/death modes.
        self.assertIn("sys.argv = [__file__, *controller.OPTIONS", runner)
        self.assertIn('--performance-profile', flow.OPTIONS)
        self.assertNotIn('--player-entry', flow.OPTIONS)
        self.assertNotIn('--death-trial', flow.OPTIONS)

    def test_idle_guard_rejects_prior_control_network_expiry_and_other_owner(self):
        owner = dict(state_file='owned', phase='game_launched')
        state = dict(state_file='owned', readonly_ai_experiment=True, readonly_hot_reload_enabled=True,
            ue4ss_deployed=True, offline_validation=True, deadline_unix=1000)
        flow.idle_guard(owner, state, 0)
        for change in (dict(boss_lifecycle_experiment=True), dict(restored=True), dict(network_active=True),
                       dict(readonly_ai_experiment=False), dict(readonly_hot_reload_enabled=False),
                       dict(ue4ss_deployed=False), dict(offline_validation=False), dict(deadline_unix=180)):
            with self.subTest(change=change), self.assertRaises(AssertionError):
                flow.idle_guard(owner, dict(state, **change), 0)
        for change in (dict(phase='armed'), dict(state_file='foreign')):
            with self.assertRaises(AssertionError): flow.idle_guard(dict(owner, **change), state, 0)

    def test_mirror_rejects_outside_duplicate_and_missing_carrier(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            carrier = root / 'Mods/PBZObserveAI/Scripts/main.lua'
            state = dict(ue4ss_loader_manifest=[dict(physical_path=str(carrier))])
            self.assertEqual(flow.mirror_guard(state, root), carrier)
            for rows in ([], state['ue4ss_loader_manifest'] * 2,
                         [dict(physical_path=str(root.parent / 'formal.lua'))],
                         [dict(physical_path=str(root / 'other.lua'))]):
                with self.assertRaises(AssertionError):
                    flow.mirror_guard(dict(ue4ss_loader_manifest=rows), root)

    def fixture(self, root):
        def save(path, data):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data), encoding='utf-8')
        session = '20261118-210000'
        work = root / 'evidence/official-validation' / session; work.mkdir(parents=True)
        stage_flow = root / 'runtime/developer-workflows/fixture'; stage_flow.mkdir(parents=True)
        (stage_flow / 'manifest.json').write_bytes(b'{}')
        target = root / 'research/bundle'; target.mkdir(parents=True)
        pool = ['Class.One_C', 'Class.Two_C']
        save(target / 'manifest.json', dict(base_mod_files={'Scripts/base.lua': 'base'},
            overrides={'Scripts/boss_candidate.lua': 'candidate'}, definition={'ability_pool': pool}))
        grant = dict(boss_candidate='071_xianzhe', developer_bundle_sha256='frozen')
        manifest = dict(id='071_xianzhe', bundle=str(target), parent_workflow_manifest={'candidate_grant': grant})
        carrier = root / 'mirror/Mods/PBZObserveAI/Scripts/main.lua'
        carrier.parent.mkdir(parents=True); carrier.write_bytes(b'-- staged\n')
        log = root / 'mirror/UE4SS.log'; log.write_bytes(b'old log\n')
        state = dict(state_file=str(root / 'runtime' / ('official-validation-' + session) / 'state.json'),
            work=str(work), readonly_ai_experiment=True, readonly_hot_reload_enabled=True,
            offline_validation=True, ue4ss_deployed=True, deadline_unix=1000,
            control_probe_expires_at=800, formal_before={'unchanged': True},
            ue4ss_loader_manifest=[dict(physical_path=str(carrier), sha256=flow.sha(carrier))])
        owner = dict(state_file=state['state_file'], phase='game_launched')
        research_pid = 42
        deployment = dict(boss_candidate=manifest['id'], player_entry=False, developer_bundle=str(target),
            candidate_identity_grant=grant, grant=dict(grant, isolated=True, offline=True,
                exe_sha256=flow.bundle.BUILD, session_id='official-validation-' + session, expires_at=800),
            module_source_sha256={'base.lua': 'base', 'boss_candidate.lua': 'candidate'},
            arena_navigation_trial=True, performance_profile=True)
        for key in ('skill_lab', 'expanded', 'player_key_trial', 'combo_scheduler_trial', 'death_trial',
                    'native_death_trial', 'active_skill_death_trial', 'active_skill_disposal_trial',
                    'incoming_combat_trial', 'scene_transition_trial'): deployment[key] = False
        return locals()

    def patches(self, f):
        from contextlib import ExitStack
        stack = ExitStack()
        stack.enter_context(patch.object(flow, 'ROOT', f['root']))
        stack.enter_context(patch.object(flow, 'verify', return_value=f['manifest']))
        stack.enter_context(patch.object(practice, 'owned_session', side_effect=lambda: (f['owner'], f['state'])))
        stack.enter_context(patch.object(practice, 'log_path', return_value=f['log']))
        stack.enter_context(patch.object(research_storage, 'container_path', return_value=f['root'] / 'mirror'))
        stack.enter_context(patch.object(validation, 'verify_build'))
        stack.enter_context(patch.object(validation.c.baseline, 'formal_files', return_value={'unchanged': True}))
        stack.enter_context(patch.object(flow.time, 'time', return_value=100))
        stack.enter_context(patch.object(flow, 'research_pid', side_effect=lambda _: f['research_pid']))
        return stack

    def staged(self, f):
        context = flow.begin_stage(f['stage_flow'])
        f['state']['boss_lifecycle_experiment'] = True
        f['state']['readonly_ai_experiment'] = False
        f['save'](f['work'] / 'control-lifecycle-deployment.json', f['deployment'])
        f['save'](f['work'] / 'control-lifecycle-deployment-1.json', f['deployment'])
        flow.finish_stage(f['stage_flow'], context)
        return context

    def test_deployment_rejects_wrong_modules_role_scope_session_and_refreshed_grant(self):
        with tempfile.TemporaryDirectory() as directory:
            f = self.fixture(Path(directory).resolve())
            flow.deployment_guard(f['deployment'], f['manifest'], f['state'], 100)
            for mode in ('role', 'module', 'scope', 'session', 'expiry', 'network', 'bundle', 'grant'):
                data = copy.deepcopy(f['deployment'])
                if mode == 'role': data['boss_candidate'] = '067_motian'
                elif mode == 'module': data['module_source_sha256']['base.lua'] = 'changed'
                elif mode == 'scope': data['death_trial'] = True
                elif mode == 'session': data['grant']['session_id'] = 'other'
                elif mode == 'expiry': data['grant']['expires_at'] = 1100
                elif mode == 'network': data['grant']['offline'] = False
                elif mode == 'bundle': data['developer_bundle'] += '-other'
                else: data['grant']['developer_bundle_sha256'] = 'changed'
                with self.subTest(mode=mode), self.assertRaises(AssertionError):
                    flow.deployment_guard(data, f['manifest'], f['state'], 100)
            with self.assertRaises(AssertionError):
                flow.deployment_guard(f['deployment'], f['manifest'], f['state'], 800)

    def test_stage_saves_intent_before_mutation_and_cannot_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            f = self.fixture(Path(directory).resolve())
            with self.patches(f):
                context = flow.begin_stage(f['stage_flow'])
                self.assertFalse(context['ui_input_sent'])
                self.assertFalse(context['staged'])
                self.assertEqual(f['carrier'].read_bytes(), b'-- staged\n')
                with self.assertRaises(AssertionError): flow.begin_stage(f['stage_flow'])
                self.assertEqual(flow.bundle.read(f['work'] / (flow.LABEL + '-intent.json')), context)

    def test_staged_snapshot_rejects_changed_carrier_deployment_expiry_and_log_prefix(self):
        for mode in ('carrier', 'archive', 'current', 'lease', 'log', 'owner', 'process'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                f = self.fixture(Path(directory).resolve())
                with self.patches(f):
                    self.staged(f)
                    flow.staged_guard(f['stage_flow'])
                    if mode == 'carrier': f['carrier'].write_bytes(b'changed')
                    elif mode == 'archive': (f['work'] / 'control-lifecycle-deployment-1.json').write_bytes(b'{}')
                    elif mode == 'current': f['save'](f['work'] / 'control-lifecycle-deployment.json', {})
                    elif mode == 'lease': f['state']['deadline_unix'] = 1200
                    elif mode == 'log': f['log'].write_bytes(b'changed prefix\n')
                    elif mode == 'owner': f['owner']['phase'] = 'armed'
                    else: f['research_pid'] = 99
                    with self.assertRaises(AssertionError): flow.staged_guard(f['stage_flow'])

    def test_reload_gate_requires_focus_and_never_sends_or_refreshes_input(self):
        with tempfile.TemporaryDirectory() as directory:
            f = self.fixture(Path(directory).resolve())
            with self.patches(f):
                self.staged(f)
                with patch.object(flow, 'foreground_window', side_effect=AssertionError('unfocused')):
                    with self.assertRaises(AssertionError): flow.reload_gate(f['stage_flow'])
                self.assertFalse(list(f['work'].glob(flow.LABEL + '-gate-*')))
                with patch.object(flow, 'foreground_window', return_value=123):
                    result = flow.reload_gate(f['stage_flow'])
                    self.assertEqual(result['window_id'], 123)
                    self.assertEqual(result['gate_expires_at'], 110)
                    self.assertEqual(result['key'], 'Control_L+r')
                    self.assertFalse(result['input_sent'])
                    self.assertEqual(f['state']['control_probe_expires_at'], 800)
                    f['log'].write_bytes(f['log'].read_bytes() + b'PBZ_CONTROL_LIFECYCLE:START=attempt\n')
                    with self.assertRaises(AssertionError): flow.reload_gate(f['stage_flow'])

    def test_capture_reports_missing_grants_without_claiming_skill_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            f = self.fixture(Path(directory).resolve())
            with self.patches(f):
                self.staged(f)
                f['log'].write_bytes(f['log'].read_bytes() + (
                    'PBZ_CONTROL_LIFECYCLE:CANDIDATE_IDENTITY_READY=071_xianzhe|class|config\n'
                    'PBZ_CONTROL_LIFECYCLE:CANDIDATE_LIVE_BINDING=071_xianzhe|skill_01|Class.One_C\n'
                    'PBZ_CONTROL_LIFECYCLE:INTERACTIVE_READY=true\n').encode())
                result = flow.capture(f['stage_flow'])
                self.assertEqual(result['missing_native_grants'], ['Class.Two_C'])
                for key in ('playable', 'activation_verified', 'damage_verified', 'restoration_verified'):
                    self.assertFalse(result[key])
                self.assertEqual(f['owner']['phase'], 'game_launched')
                with self.assertRaises(AssertionError): flow.capture(f['stage_flow'])

    def test_capture_rejects_incomplete_duplicate_foreign_and_failed_assemblies(self):
        for mode in ('incomplete', 'duplicate', 'foreign', 'fault'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                f = self.fixture(Path(directory).resolve())
                with self.patches(f):
                    self.staged(f)
                    text = ('PBZ_CONTROL_LIFECYCLE:CANDIDATE_IDENTITY_READY=071_xianzhe|class|config\n'
                            'PBZ_CONTROL_LIFECYCLE:CANDIDATE_LIVE_BINDING=071_xianzhe|skill_01|Class.One_C\n'
                            'PBZ_CONTROL_LIFECYCLE:INTERACTIVE_READY=true\n')
                    if mode == 'incomplete': text = text.replace('INTERACTIVE_READY=', 'NOT_READY=')
                    elif mode == 'duplicate': text *= 2
                    elif mode == 'foreign': text = text.replace('Class.One_C', 'Foreign.C')
                    else: text += 'state=FAULTED\n'
                    f['log'].write_bytes(f['log'].read_bytes() + text.encode())
                    with self.assertRaises(AssertionError): flow.capture(f['stage_flow'])
                    self.assertFalse((f['work'] / (flow.LABEL + '-capture.json')).exists())

    def test_build_and_verify_reject_changed_generated_script(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            target = root / 'bundle'; target.mkdir(); (target / 'manifest.json').write_bytes(b'{}')
            # Keep the filesystem verification real; substitute only the
            # independently tested parent bundle and rendering inputs.
            manifest = dict(id='071_xianzhe', bundle=str(target))
            files = {'stage_candidate.py': b'# no input\n'}
            name = 'native-grant-ui-fixture'
            with patch.object(flow, 'expected', return_value=(manifest, files, name)):
                output = flow.build(target, root)
                self.assertEqual(output, flow.build(target, root))
                (output / 'stage_candidate.py').write_bytes(b'changed')
                with self.assertRaises(AssertionError): flow.verify(output, root)


if __name__ == '__main__': unittest.main()
