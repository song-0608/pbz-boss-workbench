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
        self.assertEqual(data['skill_observations'][0]['observed_damage'], 100)

    def test_native_light_miss_and_geometry_are_preserved(self):
        text = (self.ready+self.active+'PBZ_CONTROL_LIFECYCLE:SKILL_GEOMETRY=skill_07|distance=279.959\n'
                +self.begin.replace('skill_01', 'skill_07')
                +self.end.replace('skill_01', 'skill_07').replace('8900.0', '9000.0')
                +'[PBZBossControl] auto_exit success=true state=OFF\n'
                +'PBZ_CONTROL_LIFECYCLE:NATIVE_TRAVEL_MENU_READY=true\n')
        data = observe(text)
        self.assertEqual(data['primary_observations'], [])
        skill, = data['skill_observations']
        self.assertEqual(skill['target_distance'], 279.959)
        self.assertEqual(skill['observed_damage'], 0)
        self.assertEqual(data['lifecycle'][-1]['event'], 'NATIVE_TRAVEL_MENU_READY')
        self.assertNotIn('passed', data)

    def test_new_assembly_invalidates_unfinished_primary_observation(self):
        text = self.ready+self.active+self.primary+self.begin+self.ready.replace('057_wanjun', '058_maddoctor')+self.end
        self.assertEqual(observe(text)['primary_observations'], [])

    def test_native_route_request_is_preserved_without_claiming_travel_success(self):
        data = observe(self.ready+'PBZ_CONTROL_LIFECYCLE:CROSS_MAP_TRIAL_ROUTE=/old|/new\n')
        self.assertEqual(data['cross_map_requests'][0]['destination'], '/new')
        self.assertEqual(data['lifecycle'], [])
        self.assertNotIn('passed', data)

    def test_overlapping_same_skill_tails_cannot_be_paired_to_newer_primary(self):
        text = (self.ready+self.active+self.begin+self.primary+self.begin
                +self.end+self.end.replace('8900.0', '8800.0'))
        data = observe(text)
        self.assertEqual(data['primary_observations'], [])
        self.assertEqual(data['skill_observations'], [])
        self.assertEqual(len(data['ambiguous_skill_observations']), 2)
        self.assertEqual(data['ambiguous_skill_observations'][0]['candidate_begin_lines'], [4, 6])

    def test_isolated_sample_after_all_overlapping_tails_is_preserved(self):
        text = (self.ready+self.active+self.begin+self.begin+self.end+self.end
                +self.primary+self.begin+self.end)
        data = observe(text)
        self.assertEqual(len(data['ambiguous_skill_observations']), 2)
        self.assertEqual(len(data['primary_observations']), 1)

    def test_new_assembly_clears_overlap_ambiguity(self):
        text = (self.ready+self.active+self.begin+self.begin+self.ready+self.active
                +self.primary+self.begin+self.end)
        data = observe(text)
        self.assertEqual(data['ambiguous_skill_observations'], [])
        self.assertEqual(len(data['primary_observations']), 1)

    def test_superseded_sample_cannot_contaminate_the_next_activation(self):
        text = (self.ready+self.active+self.primary+self.begin
                +'PBZ_CONTROL_LIFECYCLE:SKILL_OBSERVATION_STOPPED=skill_01|superseded by another activation attempt\n'
                +self.primary+self.begin+self.end)
        data = observe(text)
        attack, = data['primary_observations']
        self.assertEqual(attack['dispatch_line'], 7)
        self.assertEqual(data['ambiguous_skill_observations'], [])


if __name__ == '__main__':
    unittest.main()
