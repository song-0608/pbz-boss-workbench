import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from mod_installation import ROOT
from build_youlong_workbench_candidate import expected, verify
from four_boss_integration_workflow import modules
from release_youlong_workbench import inherited_payload, read, validate_world_report


class ReleaseTests(unittest.TestCase):
    def test_exact_inheritance_reconstructs_all_payloads(self):
        target = ROOT / 'runtime/release-candidates' / expected()[-1]
        self.assertTrue(inherited_payload(target)['unmodified_combat_camera_input_and_restoration'])

    def test_missing_world_or_current_sources_refused(self):
        target = ROOT / 'runtime/release-candidates' / expected()[-1]
        current = modules(verify(target))
        report = read(ROOT / 'research/boss-adaptation/developer-attempt-receipts/four-boss-youlong-world-20261116-115608.json')
        validate_world_report(report, current)
        for key in ('passed', 'ordinary_roundtrip_verified', 'ordinary_skills_verified', 'new_profile_world_cycle_verified'):
            bad = copy.deepcopy(report)
            bad[key] = False
            with self.subTest(key=key), self.assertRaises(AssertionError):
                validate_world_report(bad, current)
        bad = copy.deepcopy(report)
        bad['skill_proofs'].pop()
        with self.assertRaises(AssertionError):
            validate_world_report(bad, current)
        with self.assertRaises(AssertionError):
            validate_world_report(report, dict(current, **{'ue_combat.lua': '0' * 64}))


if __name__ == '__main__':
    unittest.main()
