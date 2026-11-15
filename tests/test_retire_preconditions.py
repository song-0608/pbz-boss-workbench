"""用途：复现窗口失焦时先改载体/监督器状态的缺陷，确保失败停在任何写操作之前。"""
import sys
import tempfile
import subprocess
import json
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import retire_restored_ahua as retire
from research_game_menu import validate_control_menu_transition


class RetirementPreconditions(unittest.TestCase):
    def test_native_menu_trial_requires_current_restore_and_idle_world_watch(self):
        owner={'phase':'armed','scene_transition_trial':True,'log_offset':0}
        text=('IDLE_WORLD_WATCH_READY=World /Old|owned=15\n'
              '[PBZBossControl] enter success=true state=ACTIVE\n'
              '[PBZBossControl] exit success=true state=OFF reason=\n'
              'ORIGINAL_PLAYER_POSITION_DELTA=0.0\nORIGINAL_PLAYER_NEW_ACTIVE_COUNT=0\n'
              'CAMERA_CLEANUP_ENGINE_VERIFIED=true\n')
        validate_control_menu_transition(owner,text)
        validate_control_menu_transition(dict(owner,scene_transition_trial=False,player_entry=True),text)
        for changed in (text.replace('IDLE_WORLD_WATCH_READY','MISSING'),
                        text+'SPAWN_ATTEMPT=2\n',text+'[PBZBossControl] enter success=true state=ACTIVE\n',
                        text.replace('CAMERA_CLEANUP_ENGINE_VERIFIED=true','')):
            with self.assertRaises(RuntimeError):validate_control_menu_transition(owner,changed)

    def test_active_skill_death_input_requires_explicit_current_session_scope(self):
        with tempfile.TemporaryDirectory()as folder:
            base=Path(folder);(base/'runtime').mkdir();state_file=base/'state.json'
            complete={'active_skill_death_trial':True,'native_death_trial':True,'death_trial':True,
                      'phase':'armed','state_file':str(state_file)}
            for field,value in (('active_skill_death_trial',False),('native_death_trial',False),('death_trial',False),
                                ('phase','game_launched'),('state_file','stale-session')):
                owner=dict(complete);owner[field]=value
                (base/'runtime/ahua-practice.json').write_text(json.dumps(owner),encoding='utf-8')
                with patch.object(retire.menu.v,'ROOT',base),patch.object(retire.menu.v,'state_path',return_value=state_file),\
                     patch.object(retire.menu.v.c.isolation,'select_box')as select:
                    with self.assertRaisesRegex(RuntimeError,'Explicit current-session active skill08'):
                        retire.menu.click(0,0,2560,1600,'control_death_skill08')
                    select.assert_not_called()

    def test_menu_transition_requires_latest_recovery_then_retirement(self):
        text=('[PBZBossControl] enter success=true state=ACTIVE\n'
              '[PBZBossControl] auto_exit success=true state=OFF reason=owned boss disposed\n'
              'ORIGINAL_PLAYER_POSITION_DELTA=0.0\nORIGINAL_PLAYER_NEW_ACTIVE_COUNT=0\n'
              'CAMERA_CLEANUP_ENGINE_VERIFIED=true\nPBZ_REARM_RETIRE:PASS=3\n')
        validate_control_menu_transition({'phase':'game_launched'},text)
        for phase,changed in (('armed',text),('game_launched',text+'SPAWN_ATTEMPT=1'),
                             ('game_launched',text.replace('CAMERA_CLEANUP_ENGINE_VERIFIED=true','')),
                             ('game_launched',text.replace('PBZ_REARM_RETIRE:PASS=3','[PBZBossControl] enter success=true state=ACTIVE\nPBZ_REARM_RETIRE:PASS=3'))):
            with self.assertRaises(RuntimeError):validate_control_menu_transition({'phase':phase},changed)

    def test_focus_failure_preserves_carrier_and_owner(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            carrier = base / 'main.lua'
            carrier.write_bytes(b'original loaded experiment')
            log = base / 'UE4SS.log'
            names = ['BP_Monster_AHua_GuiTouDao_C /Game/Test:PersistentLevel.Ahua_1',
                     'BP_Monster_AHua_GuiTouDao_C /Game/Test:PersistentLevel.Ahua_2']
            log.write_text('PBZ_CONTROL_LIFECYCLE:DEFERRED_ACTOR=owned\n'
                           + 'PBZ_CONTROL_LIFECYCLE:SPAWNED=' + names[0] + '\n'
                           + 'PBZ_CONTROL_LIFECYCLE:TRAINING_TARGET=' + names[1] + '\n'
                           + '[PBZBossControl] menu_exit success=true state=OFF reason=\n'
                           + 'ORIGINAL_PLAYER_POSITION_DELTA=0.0\n'
                           + 'ORIGINAL_PLAYER_NEW_ACTIVE_COUNT=0\n'
                           + 'CAMERA_CLEANUP_ENGINE_VERIFIED=true\n', encoding='utf-8')
            owner = {'phase': 'armed'}
            state = {'ue4ss_loader_manifest': [], 'formal_before': {'fixture': 'original'}}
            with patch.object(retire.practice, 'owned_session', return_value=(owner, state)), \
                 patch.object(retire.practice, 'log_path', return_value=log), \
                 patch.object(retire.practice, 'save_owner') as saved, \
                 patch.object(retire.v, 'verify_build'), \
                 patch.object(retire.v.c.baseline, 'formal_files', return_value=state['formal_before']), \
                 patch.object(retire.menu, 'click', side_effect=RuntimeError('Game is not foreground')) as focus:
                with self.assertRaisesRegex(RuntimeError, 'foreground'):
                    retire.retire()
                focus.assert_called_once_with(0, 0, 2560, 1600, 'control_focus')
                saved.assert_not_called()
            self.assertEqual(owner['phase'], 'armed')
            self.assertEqual(carrier.read_bytes(), b'original loaded experiment')

    def test_owned_identity_pairs_require_complete_ordered_class_records(self):
        names=['BP_Monster_AHua_GuiTouDao_C /Game/Test:PersistentLevel.Ahua_1',
               'BP_Monster_AHua_GuiTouDao_C /Game/Test:PersistentLevel.Ahua_2']
        actor_class='BlueprintGeneratedClass /PBZCombatAsset/ActorData/Mobs/042_AHua/BP_Monster_AHua_GuiTouDao.BP_Monster_AHua_GuiTouDao_C'
        ai_class='BlueprintGeneratedClass /PBZCombatAsset/Prototypes/AI/BP_PBZAIController.BP_PBZAIController_C'
        rows=[]
        for index,name in enumerate(names):
            rows.append(f'OWNED_RETIRE_REFERENCE=actor|{name}|address={100+index}|class={actor_class}')
            rows.append(f'OWNED_RETIRE_REFERENCE=controller|AI /Game/Test:PersistentLevel.AI_{index}|address={200+index}|class={ai_class}')
        text='\n'.join(rows)
        result=retire.owned_references(text,names)
        self.assertEqual(result[1]['controller']['address'],201)
        for broken in ('\n'.join(rows[:-1]),'\n'.join([rows[1],rows[0]]+rows[2:]),
                       text.replace(ai_class,'Class /Fixture.WrongAI'),text.replace(names[1],names[0]),
                       text.replace('address=101','address=0')):
            with self.assertRaises(RuntimeError):retire.owned_references(broken,names)

    def test_retirement_accepts_disposed_owner_but_rejects_reused_identity_before_deleting(self):
        root=Path(__file__).resolve().parents[1]
        references=[{'actor':{'name':'Object /Fixture.Ahua1','address':101,'class':'Class /Fixture.Ahua'},
                     'controller':{'name':'Object /Fixture.AI1','address':201,'class':'Class /Fixture.AI'}},
                    {'actor':{'name':'Object /Fixture.Ahua2','address':102,'class':'Class /Fixture.Ahua'},
                     'controller':{'name':'Object /Fixture.AI2','address':202,'class':'Class /Fixture.AI'}}]
        setup='''
local registry={}; local destroyed=0
local function obj(path,address,class,usable)
 local o={usable=usable~=false}
 function o:IsValid()return true end
 function o:GetAddress()return address end
 function o:GetFullName()return 'Object '..path end
 function o:GetClass()return{GetFullName=function()return 'Class '..class end}end
 function o:GetWorld()return registry['/Fixture.World']end
 function o:K2_DestroyActor()assert(self.usable);self.usable=false;destroyed=destroyed+1 end
 registry[path]=o;return o
end
local world=obj('/Fixture.World',1,'/Fixture.World')
local pc=obj('/Fixture.Map:PersistentLevel.PC',2,'/Fixture.PC');local player=obj('/Fixture.Player',3,'/Fixture.Player')
pc.Pawn=player;player.AttributeSetBase={Health={CurrentValue=100}}
function pc:IsMoveInputIgnored()return false end
function pc:IsLookInputIgnored()return false end
local dead=obj('/Fixture.Ahua1',101,'/Fixture.Ahua',false)
obj('/Fixture.AI1',201,'/Fixture.AI',false)
local actor=obj('/Fixture.Ahua2',REUSED and 999 or 102,'/Fixture.Ahua',not REUSED)
local ai=obj('/Fixture.AI2',202,'/Fixture.AI')
function actor:GetController()return ai end
function ai:K2_GetPawn()return actor end
function StaticFindObject(path)return registry[path]end
function FindAllOf()return{pc}end
function ExecuteInGameThread(fn)fn()end
package.loaded.object_lifecycle={new=function()return{usable=function(_,o)return o and o.usable or false end}end}
'''
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'retire.lua'
            for reused in (False,True):
                path.write_text('package.path="./mod/PBZBossControl/Scripts/?.lua;"..package.path\n'
                    +'local REUSED='+('true'if reused else'false')+'\n'+setup
                    +retire.retirement_script(references,2000000000)
                    +'\nassert(destroyed=='+('0'if reused else'2')+',"unexpected deletion count")\n',encoding='utf-8')
                run=subprocess.run([str(root.parent/'build/lua-harness/Release/lua-lab.exe'),str(path)],cwd=root,capture_output=True)
                self.assertEqual(run.returncode,0,(run.stdout+run.stderr).decode('utf-8',errors='replace'))
                self.assertIn(b'PBZ_REARM_RETIRE:REJECTED='if reused else b'PBZ_REARM_RETIRE:PASS=',run.stdout)


if __name__ == '__main__':
    unittest.main()
