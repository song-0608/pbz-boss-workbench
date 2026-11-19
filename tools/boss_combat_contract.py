"""Validate current reflection plus the complete offline cue script, not gameplay."""
from pathlib import Path
from boss_adaptation_workflow import ROOT, sha
import boss_combat_script_audit as scripts

CUE='/PBZCombatAsset/Prototypes/Actions/GAAction_WeaponParticle_BlueRedEye.GAAction_WeaponParticle_BlueRedEye_C'
NPC='/PBZDeflectSystem/Abilities/BP_StanceAction_Base_NPC.BP_StanceAction_Base_NPC_C'
STANCE='/PBZCombatAsset/ActorData/Mobs/056_YouLong/Ability/Abilities/AquaKiller/Dao/GA_AquaKiller_Stance.GA_AquaKiller_Stance_C'


def validate(report,pid,state_file):
    assert report['pid']==pid and report['state_file']==state_file and report['reflection_ready'] is True
    assert report['source_sha256']==sha(ROOT/'tools/inspect_boss_defense_contract.py'),'current collector source required'
    for key in ('gameplay_called','input_sent','grants_changed','tags_changed','runtime_behavior_verified'):
        assert report[key] is False,key
    classes={row['path']:row for row in report['classes']}
    assert len(classes)==len(report['classes']),'unique current class declarations required'
    def function(owner,name,parameters,native):
        rows=[f for f in classes[owner]['functions'] if f['name']==name]
        assert len(rows)==1,'unique current function required: '+name
        row,=rows
        actual=[p for p in row['parameters'] if int(p['property_flags'],16)&0x80]
        assert [(p['name'],p['type']) for p in actual]==parameters,'native parameter signature changed: '+name
        assert all(p['array_dim']==1 for p in actual)
        assert row['parameter_count']==len(actual)
        assert bool(int(row['flags'],16)&0x400)==native,'native/script function kind changed: '+name
        return row
    assert classes[CUE]['super']=='/Script/LegoAbility.LGAAction_Executable'
    function('/Script/LegoAbility.LGAAction','GetAvatarActor',[('ReturnValue','ObjectProperty')],True)
    function('/Script/GameplayAbilities.GameplayAbility','K2_CancelAbility',[],True)
    function(CUE,'Spawn Particles',[('Avatar','ObjectProperty')],False)
    function(CUE,'End Particles',[],False)
    function(CUE,'Received_ActionBegin',[(n,'FloatProperty') for n in ('ElapsedTime','TotalDuration','BeginTime')],False)
    function(CUE,'Received_ActionEnd',[(n,'BoolProperty') for n in ('bAbilityFinished','bActionFinished')],False)
    fields={p['name']:p for p in classes[CUE]['properties']}
    for name in ('Cascade Comps','Niagara Comps'):
        assert fields[name]['type']=='ArrayProperty' and fields[name]['element_size']==16
    assert classes[NPC]['super']=='/PBZDeflectSystem/Abilities/BP_StanceAction_Base.BP_StanceAction_Base_C'
    return dict(declaration_verified=True,avatar_binding_verified=True,class_path=CUE,
        developer_only=True,blueprint_post_hook_verified=True)


def build(report,pid,state_file,script_directory):
    cue=validate(report,pid,state_file)
    script=scripts.build(script_directory)
    assert script['cue_spawn_requires_hostile_relation'] is True
    cue['script_gate_verified']=True
    return dict(schema=1,pid=pid,state_file=state_file,cues=cue,
        defense_by_role={'056_youlong':dict(class_path=STANCE,key='RIGHT_MOUSE_BUTTON',
            developer_only=True,declaration_verified=True,active_count_field='ActiveCount',
            cancel_binding_verified=True,cancel_function='K2_CancelAbility')},
        sources=dict(validator_sha256=sha(__file__),collector_sha256=report['source_sha256'],
            script=script['sources'],script_directory=str(Path(script_directory))),
        live_grant_verified=False,defense_runtime_verified=False,cue_render_verified=False)
