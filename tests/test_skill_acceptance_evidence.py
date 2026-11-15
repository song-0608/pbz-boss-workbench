"""逐招证据必须来自同一能力实例及有序真实活动，拒绝串用其他招式的清理。"""
import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from collect_skill_acceptance import analyze,player_binding_verified,subtree_evidence

BEGIN='KEY_SKILL_BEGIN=test|target=target|health=9000|active=1\n'
INSTANCE='SKILL_INSTANCE=test|active=true|cancelable=true|object=GA_Test_C /World.Boss.Instance\n'
END='KEY_SKILL_END=test|peak=1|active=0|natural=true|health_before=9000|health_after=8800|distance=10\n'
INVOKE='CANCEL_TRACE=invoking_cancel|class=Class /Ability.GA_Test_C|active=1|matched=1|invoked=0|instance=GA_Test_C /World.Boss.Instance\n'
CLEARED='CANCEL_TRACE=activity_cleared|class=Class /Ability.GA_Test_C|active=0|matched=1|invoked=1|instance=None\n'
RESTORE=('CANCEL_RESULT=true|active=0\n[PBZBossControl] exit success=true state=OFF reason=manual exit\n'
         'ORIGINAL_PLAYER_POSITION_DELTA=0\nORIGINAL_PLAYER_NEW_ACTIVE_COUNT=0\nCAMERA_CLEANUP_ENGINE_VERIFIED=true\n')


