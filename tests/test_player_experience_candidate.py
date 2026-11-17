import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import build_player_experience_candidate as candidate


class CandidateTests(unittest.TestCase):
    def test_patch_preserves_gameplay_payload_and_marks_runtime_pending(self):
        base,files=candidate.payload()
        prefix='PBZBossControl/Scripts/'
        changed={name for name in base['files'] if files[name]!=(candidate.ROOT/'releases'/candidate.BASE/name).read_bytes()}
        self.assertEqual(changed,{prefix+name for name in ('ue_host.lua','runtime.lua','input_driver.lua',
            'control_bridge.lua','boss_catalog.lua','owned_arena.lua','player_hud.lua','workbench_catalog.lua','boss_workbench.lua')}|{'PBZBossControl/README.md'})
        self.assertIn(b'bind_gameplay',files[prefix+'runtime.lua'])
        self.assertIn(b'not session.current_skill',files[prefix+'input_driver.lua'])
        self.assertIn(b'lock_target',files[prefix+'boss_catalog.lua'])
        manifest,_=candidate.expected()
        self.assertEqual((manifest['ability_count'],manifest['skill_binding_count']),(52,53))
        self.assertFalse(manifest['runtime_acceptance_current'])
        self.assertFalse(manifest['complete_mod'])
        self.assertFalse(manifest['experience_runtime_verified'])

    def test_changed_or_repeated_immutable_anchor_is_rejected(self):
        for source in ('missing','once once'):
            with self.assertRaises(AssertionError):candidate.replace(source,'once','twice')


if __name__=='__main__':unittest.main()
