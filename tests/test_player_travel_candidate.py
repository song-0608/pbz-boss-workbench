"""Candidate preserves frozen v5 and marks native acceptance pending."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_player_travel_candidate as candidate
from mod_installation import validate_package


class TravelCandidateTests(unittest.TestCase):
    def test_exact_scoped_changes_and_no_native_verification_claim(self):
        base, files = candidate.payload()
        original = validate_package(ROOT / 'releases' / candidate.BASE)
        self.assertEqual(base, original)
        changed = {name for name, data in files.items()
            if name not in base['files'] or data != (ROOT / 'releases' / candidate.BASE / name).read_bytes()}
        self.assertEqual(changed, {candidate.PREFIX + name for name in (
            'player_role_controls.lua', 'player_native_travel_trial.lua', 'player_controller_query.lua', 'player_reassembly.lua',
            'player_assembly_tasks.lua', 'player_action_queue.lua', 'player_map_lifecycle.lua', 'player_controller_owner.lua',
            'control_bridge.lua', 'boss_catalog.lua', 'ue_calls.lua', 'ue_combat.lua', 'world_boundary.lua',
            'idle_world_watch.lua', 'map_travel_guard.lua', 'owned_arena.lua', 'runtime.lua',
            'ue_host.lua', 'remote_control.lua', 'boss_workbench.lua', 'player_boss_picker.lua', 'player_hud.lua')})
        manifest, _ = candidate.expected()
        self.assertFalse(manifest['complete_mod'])
        self.assertFalse(manifest['runtime_acceptance_current'])
        self.assertFalse(manifest['travel_repair_runtime_verified'])
        self.assertNotIn('acceptance_report', manifest)
        self.assertEqual(manifest['ability_count'], 58)
        self.assertNotIn(':OpenLevel(', files[candidate.PREFIX+'owned_arena.lua'].decode())


if __name__ == '__main__':
    unittest.main()
