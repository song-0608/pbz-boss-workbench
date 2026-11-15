"""用途：同进程部署一次短时角色生命周期实验；仅研究镜像，单独声明写操作，不冒充只读。"""
import hashlib
import json
from pathlib import Path
import time
import sys
import argparse
import official_validation as v
import research_game_menu as menu
import player_keymap
import player_settings
from practice_lease import issue_expiry
from mod_installation import active_mod_root


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--performance-profile',action='store_true')
    parser.add_argument('--interactive',action='store_true')
    parser.add_argument('--camera',action='store_true')
    parser.add_argument('--combat',action='store_true')
    parser.add_argument('--update-modules',action='store_true')
    parser.add_argument('--remote',action='store_true')
    parser.add_argument('--batch-skills',action='store_true')
    parser.add_argument('--barrier',action='store_true')
    parser.add_argument('--protect-player',action='store_true')
    parser.add_argument('--practice',action='store_true')
    parser.add_argument('--look-only',action='store_true')
    parser.add_argument('--target-cycle',action='store_true')
    parser.add_argument('--extra-skills',action='store_true')
    parser.add_argument('--skill-lab',action='store_true')
    parser.add_argument('--combo-scheduler-trial',action='store_true')
    parser.add_argument('--player-key-trial',action='store_true')
    parser.add_argument('--death-trial',action='store_true')
    parser.add_argument('--incoming-combat-trial',action='store_true')
    parser.add_argument('--native-death-trial',action='store_true')
    parser.add_argument('--active-skill-death-trial',action='store_true')
    parser.add_argument('--active-skill-disposal-trial',action='store_true')
    parser.add_argument('--player-entry',action='store_true')
    parser.add_argument('--scene-transition-trial',action='store_true')
    parser.add_argument('--arena-navigation-trial',action='store_true')
    args=parser.parse_args()
    mod_root=active_mod_root()
    scripts=mod_root/'Scripts'
    if args.active_skill_disposal_trial and not args.active_skill_death_trial:
        raise RuntimeError('Disposal trial requires explicit protected active-skill scope')
    if args.incoming_combat_trial and(not args.death_trial or args.native_death_trial or args.active_skill_death_trial or args.player_entry):
        raise RuntimeError('Incoming combat requires explicit protected idle death trial without Kill or player entry')
    if args.combo_scheduler_trial and not(args.skill_lab and args.practice and args.remote and not args.player_entry):
        raise RuntimeError('Combo scheduler requires explicit protected developer skill lab')
    if args.scene_transition_trial and not args.player_entry:raise RuntimeError('Transition trial requires complete player entry')
    if args.player_entry and (args.extra_skills or args.skill_lab or args.player_key_trial or args.death_trial):
        raise RuntimeError('Player entry cannot include developer actions')
    if args.active_skill_death_trial and not args.native_death_trial:raise RuntimeError('Active skill trial requires explicit native death scope')
    if args.native_death_trial and not args.death_trial:raise RuntimeError('Explicit owned death-trial scope required')
    native_death_reason=None
    player_keys=player_keymap.read()
    if args.scene_transition_trial and any('F12'in values.values()for values in player_keys.values()):raise RuntimeError('F12 reserved for explicit transition trial')
    if args.death_trial and(not args.practice or args.skill_lab or args.extra_skills):
        raise RuntimeError('Owned-boss death trial requires protected default practice')
    if args.death_trial and any('F12' in values.values()for values in player_keys.values()):
        raise RuntimeError('F12 reserved for explicit developer death trial')
    if args.player_key_trial and (not args.practice or args.skill_lab or args.extra_skills):
        raise RuntimeError('Player-key trial requires protected default-key practice without another F8 bank')
    if args.extra_skills and args.skill_lab:raise RuntimeError('Choose one developer bank; F8/F9 are shared')
    if (args.target_cycle or args.extra_skills or args.skill_lab)and not(args.practice and args.combat):raise RuntimeError('Expanded controls require protected offline practice')
    if args.practice and not(args.interactive and args.remote and args.barrier and args.protect_player and args.batch_skills):raise RuntimeError('Practice requires complete protected interactive assembly')
    if args.combat and args.interactive and not(args.remote and args.barrier):raise RuntimeError('Interactive combat requires remote control and owned input barrier')
    if args.barrier and not args.remote:raise RuntimeError('--barrier requires --remote')
    if args.remote and not(args.combat and args.camera):raise RuntimeError('--remote requires --combat --camera')
    if args.batch_skills and not args.remote:raise RuntimeError('--batch-skills requires --remote')
    if args.look_only and not (args.camera and args.interactive):raise RuntimeError('--look-only requires --camera --interactive')
    s=json.loads(v.state_path().read_text(encoding='utf-8'));work=Path(s['work'])
    if s.get('restored') or not s.get('offline_validation') or s.get('network_active') or time.time()>s['deadline_unix']-120:
        raise RuntimeError('Active offline lease and cleanup margin required')
    c=v.c;c.isolation.select_box('PBZSteamLab');dll=c.isolation.api()
    c.isolation.check_policy(dll,allow_offline_validation=True)
    if args.arena_navigation_trial:
        if not(args.player_entry or args.skill_lab or args.combo_scheduler_trial or args.player_key_trial or args.active_skill_disposal_trial):raise RuntimeError('Navigation requires player entry or explicit protected skill/combo/key/disposal trial')
        import arena_contract
        arena_contract.validate(json.loads((work/'arena-native-contract.json').read_text(encoding='utf-8')),
            {p['ProcessId']for p in c.box_processes(dll)if p['Name'].lower()=='pbz.exe'})
    if args.player_entry or((args.skill_lab or args.combo_scheduler_trial or args.player_key_trial or args.active_skill_disposal_trial)and args.arena_navigation_trial):
        import player_ui_contract
        ui_contract_path=work/'player-ui-native-contract.json'
        player_ui_contract.validate(json.loads(ui_contract_path.read_text(encoding='utf-8')),
            {p['ProcessId']for p in c.box_processes(dll)if p['Name'].lower()=='pbz.exe'})
        if args.scene_transition_trial:
            functions=json.loads(ui_contract_path.read_text(encoding='utf-8'))['functions']
            rows=[f for f in functions if f['path']=='/Script/Engine.GameplayStatics.OpenLevel']
            expected=[('WorldContextObject','ObjectProperty','0x0',8),('LevelName','NameProperty','0x8',8),
                      ('bAbsolute','BoolProperty','0x10',1),('Options','StrProperty','0x18',16)]
            if len(rows)!=1 or rows[0]['parameter_bytes']!=40 or [(p['name'],p['type'],p['offset'],p['element_size'])for p in rows[0]['parameters']]!=expected:
                raise RuntimeError('Exact current-process OpenLevel contract required')
    if args.death_trial:
        contract=json.loads((work/'boss-lifecycle-contract.json').read_text(encoding='utf-8'))
        pids={p['ProcessId']for p in c.box_processes(dll)if p['Name'].lower()=='pbz.exe'}
        expected=[('DamagedActor','ObjectProperty'),('BaseDamage','FloatProperty'),('EventInstigator','ObjectProperty'),
            ('DamageCauser','ObjectProperty'),('DamageTypeClass','ClassProperty'),('ReturnValue','FloatProperty')]
        damage=contract['damage']
        if contract['pid']not in pids or len(damage)!=1 or damage[0]['parameter_bytes']!=44 or [(p['name'],p['type'])for p in damage[0]['parameters']]!=expected:
            raise RuntimeError('Fresh exact ApplyDamage contract required')
        if args.native_death_trial:
            kills=[fn for cls in contract['classes']if cls['path']=='/Script/ProjectPBZ.PBZCharacter_NPC'
                   for fn in cls['functions']if fn['name']=='Kill']
            if len(kills)!=1 or kills[0]['parameter_bytes']!=1 or [(p['name'],p['type'],p['offset'])for p in kills[0]['parameters']]!=[('DieReason','EnumProperty','0x0')]:
                raise RuntimeError('Fresh exact native Kill enum parameter required')
            reasons=[r['value']for enum in contract.get('enums',[])if enum['path']=='/Script/CharacterBasics.EPBZDieReason'
                     for r in enum['rows']if r['name']=='EPBZDieReason::Damaged']
            if len(reasons)!=1 or not 0<reasons[0]<255:raise RuntimeError('Verified current native damage death reason required')
            native_death_reason=reasons[0]
    if args.protect_player:
        protection=json.loads((work/'player-protection-contract.json').read_text(encoding='utf-8'))
        if protection['pid']not in{p['ProcessId']for p in c.box_processes(dll)if p['Name'].lower()=='pbz.exe'}:raise RuntimeError('Fresh player protection declarations required')
        fs={f['name']:f['parameter_bytes']for cls in protection['classes']for f in cls['functions']}
        if any(fs.get(k)!=n for k,n in {'DisableMovement':0,'SetMovementMode':2,'GetActorEnableCollision':1,'SetActorEnableCollision':1,'SetActorHiddenInGame':1}.items()):raise RuntimeError('Player protection function mismatch')
    if c.host_steam_pids(dll) or c.baseline.formal_files()!=s['formal_before']:raise RuntimeError('Existing session or formal change preserved')
    v.verify_build(s['ue4ss_loader_manifest'])
    # 用途：热重载会卸载旧Lua回调；上一临时角色实验未确认结束时，禁止覆盖恢复凭据。
    if s.get('boss_lifecycle_experiment'):
        previous_log=next(Path(r['physical_path']).parent/'UE4SS.log' for r in s['ue4ss_loader_manifest'] if r['physical_path'].endswith('UE4SS.dll'))
        previous=previous_log.read_text(encoding='utf-8',errors='replace')
        start=previous.rfind('PBZ_CONTROL_LIFECYCLE:DEFERRED_ACTOR=')
        if start>=0:
            segment=previous[start:]
            ended='PBZ_CONTROL_LIFECYCLE:INTERACTIVE_END=' in segment or 'PBZ_CONTROL_LIFECYCLE:END=' in segment
            if not ended or 'DESTROY_SKIPPED' in segment or 'ISSUE_CLEANUP' in segment:
                raise RuntimeError('Previous lifecycle cleanup not confirmed; preserve current runtime')
    proof=json.loads((v.ROOT/'evidence/latest-gameplay-save-isolation.json').read_text(encoding='utf-8'))
    if not proof.get('passed') or not (work/'gameplay-probe-allowed.json').exists():raise RuntimeError('Fresh backup and game-authored save isolation required')
    remote_binding=None
    if args.remote:
        contract=json.loads((work/'remote-native-contract.json').read_text(encoding='utf-8'))
        ai_class=contract['ai_class']
        assert all(any(f['name']==name and f['parameter_bytes']==0 for f in ai_class['functions'])for name in ('StartAI','StopAI'))
        assert any(p['name']=='bAIStarted'and p['type']=='BoolProperty'for p in ai_class['fields'])
        current={p['ProcessId']for p in c.box_processes(dll)if p['Name'].lower()=='pbz.exe'}
        if not contract.get('passed')or contract['pid']not in current:raise RuntimeError('Fresh remote native contract required')
        expected={'SetActorTickEnabled':1,'IsActorTickEnabled':1,'SetComponentTickEnabled':1,'IsComponentTickEnabled':1,'SetIgnoreMoveInput':1,'SetIgnoreLookInput':1,'IsMoveInputIgnored':1,'IsLookInputIgnored':1,
            'GetControlRotation':24,'SetControlRotation':24,'DisableInput':8,'EnableInput':8,
            'K2_SetFocus':8,'K2_ClearFocus':0,'GetFocusActor':8}
        for name,size in expected.items():
            found=[f for f in contract['functions']if f['path'].rsplit('.',1)[1]==name]
            if len(found)!=1 or found[0]['parameter_bytes']!=size:raise RuntimeError('Remote contract mismatch: '+name)
        remote_binding={'binding_verified':True}
        if args.barrier:
            barrier=json.loads((work/'input-barrier-contract.json').read_text(encoding='utf-8'))
            if not barrier.get('passed')or barrier['pid']not in current:raise RuntimeError('Fresh input barrier property contract required')
    combat_binding=None
    if args.combat:
        contract=json.loads((work/'combat-native-contract.json').read_text(encoding='utf-8'))
        types=json.loads((work/'combat-types.json').read_text(encoding='utf-8'))
        current={p['ProcessId']for p in c.box_processes(dll)if p['Name'].lower()=='pbz.exe'}
        if contract['pid']not in current or types['pid']!=contract['pid']:raise RuntimeError('Current combat declarations required')
        expected={'SetFaction':8,'GetCurrnetFaction':8,'SetLockTarget':17,'StopLockTarget':0,'GetLockingTarget':16}
        functions=[f for row in contract['classes']for f in row['functions']]
        for name,size in expected.items():
            found=[f for f in functions if f['name']==name]
            if not found or any(f['parameter_bytes']!=size for f in found):raise RuntimeError('Combat contract mismatch: '+name)
        for path,size in [('/Script/GameplayTags.GameplayTag',8),('/Script/SGameUtils.ComponentSocket',16)]:
            if not any(t['path']==path and t['size']==size for t in types['structs']):raise RuntimeError('Combat struct mismatch: '+path)
        log_path=next(Path(r['physical_path']).parent/'UE4SS.log'for r in s['ue4ss_loader_manifest']if r['physical_path'].endswith('UE4SS.dll'))
        log=log_path.read_text(encoding='utf-8',errors='replace')
        for required in ('PBZ_COMBAT_CONTRACT:ENUM=ETeamAttitude::Friendly|0','PBZ_COMBAT_CONTRACT:ENUM=ETeamAttitude::Hostile|2','PBZ_COMBAT_CONTRACT:PASS=read only faction and component query'):
            if required not in log:raise RuntimeError('Missing combat read-only proof: '+required)
        combat_binding={'binding_verified':True,'friendly':0,'hostile':2,'diagnostic':True}
        if remote_binding:combat_binding['ai_focus_bridge']=True
        v.save(work/'combat-binding.json',{'at':v.utc8(),'pid':contract['pid'],'binding':combat_binding})
    camera_binding=None
    if args.camera:
        contract=json.loads((work/'camera-native-contract.json').read_text(encoding='utf-8'))
        current={p['ProcessId'] for p in c.box_processes(dll) if p['Name'].lower()=='pbz.exe'}
        if not contract.get('passed') or contract.get('pid') not in current:raise RuntimeError('Current-process camera contract required')
        expected={
            'BeginDeferredActorSpawnFromClass':(144,['WorldContextObject','ActorClass','SpawnTransform','CollisionHandlingOverride','Owner','TransformScaleMethod','ReturnValue']),
            'FinishSpawningActor':(128,['Actor','SpawnTransform','TransformScaleMethod','ReturnValue']),
            'MakeTransform':(176,['Location','Rotation','Scale','ReturnValue']),
            'K2_AttachToComponent':(21,['Parent','SocketName','LocationRule','RotationRule','ScaleRule','bWeldSimulatedBodies','ReturnValue']),
            'AddComponentByClass':(128,['Class','bManualAttachment','RelativeTransform','bDeferredFinish','ReturnValue']),
            'K2_SetWorldRotation':(289,['NewRotation','bSweep','SweepHitResult','bTeleport']),
            'SetAbsolute':(3,['bNewAbsoluteLocation','bNewAbsoluteRotation','bNewAbsoluteScale']),
            'K2_DestroyComponent':(8,['Object']),
            'IsBeingDestroyed':(1,['ReturnValue']),
            'IsComponentTickEnabled':(1,['ReturnValue']),
            'SetComponentTickEnabled':(1,['bEnabled']),
            'IsActorBeingDestroyed':(1,['ReturnValue']),
            'GetAttachParent':(8,['ReturnValue']),
            'IsValid':(9,['Object','ReturnValue']),
        }
        for name,(size,params) in expected.items():
            found=[f for f in contract['functions'] if f['path'].rsplit('.',1)[-1]==name]
            if len(found)!=1 or found[0]['parameter_bytes']!=size or [p['name'] for p in found[0]['parameters']]!=params:
                raise RuntimeError('Camera parameter contract mismatch: '+name)
        log_path=next(Path(r['physical_path']).parent/'UE4SS.log' for r in s['ue4ss_loader_manifest'] if r['physical_path'].endswith('UE4SS.dll'))
        log=log_path.read_text(encoding='utf-8',errors='replace')
        values={'keep_relative':('EAttachmentRule','EAttachmentRule::KeepRelative',0),
            'keep_world':('EAttachmentRule','EAttachmentRule::KeepWorld',1),'snap':('EAttachmentRule','EAttachmentRule::SnapToTarget',2),
            'camera_channel':('ECollisionChannel','ECC_Camera',4),
            'spawn_collision':('ESpawnActorCollisionHandlingMethod','ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButDontSpawnIfColliding',3),
            'spawn_scale':('ESpawnActorScaleMethod','ESpawnActorScaleMethod::OverrideRootScale',0)}
        for enum,name,value in values.values():
            if 'PBZ_CAMERA_CONTRACT:ENUM=/Script/Engine.'+enum+'|'+name+'|'+str(value) not in log:
                raise RuntimeError('Missing current-process enum evidence: '+name)
        camera_binding={'binding_verified':True,**{key:value[2] for key,value in values.items()}}
        v.save(work/'camera-binding.json',{'at':v.utc8(),'pid':contract['pid'],'binding':camera_binding,'contract_sha256':hashlib.sha256((work/'camera-native-contract.json').read_bytes()).hexdigest()})
    elif not (work/'spawn-contract.json').exists() or not (work/'make-transform-contract.json').exists():raise RuntimeError('Current-process parameter contracts required')
    candidates=[row for row in s['ue4ss_loader_manifest'] if row['physical_path'].replace('\\','/').endswith('/Mods/PBZObserveAI/Scripts/main.lua')]
    if len(candidates)!=1:raise RuntimeError('Exact experiment carrier required')
    row=candidates[0];main_path=Path(row['physical_path']);directory=main_path.parent
    # 初始化单独预留120秒；交互仍由owned_arena硬限600秒，总会话期限始终优先。
    # 只用于新签发装配，不修改或延长任何已有凭据。
    grant={'isolated':True,'offline':True,'expires_at':issue_expiry(time.time(),s['deadline_unix'],practice=args.practice,remote=args.remote),
           'session_id':Path(s['state_file']).parent.name,'exe_sha256':'4415933ce33476f14c837abb61a1b60af8b78cd81783896501913a7aac69e423'}
    # 用途：签发者已核对真实策略；此凭据仅45秒且独立看门狗不延长总会话，不是永久offline开关。
    fields=', '.join(key+'='+('true' if value is True else str(value) if isinstance(value,int) else json.dumps(value)) for key,value in grant.items())
    interactive=args.interactive
    prefix='local experiment_interactive='+('true' if interactive else 'false')+'\nlocal function experiment_attest() return {'+fields+'} end\n'
    if args.performance_profile:
        prefix+=(v.ROOT/'tools/performance_probe.lua').read_text(encoding='utf-8')+'\n'
    if camera_binding:
        prefix+='local experiment_camera_binding={'+','.join(k+'='+('true' if value is True else str(value)) for k,value in camera_binding.items())+'}\n'
    if combat_binding:
        prefix+='local experiment_combat_binding={'+','.join(k+'='+('true'if value is True else str(value))for k,value in combat_binding.items())+'}\n'
    if remote_binding:prefix+='local experiment_remote_binding={binding_verified=true}\n'
    if args.batch_skills:prefix+='local experiment_batch_skills=true\n'
    if args.barrier:prefix+='local experiment_barrier_binding={binding_verified=true}\n'
    if args.protect_player:prefix+='local experiment_protection_binding={binding_verified=true}\n'
    if args.practice:prefix+='local experiment_practice=true\n'
    if args.target_cycle:prefix+='local experiment_target_cycle=true\n'
    if args.extra_skills:prefix+='local experiment_extra_skills=true\n'
    if args.skill_lab:prefix+='local experiment_skill_lab=true\n'
    if args.combo_scheduler_trial:prefix+='local experiment_combo_scheduler_trial=true\n'
    if args.player_key_trial:prefix+='local experiment_player_key_trial=true\n'
    if args.death_trial:prefix+='local experiment_death_trial=true\n'
    if args.incoming_combat_trial:prefix+='local experiment_incoming_combat_trial=true\n'
    if args.active_skill_death_trial:prefix+='local experiment_active_skill_death_trial=true\n'
    if args.active_skill_disposal_trial:prefix+='local experiment_active_skill_disposal_trial=true\n'
    if native_death_reason is not None:prefix+='local experiment_native_death_reason='+str(native_death_reason)+'\n'
    if not(args.skill_lab or args.extra_skills):prefix+='local experiment_keymap='+player_keymap.lua(player_keys)+'\n'
    if (args.skill_lab or args.combo_scheduler_trial or args.player_key_trial or args.active_skill_disposal_trial)and args.arena_navigation_trial:
        prefix+='local experiment_player_ui_binding={binding_verified=true}\nlocal experiment_arena_binding={binding_verified=true}\n'
    if args.player_entry:
        prefix+='local experiment_player_ui_binding={binding_verified=true}\n'
        prefix+='local experiment_arena_binding='+('{binding_verified=true}'if args.arena_navigation_trial else'nil')+'\n'
        prefix+='local experiment_scene_transition_trial='+('true'if args.scene_transition_trial else'false')+'\n'
        options=('attest','interactive','camera_binding','combat_binding','remote_binding','batch_skills',
                 'barrier_binding','protection_binding','practice','target_cycle','keymap','player_ui_binding','scene_transition_trial','arena_binding')
        selected=player_settings.read()['boss_id']
        prefix+='PBZBossControlLaunch={boss_id='+json.dumps(selected)+',options={'+','.join(
            key+'=experiment_'+key for key in options)+'}}\n'
        content=prefix.encode('utf-8')+(scripts/'main.lua').read_bytes()
    else:
        content=prefix.encode('utf-8')+(mod_root/'Experiments/spawn_lifecycle.lua').read_bytes()
    pending={main_path:content}
    for source in scripts.rglob('*.lua'):
        if source.name=='main.lua':continue
        target=directory/source.relative_to(scripts)
        if target.exists():
            declared=next((r for r in s['ue4ss_loader_manifest'] if r['physical_path']==str(target)),None)
            if not declared or hashlib.sha256(target.read_bytes()).hexdigest()!=declared['sha256']:
                raise RuntimeError('Undeclared or changed existing script preserved: '+str(target))
            if target.read_bytes()!=source.read_bytes():
                if not args.update_modules:raise RuntimeError('Module changed; batch rebuild required before reloading')
                # 用途：旧实验结束且现有哈希吻合后，留底批量更新，不覆盖未结束实验。
                backup=work/'module-history'/str(time.time_ns())/source.relative_to(scripts)
                backup.parent.mkdir(parents=True,exist_ok=True);backup.write_bytes(target.read_bytes())
                pending[target]=source.read_bytes()
            continue
        pending[target]=source.read_bytes()
    (work/'control-probe-before.lua').write_bytes(main_path.read_bytes())
    row['sha256']=hashlib.sha256(content).hexdigest()
    for target,data in pending.items():
        if target!=main_path:
            prior=next((r for r in s['ue4ss_loader_manifest']if r['physical_path']==str(target)),None)
            if prior:prior['sha256']=hashlib.sha256(data).hexdigest()
            else:s['ue4ss_loader_manifest'].append({'physical_path':str(target),'sha256':hashlib.sha256(data).hexdigest()})
    s.update({'boss_lifecycle_experiment':True,'readonly_ai_experiment':False,'readonly_ue4ss_experiment':False,
              'control_probe_interactive':interactive,'control_probe_expires_at':grant['expires_at'],
              'control_probe_scope':'Temporary confirmed Ahua: possession, bounded movement, first granted skill and natural finish, restoration, destroy owned actor; no map exploration or formal save changes'})
    if args.combo_scheduler_trial:
        s['control_probe_scope']='Owned Ahua Attack_01 developer experiment: exact granted parent and known subtree; at most 25 seconds Brain permission; outer AI and controller ticks stopped; track parent/children; native StopLogic/cancel and verified restore or terminate isolated process'
    # 用途：先记录拟部署文件，确保回收器能撤除所有新增模块。
    v.save(v.state_path(),s)
    for target,data in pending.items():
        target.parent.mkdir(parents=True,exist_ok=True);temporary=target.with_suffix('.pending');temporary.write_bytes(data);temporary.replace(target)
    v.verify_build(s['ue4ss_loader_manifest'])
    deployment={'at':v.utc8(),'grant':grant,'formal_install_modified':False,'temporary_actor_owned_by_probe':True,
                'performance_profile':args.performance_profile,
                'player_entry':args.player_entry,'boss_id':player_settings.read()['boss_id']if args.player_entry else None,
                'scene_transition_trial':args.scene_transition_trial,
                'arena_navigation_trial':args.arena_navigation_trial,
                'skill_lab':args.skill_lab,'expanded':args.extra_skills,'player_key_trial':args.player_key_trial,
                'combo_scheduler_trial':args.combo_scheduler_trial,
                'death_trial':args.death_trial,'native_death_trial':args.native_death_trial,'active_skill_death_trial':args.active_skill_death_trial,
                'active_skill_disposal_trial':args.active_skill_disposal_trial,
                'incoming_combat_trial':args.incoming_combat_trial,
                'player_keymap':player_keys if not(args.skill_lab or args.extra_skills) else None,
                'mod_source_directory':str(mod_root),
                'assembly_source_sha256':hashlib.sha256((mod_root/'Experiments/spawn_lifecycle.lua').read_bytes()).hexdigest(),
                'module_source_sha256':{p.relative_to(scripts).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in scripts.rglob('*.lua') if p.name!='main.lua'}}
    v.save(work/'control-lifecycle-deployment.json',deployment)
    # 用途：同进程多次装配各留一份来源记录，不用后一次配置冒充前一次实测源码。
    v.save(work/('control-lifecycle-deployment-'+str(time.time_ns())+'.json'),deployment)
    menu.click(0,0,2560,1600,'control_reload')
    print('Bounded lifecycle experiment hot reload requested in existing isolated game; no restart.')


if __name__=='__main__':main()
