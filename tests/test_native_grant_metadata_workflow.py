"""Closed metadata evidence must survive independent replay; never launches a game."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import native_grant_metadata_workflow as flow
import boss_native_grant_followup as grants
from boss_adaptation_workflow import sha


class WorkflowTests(unittest.TestCase):
    def manifest(self):
        record, _ = grants.expected()
        return record

    def lines(self, manifest):
        return ['PBZ_ADAPTER_META:START=' + manifest['fingerprint']] + [
            'PBZ_ADAPTER_META:OUTCOME=' + j['key'] + '|ability|' + j['lookup_path'] + '|leaf'
            for j in manifest['jobs']] + ['PBZ_ADAPTER_META:END=' + manifest['fingerprint']]

    def test_idle_carrier_and_remaining_lease_are_required(self):
        owner = dict(state_file='owned', phase='game_launched')
        state = dict(state_file='owned', readonly_ai_experiment=True, ue4ss_deployed=True,
                     readonly_hot_reload_enabled=True, offline_validation=True, deadline_unix=1000)
        flow.idle_guard(owner, state, 0)
        for change in (dict(boss_lifecycle_experiment=True), dict(readonly_ai_experiment=False),
                       dict(ue4ss_deployed=False), dict(restored=True), dict(network_active=True),
                       dict(readonly_hot_reload_enabled=False),
                       dict(offline_validation=False), dict(deadline_unix=120)):
            with self.subTest(change=change), self.assertRaises(AssertionError):
                flow.idle_guard(owner, dict(state, **change), 0)
        for change in (dict(phase='armed'), dict(state_file='foreign')):
            with self.assertRaises(AssertionError): flow.idle_guard(dict(owner, **change), state, 0)

    def test_leaf_and_subtree_metadata_never_promote_gameplay(self):
        manifest = self.manifest(); lines = self.lines(manifest)
        lines[1] = lines[1].replace('|leaf', '|subtree')
        _, rows = flow.analyze_attempt('\n'.join(lines), manifest)
        self.assertEqual(rows[0]['ability_kind'], 'subtree')
        self.assertTrue(all(r['metadata_verified'] for r in rows))
        self.assertTrue(all(not r[k] for r in rows for k in
                            ('playable', 'activation_verified', 'live_grant_verified', 'identity_verified')))

    def test_incomplete_duplicate_and_foreign_attempts_are_rejected(self):
        manifest = self.manifest(); lines = self.lines(manifest)
        trials = [lines[:-1], lines * 2, lines[:2] + lines[1:],
                  [lines[0], lines[1].replace(manifest['jobs'][0]['key'], 'unknown')] + lines[2:]]
        for trial in trials:
            with self.assertRaises(AssertionError): flow.analyze_attempt('\n'.join(trial), manifest)

    def fixture(self, root):
        manifest = self.manifest(); session = '20261118-200000'
        batch = root / 'research/boss-adaptation/native-grant-followups' / manifest['fingerprint']
        work = root / 'evidence/official-validation' / session
        state_path = root / 'runtime' / ('official-validation-' + session) / 'state.json'
        for p in (batch, work, state_path.parent): p.mkdir(parents=True)
        def save(path, data): path.write_text(json.dumps(data), encoding='utf-8')
        save(batch / 'manifest.json', manifest)
        # Match a small fixture script instead of loading any game code.
        script = batch / 'metadata-probe.lua'; script.write_bytes(b'-- metadata fixture\n')
        manifest['script_sha256'] = sha(script); save(batch / 'manifest.json', manifest)
        label = flow.stem(manifest)
        (work / (label + '.lua')).write_bytes(script.read_bytes())
        prefix = 'old unrelated log\n'.encode('utf-8')
        lines = self.lines(manifest)
        (work / 'UE4SS.log').write_bytes(prefix + ('\n'.join(lines) + '\n').encode('utf-8'))
        save(state_path, dict(restored=True, work=str(work)))
        save(work / 'postcheck.json', dict(validation_state=str(state_path), research_box_empty=True,
             research_loader_removed=True, host_registry_unchanged=True,
             formal_files_changed=[], host_config_files_changed=[]))
        common = dict(state_file=str(state_path), fingerprint=manifest['fingerprint'],
                      script_sha256=manifest['script_sha256'], batch_manifest_sha256=sha(batch / 'manifest.json'),
                      metadata_only=True)
        save(work / (label + '-staged.json'), dict(common, log_byte_offset=len(prefix), ui_input_sent=False))
        save(work / (label + '-results.json'), dict(common, lines=lines, boss_control_verified=False,
                                                  all_metadata_requests_passed=True))
        return manifest, session, batch, work, save

    def test_closed_collect_and_receipt_replay_do_not_promote_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); manifest, session, batch, _, _ = self.fixture(root)
            with patch.object(flow, 'verify', return_value=manifest):
                target = flow.collect(session, batch, root)
                self.assertEqual(flow.collect(session, batch, root), target)
                receipt = flow.verify_receipt(target, root)
                self.assertFalse(receipt['playable']); self.assertFalse(receipt['runtime_acceptance_current'])
                changed = copy.deepcopy(receipt); changed['playable'] = True
                target.write_text(json.dumps(changed), encoding='utf-8')
                with self.assertRaises(AssertionError): flow.verify_receipt(target, root)

    def test_postcheck_raw_script_action_and_offset_drift_are_rejected(self):
        for mutation in ('postcheck', 'raw', 'script', 'action', 'offset', 'prior_duplicate'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve(); manifest, session, batch, work, save = self.fixture(root)
                label = flow.stem(manifest)
                if mutation == 'postcheck':
                    path = work / 'postcheck.json'; data = json.loads(path.read_bytes())
                    data['formal_files_changed'] = ['changed']; save(path, data)
                elif mutation == 'raw':
                    path = work / 'UE4SS.log'
                    path.write_bytes(path.read_bytes().replace(b'|leaf', b'|subtree', 1))
                elif mutation == 'script': (work / (label + '.lua')).write_bytes(b'changed')
                elif mutation == 'action':
                    path = work / (label + '-results.json'); data = json.loads(path.read_bytes())
                    data['lines'] = data['lines'][:-1]; save(path, data)
                elif mutation == 'offset':
                    path = work / (label + '-staged.json'); data = json.loads(path.read_bytes())
                    data['log_byte_offset'] = -1; save(path, data)
                else:
                    path = work / 'UE4SS.log'; raw = path.read_bytes(); path.write_bytes(raw + raw)
                    staged = work / (label + '-staged.json'); data = json.loads(staged.read_bytes())
                    data['log_byte_offset'] += len(raw); save(staged, data)
                with patch.object(flow, 'verify', return_value=manifest), self.assertRaises(AssertionError):
                    flow.closed_evidence(session, batch, root)

    def test_frozen_followup_rejects_manifest_script_or_directory_drift(self):
        record, raw = grants.expected()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            target = root / 'research/boss-adaptation/native-grant-followups' / record['fingerprint']
            target.mkdir(parents=True)
            path = target / 'manifest.json'; path.write_text(json.dumps(record), encoding='utf-8')
            script = target / 'metadata-probe.lua'; script.write_bytes(raw)
            with patch.object(grants, 'expected', return_value=(record, raw)):
                grants.verify(target, root)
                changed = copy.deepcopy(record); changed['playable'] = True
                path.write_text(json.dumps(changed), encoding='utf-8')
                with self.assertRaises(AssertionError): grants.verify(target, root)
                path.write_text(json.dumps(record), encoding='utf-8'); script.write_bytes(b'changed')
                with self.assertRaises(AssertionError): grants.verify(target, root)
                script.write_bytes(raw); (target / 'extra.lua').write_bytes(b'changed')
                with self.assertRaises(AssertionError): grants.verify(target, root)


if __name__ == '__main__': unittest.main()
