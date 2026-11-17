"""Aggregation must retain each closed session's exact deployment and input gate."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import collect_expanded_boss_player as collector


class ClosedSessionTests(unittest.TestCase):
    def historical_fixture(self, root):
        identifier = collector.experience_candidate.BASE
        base = root / 'releases' / identifier
        base.mkdir(parents=True)
        manifest = dict(release_id=identifier, status='release', runtime_acceptance_current=True)
        (base / collector.MANIFEST).write_text(json.dumps(manifest), encoding='utf-8')
        package = root / 'candidate'; package.mkdir()
        recorded = dict(experience_base_release=identifier,
            experience_base_manifest_sha256=collector.sha(base / collector.MANIFEST))
        (package / collector.MANIFEST).write_text(json.dumps(recorded), encoding='utf-8')
        return package, base, manifest

    def test_upgrade_replay_pins_original_base_and_restores_current_resolver(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); package, base, manifest = self.historical_fixture(root)
            original = collector.developer_bundle.active_mod_root
            with patch.object(collector, 'validate_package', return_value=manifest) as validated:
                with self.assertRaisesRegex(RuntimeError, 'replay stopped'):
                    with collector.historical_profile_base(package, root):
                        self.assertEqual(collector.developer_bundle.active_mod_root(root), base / 'PBZBossControl')
                        with self.assertRaises(AssertionError):
                            collector.developer_bundle.active_mod_root(root / 'other')
                        raise RuntimeError('replay stopped')
                validated.assert_called_once_with(base.resolve())
            self.assertIs(collector.developer_bundle.active_mod_root, original)

    def test_upgrade_replay_rejects_changed_historical_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); package, base, _ = self.historical_fixture(root)
            original = collector.developer_bundle.active_mod_root
            with (base / collector.MANIFEST).open('a', encoding='utf-8') as stream:
                stream.write(' ')
            with patch.object(collector, 'validate_package') as validated:
                with self.assertRaises(AssertionError):
                    with collector.historical_profile_base(package, root):
                        self.fail('Changed base must not enter replay')
                validated.assert_not_called()
            self.assertIs(collector.developer_bundle.active_mod_root, original)

    def test_closed_sessions_keep_their_own_payload_and_postcheck(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); package = root / 'candidate'
            def save(path, value):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(value), encoding='utf-8')
            session = '20261117-190000'
            state = root / 'runtime' / ('official-validation-' + session) / 'state.json'
            work = root / 'evidence/official-validation' / session
            save(state, dict(restored=True, work=str(work)))
            post_path = work / 'postcheck.json'
            post = dict(validation_state=str(state), validation_restored=True, research_box_empty=True,
                research_loader_removed=True, host_registry_unchanged=True,
                formal_files_changed=[], host_config_files_changed=[], remaining_games=[])
            save(post_path, post)
            deploy_path = work / 'control-lifecycle-deployment-1.json'
            deploy = dict(player_entry=True, mod_source_directory=str(package / 'PBZBossControl'),
                          module_source_sha256={'test': 'exact'})
            save(deploy_path, deploy); (work / 'UE4SS.log').write_text('session-local log', encoding='utf-8')
            with patch.object(collector, 'ROOT', root), patch.object(collector, 'modules', return_value={'test': 'exact'}):
                result = collector.closed_session(session, root / 'flow', package, {})
                self.assertEqual(result[:3], (state, work, 'session-local log'))
                deploy['mod_source_directory'] = str(root / 'other/PBZBossControl'); save(deploy_path, deploy)
                with self.assertRaises(AssertionError): collector.closed_session(session, root / 'flow', package, {})
                deploy['mod_source_directory'] = str(package / 'PBZBossControl'); save(deploy_path, deploy)
                post['validation_state'] = str(root / 'other/state.json'); save(post_path, post)
                with self.assertRaises(AssertionError): collector.closed_session(session, root / 'flow', package, {})

    def test_dispatch_requires_the_matching_unexpired_original_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory); state = work / 'state.json'; flow = work / 'flow'; package = work / 'package'
            gate = dict(state_file=str(state), workflow=str(flow), candidate_manifest_sha256='exact',
                action='enter', input_sent=False, gameplay_verified=False, gate_expires_at=2000000000,
                log_offset=42)
            dispatch = dict(gate, input_sent=True, dispatch_at='2026-11-17T19:00:00+08:00')
            gate_path = work / 'experience-input-1.json'; output = work / 'experience-dispatch-1.json'
            def save(path, value): path.write_text(json.dumps(value), encoding='utf-8')
            save(gate_path, gate); save(output, dispatch)
            with patch.object(collector, 'sha', return_value='exact'):
                rows, sources = collector.verified_dispatches(work, state, flow, package)
                self.assertEqual(rows, [dispatch]); self.assertEqual(set(sources), {gate_path, output})
                gate['state_file'] = str(work / 'other-state.json'); save(gate_path, gate)
                with self.assertRaises(AssertionError): collector.verified_dispatches(work, state, flow, package)
                gate['state_file'] = str(state); save(gate_path, gate)
                dispatch['dispatch_at'] = '2040-01-01T00:00:00+08:00'; save(output, dispatch)
                with self.assertRaises(AssertionError): collector.verified_dispatches(work, state, flow, package)


if __name__ == '__main__': unittest.main()
