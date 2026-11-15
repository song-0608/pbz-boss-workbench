"""注册技能只能来自当前部署快照；在策略检查处停止，绝不访问窗口或发按键。"""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import research_game_menu as menu


class PolicyReached(Exception):pass


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);(self.root/'runtime').mkdir()
        self.state=self.root/'state.json'
        self.owner={'phase':'armed','state_file':str(self.state),'actual_bindings':[
            {'slot':'skill_04','skill':'skill_04','key':'ONE'}]}

    def dispatch(self,purpose,owner=None):
        (self.root/'runtime/ahua-practice.json').write_text(json.dumps(owner or self.owner),encoding='utf-8')
        with patch.object(menu.v,'ROOT',self.root),patch.object(menu.v,'state_path',return_value=self.state),\
             patch.object(menu.v.c.isolation,'select_box'),patch.object(menu.v.c.isolation,'api',return_value=object()),\
             patch.object(menu.v.c.isolation,'check_policy',side_effect=PolicyReached),\
             patch.object(menu.ctypes,'WinDLL',side_effect=AssertionError('Window API must not run')):
            menu.click(0,0,2560,1600,purpose)

    def test_normal_and_cancel_keep_registered_purpose(self):
        for purpose in ('control_registered_skill_skill_04','control_cancel_registered_skill_skill_04'):
            with self.subTest(purpose=purpose),self.assertRaises(PolicyReached):self.dispatch(purpose)

    def test_unknown_action_cannot_reach_policy_or_input(self):
        for purpose in ('control_registered_skill_invented','control_cancel_registered_skill_invented'):
            with self.assertRaisesRegex(RuntimeError,'Unregistered'):self.dispatch(purpose)

    def test_base_alias_combo_and_mouse_use_the_same_policy_gate(self):
        for slot,skill,key in (('slot1','skill_01','F1'),('primary_attack','skill_01','LEFT_MOUSE_BUTTON'),
                               ('native_combo','attack_01','R'),('dash','dash','F4')):
            owner=dict(self.owner,actual_bindings=[{'slot':slot,'skill':skill,'key':key}])
            for prefix in ('control_registered_skill_','control_cancel_registered_skill_'):
                with self.subTest(slot=slot,prefix=prefix),self.assertRaises(PolicyReached):
                    self.dispatch(prefix+slot,owner)

    def test_lab_cancel_reaches_same_isolation_gate(self):
        for purpose in ('control_lab_cast','control_cancel_lab_cast'):
            with self.subTest(purpose=purpose),self.assertRaises(PolicyReached):self.dispatch(purpose)

    def test_bounded_startup_positioning_keeps_isolation_gate(self):
        for purpose in ('practice_position_left','practice_position_forward','practice_position_back'):
            with self.subTest(purpose=purpose),self.assertRaises(PolicyReached):self.dispatch(purpose)

    def test_positioning_requires_current_unarmed_waiting_scene(self):
        owner={'phase':'game_launched','state_file':'current'}
        state={'state_file':'current','offline_validation':True,'network_active':False,'ue4ss_deployed':True}
        text='PBZ_PRACTICE:WAITING=load your isolated scene then enable practice\n'
        menu.validate_startup_positioning(owner,state,text)
        cases=[(dict(owner,phase='armed'),state,text),(dict(owner,state_file='old'),state,text),
            (owner,dict(state,network_active=True),text),(owner,dict(state,offline_validation=False),text),
            (owner,dict(state,restored=True),text),(owner,dict(state,ue4ss_deployed=False),text),
            (owner,state,''),(owner,state,text+'PBZ_CONTROL_LIFECYCLE:SPAWN_ATTEMPT=1\n')]
        for args in cases:
            with self.subTest(args=args),self.assertRaises(RuntimeError):menu.validate_startup_positioning(*args)

    def test_developer_or_stale_snapshot_rejected(self):
        for changes in ({'skill_lab':True},{'state_file':'old-session'},
                        {'actual_bindings':[{'slot':'skill_04','skill':'skill_07','key':'ONE'}]},
                        {'actual_bindings':[{'slot':'skill_04','skill':'skill_04','key':'W'}]}):
            with self.assertRaises(RuntimeError):self.dispatch('control_cancel_registered_skill_skill_04',dict(self.owner,**changes))

    def test_reposition_after_rejected_assembly_requires_full_cleanup_and_no_takeover(self):
        owner={'phase':'game_launched','state_file':'current'}
        state={'state_file':'current','offline_validation':True,'network_active':False,'ue4ss_deployed':True}
        text='PBZ_PRACTICE:WAITING=load your isolated scene then enable practice\nPBZ_CONTROL_LIFECYCLE:SPAWN_ATTEMPT=3\n'
        text+='\n'.join('OWNED_DESTROY_VERIFIED='+name+'|engine_unusable=true'for name in
            ('boss','boss_controller','target','target_controller','extra_target','extra_target_controller'))
        text+='\nPBZ_CONTROL_LIFECYCLE:PREREQUISITE_RETRY_SAFE=true\n'
        text+='PBZ_CONTROL_LIFECYCLE:END=initialization rejected before takeover; original player restoration verified\n'
        menu.validate_startup_positioning(owner,state,text)
        for extra in ('enter success=true','PLAYER_ENTRY_READY=ahua_guitoudao','ISSUE_CLEANUP=bad','state=FAULTED',
                      'PBZ_CONTROL_LIFECYCLE:SPAWN_ATTEMPT=4\n'):
            with self.subTest(extra=extra),self.assertRaises(RuntimeError):menu.validate_startup_positioning(owner,state,text+extra)
        with self.assertRaises(RuntimeError):menu.validate_startup_positioning(owner,state,text.replace('extra_target_controller|engine_unusable=true','missing'))


if __name__=='__main__':unittest.main()
