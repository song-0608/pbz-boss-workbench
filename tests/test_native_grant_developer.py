import ast
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import native_grant_developer_bundle as bundle
import native_grant_developer_workflow as workflow


class DeveloperTests(unittest.TestCase):
    def test_exact_new_leaf_pools_and_historical_identity_without_player_promotion(self):
        for identifier, review in bundle.REVIEWS.items():
            value, evidence = bundle.definition(identifier)
            baseline, _ = bundle.previous.definition(identifier)
            self.assertEqual([p.rsplit('.', 1)[-1] for p in value['ability_pool']], list(review['priority']))
            self.assertEqual(value['class_path'], baseline['class_path'])
            self.assertEqual(value['config_path'], baseline['config_path'])
            self.assertEqual(value['max_local_displacement_cm'], 3000)
            self.assertIn(bundle.RECEIPT, evidence)
            self.assertNotIn('playable', value)
        self.assertEqual(bundle.definition('067_motian')[0]['followup_action_kind'], 'dodge-only-candidate')
        with self.assertRaises(AssertionError): bundle.definition('058_maddoctor')

    def test_failed_subtree_duplicate_foreign_or_promoted_metadata_is_rejected(self):
        original = bundle.verify_receipt
        for mode in ('failed', 'subtree', 'duplicate', 'foreign', 'promoted', 'live'):
            def changed(path, root):
                data = copy.deepcopy(original(path, root))
                row = next(r for r in data['outcomes'] if r['id'] == '071_xianzhe')
                if mode == 'failed': row['metadata_verified'] = False
                elif mode == 'subtree': row['ability_kind'] = 'subtree'
                elif mode == 'duplicate': data['outcomes'].append(copy.deepcopy(row))
                elif mode == 'foreign': row['class_path'] = row['class_path'].replace('071_XianZhe', '067_MoTian')
                elif mode == 'promoted': data['playable'] = True
                else: row['live_grant_verified'] = True
                return data
            with self.subTest(mode=mode), patch.object(bundle, 'verify_receipt', side_effect=changed):
                with self.assertRaises(AssertionError): bundle.definition('071_xianzhe')

    def test_versioned_workflow_retains_original_runtime_gates(self):
        files = workflow.render()
        for name, data in files.items(): ast.parse(data.decode('utf-8'), filename=name)
        runner = files['run_control_lifecycle_probe.py'].decode('utf-8')
        for gate in ('v.verify_build', "c.baseline.formal_files()!=s['formal_before']", 'issue_expiry',
                     "time.time()>s['deadline_unix']-120"):
            self.assertIn(gate, runner)
        for name in ('test_player_skill_batch.py', 'run_boss_candidate_milestone.py', 'collect_boss_candidate_acceptance.py'):
            self.assertIn('native_grant_developer_bundle', files[name].decode('utf-8'))
            self.assertNotIn('expanded_boss_developer_bundle', files[name].decode('utf-8'))
        gate = {}; exec(files['boss_candidate_gate.py'], gate)
        for identifier in ('071_xianzhe', '067_motian', '058_maddoctor'):
            with self.assertRaises(RuntimeError): gate['validate'](identifier)

    def test_mutated_frozen_bundle_cannot_validate(self):
        value, _ = bundle.definition('071_xianzhe')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); base = root / 'mod/PBZBossControl/Scripts'; base.mkdir(parents=True)
            (base / 'sentinel.lua').write_bytes(b'return {}')
            for name in bundle.SOURCES:
                path = root / name; path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((bundle.ROOT / name).read_bytes())
            with patch.object(bundle, 'definition', return_value=(value, {})):
                target = bundle.build('071_xianzhe', root)
                self.assertEqual(target, bundle.build('071_xianzhe', root))
                (target / 'boss_candidate.lua').write_bytes(b'changed')
                with self.assertRaises(AssertionError): bundle.validate('071_xianzhe', target, root=root)


if __name__ == '__main__': unittest.main()
