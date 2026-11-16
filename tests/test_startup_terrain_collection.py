from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from collect_startup_terrain import observation

RAW = ('PBZ_TERRAIN_TRACE:BEGIN=origin:0,0,96|forward:1,0,0\n'
       'PBZ_TERRAIN_TRACE:QUERY=1|wanted=450,0,96|actual=unavailable\n'
       'PBZ_TERRAIN_TRACE:END=queries:1|accepted:false\n'
       'PBZ_STARTUP_TERRAIN:TOKEN=123|accepted=false|position_unchanged=true|reason=no clearance\n')


class StartupCollectionTests(unittest.TestCase):
    def test_refusal_is_observation_only(self):
        result = observation(RAW, '123', 0)
        self.assertFalse(result['ordinary_integration_accepted'])
        self.assertFalse(result['geometric_replay_claimed'])
        self.assertEqual(result['unavailable_projections'], 1)

    def test_malformed_stale_duplicate_and_contradictory_traces_rejected(self):
        variants = [RAW.replace('QUERY=1', 'QUERY=2'), RAW.replace('queries:1', 'queries:2'),
                    RAW.replace('origin:0,0,96', 'origin:nan,0,96'),
                    RAW.replace('position_unchanged=true', 'position_unchanged=false'),
                    RAW.replace('TOKEN=123', 'TOKEN=999'), RAW + RAW,
                    RAW.replace('TOKEN=123|accepted=false', 'TOKEN=123|accepted=true')]
        for raw in variants:
            with self.subTest(raw=raw), self.assertRaises((AssertionError, ValueError)):
                observation(raw, '123', 0)

    def test_assembly_or_takeover_cannot_count_as_readonly(self):
        for marker in ('SPAWN_ATTEMPT=1', 'KEY_SKILL_BEGIN=test', 'enter success=true', 'PLAYER_ENTRY_READY=ahua'):
            with self.subTest(marker=marker), self.assertRaises(AssertionError):observation(marker + '\n' + RAW, '123', 0)

    def test_later_expiry_is_preserved_without_changing_original_refusal(self):
        result = observation(RAW + 'PBZ_STARTUP_TERRAIN:ERROR=123|startup preflight expired\n', '123', 0)
        self.assertFalse(result['terrain_preflight_result'])
        self.assertEqual(result['later_errors'], ['startup preflight expired'])


if __name__ == '__main__':unittest.main()
