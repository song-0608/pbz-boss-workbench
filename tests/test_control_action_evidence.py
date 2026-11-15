"""用途：用真实失败模式保护验收结论，不把限时收尾和冷却拒绝记成按键取消通过。"""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from control_action_evidence import cancellation_result, classify_stop, restoration_result, death_restoration_result, reload_retakeover_result, world_retirement_result


class CancellationEvidence(unittest.TestCase):
    start='KEY_SKILL_BEGIN=skill_07|active=1\nCANCEL_ACTIVE_BEFORE=1\nCANCEL_RESULT=true|active=0\n'
    exit='[PBZBossControl] exit success=true state=OFF'

    def test_real_player_cancel(self):
        self.assertTrue(cancellation_result(self.start+self.exit,'skill_07'))

    def test_automatic_timeout_is_not_f10(self):
        text=self.start+'[PBZBossControl] stop success=true state=OFF'
        self.assertFalse(cancellation_result(text,'skill_07'))
        self.assertTrue(classify_stop(text)['automatic_stop'])

    def test_cooldown_rejection_and_unrelated_skill(self):
        self.assertFalse(cancellation_result(self.exit,'skill_07'))
        self.assertFalse(cancellation_result(self.start+self.exit,'skill_08'))

    def test_failed_or_out_of_order_restore(self):
        self.assertFalse(cancellation_result(self.exit+self.start,'skill_07'))
        self.assertFalse(cancellation_result(self.start+self.exit+' state=FAULTED','skill_07'))


class RestorationEvidence(unittest.TestCase):
    event = '[PBZBossControl] menu_exit success=true state=OFF reason=Esc requested menu exit\n'
    reads = ('ORIGINAL_PLAYER_POSITION_DELTA=0.0\nORIGINAL_PLAYER_NEW_ACTIVE_COUNT=0\n'
             'CAMERA_CLEANUP_ENGINE_VERIFIED=true\n')

    def test_menu_restore_requires_all_independent_reads(self):
        self.assertTrue(restoration_result(self.event+self.reads, 'menu_exit')['passed'])
        self.assertFalse(restoration_result(self.event, 'menu_exit')['passed'])
        self.assertFalse(restoration_result(self.reads+self.event, 'menu_exit')['passed'])

    def test_next_control_cycle_cannot_supply_missing_reads(self):
        text = self.event+'[PBZBossControl] enter success=true state=ACTIVE\n'+self.reads
        self.assertFalse(restoration_result(text, 'menu_exit')['passed'])

    def test_death_and_timeout_are_distinct(self):
        death = '[PBZBossControl] auto_exit success=true state=OFF reason=boss health depleted\n'
        self.assertTrue(restoration_result(death+self.reads, 'auto_exit', 'boss health depleted')['passed'])
        self.assertFalse(restoration_result(death+self.reads, 'exit')['passed'])
        self.assertFalse(restoration_result('[PBZBossControl] stop success=true state=OFF\n'+self.reads)['passed'])

    def test_player_drift_or_unusable_numeric_evidence_fails(self):
        for value in ('356', 'nan', 'inf', 'unreadable'):
            self.assertFalse(restoration_result(self.event+self.reads.replace('0.0', value))['passed'])

    def test_native_disposal_requires_ordered_engine_proof_and_is_not_hp_depletion(self):
        text = ('OWNED_DEATH_TRIAL_BEGIN=owned|health=9000\n'
                'OWNED_DEATH_TRIAL_KILL_REQUESTED=true\n'
                'PBZ_CONTROL_RESTORE:OWNED_DISPOSAL_VERIFIED=true\n'
                '[PBZBossControl] auto_exit success=true state=OFF reason=owned boss disposed\n'
                'CONTROLLED_BOSS_DISPOSED=true\n'+self.reads)
        proof = death_restoration_result(text, native=True)
        self.assertTrue(proof['passed'])
        self.assertFalse(proof['hp_depletion_verified'])
        self.assertFalse(death_restoration_result(text, native=False)['passed'])
        for missing in ('OWNED_DEATH_TRIAL_KILL_REQUESTED=true', 'PBZ_CONTROL_RESTORE:OWNED_DISPOSAL_VERIFIED=true',
                        'CONTROLLED_BOSS_DISPOSED=true'):
            self.assertFalse(death_restoration_result(text.replace(missing, ''), native=True)['passed'])
        active=text.replace('OWNED_DEATH_TRIAL_KILL_REQUESTED=true','OWNED_DEATH_TRIAL_ACTIVE_SKILL=skill_08|active=1\nOWNED_DEATH_TRIAL_KILL_REQUESTED=true')
        proof=death_restoration_result(active,native=True,active_skill='skill_08')
        self.assertTrue(proof['passed']);self.assertEqual(proof['active_count_at_request'],1)
        self.assertFalse(proof['active_at_object_disposal_verified'])
        self.assertFalse(death_restoration_result(text,native=True,active_skill='skill_08')['passed'])


