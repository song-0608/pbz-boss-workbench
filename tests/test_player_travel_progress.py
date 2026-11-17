"""Progress reports must preserve the distinction between requests and real effects."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from report_player_travel_progress import observe


class TravelProgressTests(unittest.TestCase):
    ready = ('PBZ_CONTROL_LIFECYCLE:SPAWN_ATTEMPT=1\n'
             'PBZ_CONTROL_LIFECYCLE:PLAYER_ENTRY_READY=057_wanjun\n')
    active = '[PBZBossControl] enter success=true state=ACTIVE\n'
    primary = '[PBZBossControl] primary_attack success=true state=ACTIVE\n'
    begin = 'PBZ_CONTROL_LIFECYCLE:KEY_SKILL_BEGIN=skill_01|active=1\n'
    end = ('PBZ_CONTROL_LIFECYCLE:KEY_SKILL_END=skill_01|peak=1|active=0|natural=true|'
           'health_before=9000.0|health_after=8900.0\n')

    def test_request_or_dispatch_alone_is_not_a_damage_observation(self):
        for text in (self.ready, self.ready+self.active+self.primary,
                     self.ready+self.active+self.primary+self.begin):
            self.assertEqual(observe(text)['primary_observations'], [])

    def test_native_primary_and_health_are_paired(self):
        data = observe(self.ready+self.active+self.primary+self.begin+self.end)
        attack, = data['primary_observations']
        self.assertEqual(attack['role'], '057_wanjun')
        self.assertEqual(attack['observed_damage'], 100)
        self.assertTrue(attack['active'] and attack['natural'])

    def test_unrelated_function_key_damage_is_not_mouse_damage(self):
        data = observe(self.ready+self.active+'[PBZBossControl] slot1 success=true state=ACTIVE\n'
                       +self.begin+self.end)
        self.assertEqual(data['primary_observations'], [])

    def test_new_assembly_invalidates_unfinished_primary_observation(self):
        text = self.ready+self.active+self.primary+self.begin+self.ready.replace('057_wanjun', '058_maddoctor')+self.end
        self.assertEqual(observe(text)['primary_observations'], [])

    def test_native_route_request_is_preserved_without_claiming_travel_success(self):
        data = observe(self.ready+'PBZ_CONTROL_LIFECYCLE:CROSS_MAP_TRIAL_ROUTE=/old|/new\n')
        self.assertEqual(data['cross_map_requests'][0]['destination'], '/new')
        self.assertEqual(data['lifecycle'], [])
        self.assertNotIn('passed', data)


if __name__ == '__main__':
    unittest.main()