class EvidenceTests(unittest.TestCase):
    def test_player_binding_requires_deployment_and_actual_registration(self):
        action={'skill':'skill_04','binding':{'slot':'skill_04','skill':'skill_04','key':'ONE'}}
        deployment={'player_entry':True,'player_keymap':{'skills':{'skill_04':'ONE'}}}
        self.assertTrue(player_binding_verified(action,'PLAYER_BINDING=skill_04|skill_04|ONE\n',deployment))
        for text in ('PLAYER_BINDING=skill_04|skill_04|TWO\n','PLAYER_BINDING=other|skill_04|ONE\n','',
                     'PLAYER_BINDING=skill_04|skill_04|ONE\nPLAYER_BINDING=skill_04|skill_04|ONE\n'):
            self.assertFalse(player_binding_verified(action,text,deployment))
        self.assertFalse(player_binding_verified(action,'PLAYER_BINDING=skill_04|skill_04|ONE\n',dict(deployment,skill_lab=True)))

    def test_player_alias_requires_its_exact_catalog_ability(self):
        action={'skill':'skill_01','binding':{'slot':'slot1','skill':'skill_01','key':'F1'}}
        deployment={'player_entry':True,'player_keymap':{'skills':{'slot1':'F1'}}}
        self.assertTrue(player_binding_verified(action,'PLAYER_BINDING=slot1|skill_01|F1\n',deployment))
        self.assertFalse(player_binding_verified(dict(action,skill='heavy_01'),'PLAYER_BINDING=slot1|heavy_01|F1\n',deployment))

    def test_natural_requires_activation_and_instance(self):
        self.assertTrue(analyze(BEGIN+INSTANCE+END,'test')['natural_completion']['damage_observed'])
        for text in (END,INSTANCE+END,BEGIN+END,END+BEGIN+INSTANCE):
            self.assertIsNone(analyze(text,'test')['natural_completion'])
        self.assertIsNone(analyze(BEGIN+INSTANCE+BEGIN+INSTANCE+END,'test')['natural_completion'])

    def test_exact_instance_ordered_cancel(self):
        self.assertTrue(analyze(BEGIN+INSTANCE+INVOKE+CLEARED+RESTORE,'test')['active_cancel_and_restoration'])
        for text in (BEGIN+INSTANCE+CLEARED+INVOKE+RESTORE,
                     BEGIN+INSTANCE+INVOKE.replace('Boss.Instance','Boss.Other')+CLEARED+RESTORE,
                     BEGIN+INSTANCE+INVOKE+CLEARED.replace('GA_Test_C','GA_Other_C')+RESTORE,
                     BEGIN+INSTANCE+INVOKE+CLEARED+RESTORE.replace('exit success','stop success')):
            self.assertFalse(analyze(text,'test')['active_cancel_and_restoration'])

    def test_restore_requires_complete_same_event(self):
        text=BEGIN+INSTANCE+INVOKE+CLEARED+RESTORE
        self.assertFalse(analyze(text.replace('CAMERA_CLEANUP_ENGINE_VERIFIED=true',''),'test')['active_cancel_and_restoration'])
        self.assertFalse(analyze(text+'state=FAULTED','test')['active_cancel_and_restoration'])

    def test_natural_finite_nonnegative_and_no_fault(self):
        for replacement in ('distance=1e999','distance=-5'):
            self.assertIsNone(analyze(BEGIN+INSTANCE+END.replace('distance=10',replacement),'test')['natural_completion'])
        self.assertIsNone(analyze(BEGIN+INSTANCE+END+'PBZ_CONTROL_RESTORE:FAILED=true','test')['natural_completion'])

    def test_unrelated_player_activation_invalidates_attribution(self):
        text=BEGIN+INSTANCE+'KEY_SKILL_BEGIN=other|target=target|health=9000|active=1\n'+END+INVOKE+CLEARED+RESTORE
        result=analyze(text,'test')
        self.assertIsNone(result['natural_completion'])
        self.assertFalse(result['active_cancel_and_restoration'])
        self.assertEqual(result['foreign_keyed_activations'],['other'])

    def test_subtree_requires_exact_parent_order_and_full_cleanup(self):
        skill='homing_flower'
        name='GA_AHua_Homing_Flower'
        exact='/PBZCombatAsset/ActorData/Mobs/042_AHua/Ability/GuiTouDao/Abilities/New/'+name+'.'+name+'_C'
        start='COMBO_SCHEDULER_BEGIN='+skill+'|brain_tick=true|outer_ai=false|ai_tick=false|limit=25\n'
        begin=BEGIN.replace('=test|','='+skill+'|')
        instance=INSTANCE.replace('=test|','='+skill+'|').replace('GA_Test_C',name+'_C')
        observed='COMBO_OBSERVED_ACTIVE='+exact+'|active=1|baseline=0\n'
        stopped='COMBO_TREE_STOP=running_before=true\nCOMBO_SCHEDULER_END=cancelled=true|all_grants_at_baseline=true|brain_tick=false\n'
        segment=start+begin+instance+observed+stopped+RESTORE
        def check(text,path=exact):return subtree_evidence(text,skill,analyze(text,skill),path)
        self.assertTrue(check(segment)['active_cancel_and_restoration'])
        for text in (segment.replace(instance,''),start+instance+begin+observed+stopped+RESTORE,
                     segment.replace('all_grants_at_baseline=true','all_grants_at_baseline=false'),
                     segment.replace('COMBO_TREE_STOP=','OTHER='),start+segment,
                     segment.replace('CAMERA_CLEANUP_ENGINE_VERIFIED=true',''),
                     segment+'KEY_SKILL_BEGIN=other|target=x|active=1\n'):
            self.assertFalse(check(text)['active_cancel_and_restoration'])
        self.assertFalse(check(segment,exact.replace('Homing_Flower','Attack_01'))['active_cancel_and_restoration'])

    def test_subtree_natural_requires_scheduler_end(self):
        skill='attack_01';name='GA_AHua_Attack_01'
        exact='/PBZCombatAsset/ActorData/Mobs/042_AHua/Ability/GuiTouDao/Abilities/New/'+name+'.'+name+'_C'
        segment=('COMBO_SCHEDULER_BEGIN='+skill+'|brain_tick=true|outer_ai=false|ai_tick=false|limit=25\n'
            +BEGIN.replace('=test|','='+skill+'|')+INSTANCE.replace('=test|','='+skill+'|').replace('GA_Test_C',name+'_C')
            +'COMBO_OBSERVED_ACTIVE='+exact+'|active=1|baseline=0\n'
            +'COMBO_SCHEDULER_END=natural=true|all_grants_at_baseline=true|brain_tick=false\n'
            +END.replace('=test|','='+skill+'|'))
        self.assertIsNotNone(subtree_evidence(segment,skill,analyze(segment,skill),exact)['natural_completion'])
        missing=segment.replace('COMBO_SCHEDULER_END=natural=true','COMBO_SCHEDULER_END=natural=false')
        self.assertIsNone(subtree_evidence(missing,skill,analyze(missing,skill),exact)['natural_completion'])
        end_line='COMBO_SCHEDULER_END=natural=true|all_grants_at_baseline=true|brain_tick=false\n'
        reversed_order=segment.replace(end_line,'')+end_line
        self.assertIsNone(subtree_evidence(reversed_order,skill,analyze(reversed_order,skill),exact)['natural_completion'])


if __name__=='__main__':unittest.main()