class ReloadEvidence(unittest.TestCase):
    def cycle(self,world,offset,skill=False):
        text='[PBZBossControl] enter success=true state=ACTIVE reason=\nCONTROL_WORLD_ID=session|World /Game/Map|'+str(world)+'\n'
        for index,key in enumerate(('player_controller','player','boss')):
            text+=f'CONTROL_PARTICIPANT={key}|Object /Game/{key}_{offset}|address={offset+index}|class=Class /Fixture.{key}\n'
        if skill:text+='KEY_SKILL_END=skill_01|peak=1|active=0|natural=true|health_before=9000|health_after=8900\n'
        return(text+'[PBZBossControl] exit success=true state=OFF reason=\n'
               'ORIGINAL_PLAYER_POSITION_DELTA=0.0\nORIGINAL_PLAYER_NEW_ACTIVE_COUNT=0\nCAMERA_CLEANUP_ENGINE_VERIFIED=true\n')

    def test_new_world_and_new_participant_retakeover(self):
        proof=reload_retakeover_result(self.cycle(100,10)+'PBZ_REARM_RETIRE:PASS=3\n',self.cycle(200,20,True))
        self.assertTrue(proof['passed'])

    def test_screenshot_alone_reused_identity_and_old_world_cannot_pass(self):
        before=self.cycle(100,10)+'PBZ_REARM_RETIRE:PASS=3\n'
        for after in ('title and gameplay screenshots',self.cycle(100,20,True),self.cycle(200,10,True),
                      self.cycle(200,20),self.cycle(200,20,True).replace('session|','another|')):
            self.assertFalse(reload_retakeover_result(before,after)['passed'])

    def test_next_cycle_cannot_supply_identity_or_cleanup(self):
        before=self.cycle(100,10)+'PBZ_REARM_RETIRE:PASS=3\n'
        after=self.cycle(200,20,True).replace('CONTROL_WORLD_ID=','MISSING_WORLD=')
        self.assertFalse(reload_retakeover_result(before,after)['passed'])
        self.assertFalse(reload_retakeover_result(before.replace('PBZ_REARM_RETIRE:PASS=3',''),self.cycle(200,20,True))['passed'])


class WorldRetirementEvidence(unittest.TestCase):
    begin=('[PBZBossControl] enter success=true state=ACTIVE\n'
           'ACTIVE_WORLD_TRIAL_REQUESTED=true\nPBZ_CONTROL_WORLD:OLD_OBJECTS_DISPOSED=true\n'
           '[PBZBossControl] world_retired success=true state=OFF reason=old world and modified participants disposed\n')
    cleanup=''.join('OWNED_DESTROY_VERIFIED='+label+'|engine_unusable=true\n'for label in(
        'boss','boss_controller','target','target_controller','extra_target','extra_target_controller'))+'WORLD_REASSEMBLY_WAIT=true\n'

    def test_disposal_is_not_new_world_readiness(self):
        proof=world_retirement_result(self.begin+self.cleanup)
        self.assertTrue(proof['passed']);self.assertFalse(proof['new_world_ready'])

    def test_missing_owned_object_or_fault_cannot_pass(self):
        text=self.begin+self.cleanup
        for broken in(text.replace('OWNED_DESTROY_VERIFIED=boss|','MISSING=boss|'),
                      text+'state=FAULTED',text.replace('ACTIVE_WORLD_TRIAL_REQUESTED=true',''),
                      self.begin.replace('world_retired success=true','state=FAULTED\nworld_retired success=true')+self.cleanup):
            self.assertFalse(world_retirement_result(broken)['passed'])

    def test_next_assembly_cannot_supply_cleanup(self):
        self.assertFalse(world_retirement_result(self.begin+'SPAWN_ATTEMPT=1\n'+self.cleanup)['passed'])
        self.assertFalse(world_retirement_result(self.begin+'[PBZBossControl] enter success=true state=ACTIVE\n'+self.cleanup)['passed'])

if __name__=='__main__':unittest.main()
