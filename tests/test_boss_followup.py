import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from collect_boss_followup import analyze
from build_boss_followup_batch import plan, render


class FollowupTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {'batch_fingerprint': 'fixture', 'ability_requests': [
            {'id': '073_yanqiansui', 'lookup_path': '/A.Leaf_C'},
            {'id': '073_yanqiansui', 'lookup_path': '/A.Tree_C'}]}
        self.lines = ['PBZ_BOSS_META:START=fixture',
            'PBZ_BOSS_META:ABILITY=073_yanqiansui|/A.Leaf_C|leaf',
            'PBZ_BOSS_META:ABILITY=073_yanqiansui|/A.Tree_C|subtree', 'PBZ_BOSS_META:END=fixture']

    def test_missing_only_and_observed_cdo_correction(self):
        candidate, identity, abilities, _ = plan()
        self.assertEqual({r['id'] for r in identity}, {'056_youlong'})
        self.assertTrue(identity[1]['lookup_path'].endswith('ActorC_YouLong_Harpoon.ActorC_YouLong_Harpoon'))
        self.assertNotEqual(identity[1]['lookup_path'], candidate['correction_source']['previous_rejected_config'])
        self.assertEqual({r['id'] for r in abilities}, {'073_yanqiansui'})
        self.assertEqual(len(abilities), 24)
        self.assertFalse(candidate['identity_verified'])
        self.assertTrue(all(not r['granted_to_actor'] and not r['playable'] for r in abilities))

    def test_types_never_prove_grants_or_control(self):
        rows = analyze(self.lines, self.manifest)
        self.assertEqual([r['ability_kind'] for r in rows], ['leaf', 'subtree'])
        self.assertTrue(all(r['metadata_verified'] for r in rows))
        self.assertTrue(all(not r['live_grant_verified'] and not r['activation_verified'] and not r['playable'] for r in rows))

    def test_missing_wrong_batch_and_expired_rejected(self):
        variants = [self.lines[:-1], self.lines[:2] + self.lines[-1:],
            [s.replace('START=fixture', 'START=other') for s in self.lines],
            self.lines + ['PBZ_BOSS_META:STOP=deadline']]
        for lines in variants:
            with self.subTest(lines=lines), self.assertRaises(AssertionError):
                analyze(lines, self.manifest)

    def test_duplicate_foreign_and_invalid_types_rejected(self):
        for line in (self.lines[1], 'PBZ_BOSS_META:ABILITY=other|/A.Leaf_C|leaf',
                'PBZ_BOSS_META:ABILITY=073_yanqiansui|/A.Unknown_C|leaf'):
            with self.subTest(line=line), self.assertRaises(AssertionError):
                analyze(self.lines[:-1] + [line, self.lines[-1]], self.manifest)
        with self.assertRaises(AssertionError):
            analyze([s.replace('|subtree', '|passive') for s in self.lines], self.manifest)

    def test_failure_is_explicit_not_success(self):
        lines = self.lines.copy()
        lines[2] = 'PBZ_BOSS_META:REJECTED=073_yanqiansui|ability|/A.Tree_C|unavailable'
        rows = analyze(lines, self.manifest)
        self.assertFalse(rows[1]['metadata_verified'])
        self.assertEqual(rows[1]['rejection'], 'unavailable')
        with self.assertRaises(AssertionError):
            analyze(self.lines[:-1] + [lines[2], self.lines[-1]], self.manifest)

    def test_probe_has_no_gameplay_calls(self):
        candidate, identity, abilities, _ = plan()
        script = render(identity, abilities, 'fixture')
        for token in ('SpawnActor(', 'Possess(', 'TryActivate', 'GiveAbility(', 'FindAllOf('):
            self.assertNotIn(token, script)
        self.assertIn('local deadline=os.time()+90', script)


if __name__ == '__main__':
    unittest.main()
