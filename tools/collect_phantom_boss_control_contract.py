"""Collect pinned control declarations once per live role; never issue bindings or call gameplay."""
import argparse
import json
from pathlib import Path
import struct
import time
import uuid

from build_phantom_boss_candidate import ROOT, canonical, sha
from inspect_camera_contract import FUNCTIONS as CAMERA_FUNCTIONS, PROPERTIES as CAMERA_PROPERTIES
from inspect_remote_contract import FUNCTIONS as REMOTE_FUNCTIONS
from inspect_arena_contract import FUNCTIONS as ARENA_FUNCTIONS
from inspect_pbz_ai_metadata import fields
from phantom_boss_online_readonly import OnlineGameRead, validate_receipt

FUNCTIONS=CAMERA_FUNCTIONS|REMOTE_FUNCTIONS|ARENA_FUNCTIONS|{
    '/Script/Engine.CharacterMovementComponent.DisableMovement',
    '/Script/Engine.CharacterMovementComponent.SetMovementMode',
    '/Script/Engine.Actor.GetActorEnableCollision',
    '/Script/Engine.Actor.SetActorEnableCollision',
    '/Script/Engine.Actor.SetActorHiddenInGame',
    '/Script/Engine.Controller.LineOfSightTo',
    '/Script/AIModule.BrainComponent.StopLogic',
    '/Script/AIModule.BrainComponent.IsRunning',
    '/Script/SGameAI.SGameAIComponent.StartAI',
    '/Script/SGameAI.SGameAIComponent.StopAI',
    '/Script/SGameCombatSystem.FactionComponent.SetFaction',
    '/Script/SGameCombatSystem.FactionComponent.GetCurrnetFaction',
    '/Script/SGameCombatSystem.FactionUtils.GetFactionRelation',
    '/Script/SGameCombatSystem.TargetingComponent.SetLockTarget',
    '/Script/SGameCombatSystem.TargetingComponent.StopLockTarget',
    '/Script/SGameCombatSystem.TargetingComponentHolder.GetTargetingComponent',
    '/Script/ProjectPBZ.PBZCharacter.GetLockingTarget',
}
PROPERTIES={owner:set(names) for owner,names in CAMERA_PROPERTIES.items()}
PROPERTIES['/Script/Engine.Actor'].update({'bBlockInput','InputPriority','InputComponent','bHidden','bCanBeDamaged'})
PROPERTIES.update({
    '/Script/Engine.InputComponent':set(),
    '/Script/Engine.CharacterMovementComponent':{'MovementMode','CustomMovementMode'},
    '/Script/SGameAI.SGameAIComponent':{'bAIStarted','bInitialized'},
    '/Script/SGameCombatSystem.TargetingComponent':{'LockTarget'},
    '/Script/GameplayTags.GameplayTag':{'TagName'},
    '/Script/SGameUtils.ComponentSocket':{'Component','SocketName'},
})
ENUMS={
    '/Script/Engine.EAttachmentRule',
    '/Script/Engine.ECollisionChannel',
    '/Script/Engine.ESpawnActorCollisionHandlingMethod',
    '/Script/Engine.ESpawnActorScaleMethod',
    '/Script/AIModule.ETeamAttitude',
}
PREFIXES=tuple(sorted({path.split('.',1)[0]+'.' for path in FUNCTIONS|PROPERTIES.keys()|ENUMS}))
SOURCES=('tools/collect_phantom_boss_control_contract.py','tools/phantom_boss_online_readonly.py',
    'tools/inspect_camera_contract.py','tools/inspect_remote_contract.py','tools/inspect_arena_contract.py',
    'tools/inspect_pbz_ai_metadata.py')


def enum_rows(game,address):
    # Same verified UE5_07 split name/value array layout used by the existing
    # lifecycle inspector; values belong to reflected enums, never actor state.
    names,values,count=struct.unpack('<QQi4x',game.read(address+0x40,24))
    if not 0<count<=512:raise ValueError('bounded control enum required')
    names&=~1;values&=~1
    result=[]
    for index in range(count):
        comp,num=struct.unpack('<II',game.read(names+index*8,8))
        result.append(dict(name=game.name(comp,num),value=struct.unpack('<q',game.read(values+index*8,8))[0]))
    if len({row['name'] for row in result})!=len(result):raise ValueError('duplicate control enum name')
    return result


def capture(game,*,functions=None,requested_properties=None,enums=None):
    """One bounded native metadata pass, injectable for offline regression."""
    functions=FUNCTIONS if functions is None else functions
    requested_properties=PROPERTIES if requested_properties is None else requested_properties
    enums=ENUMS if enums is None else enums
    wanted=functions|requested_properties.keys()|enums
    prefixes=tuple(sorted({path.split('.',1)[0]+'.' for path in wanted}))
    requested_enums=set(enums)
    found={};declarations=[];properties=[];enum_declarations=[];classes=[]
    for row in game.find_native({p.rsplit('.',1)[1] for p in wanted},prefixes=prefixes):
        path=row['path']
        if path not in wanted:continue
        if path in found:raise ValueError('ambiguous control declaration: '+path)
        found[path]=row
        address=int(row['address'],16)
        if path in functions:
            parameters=fields(game,address,33)
            if len(parameters)>32:raise ValueError('control parameter chain exceeds bound')
            declarations.append(dict(path=path,parameter_bytes=struct.unpack('<H',game.read(address+0x106,2))[0],
                parameter_count=game.read(address+0x104,1)[0],
                return_offset=struct.unpack('<H',game.read(address+0x108,2))[0],
                parameters=[p for p in parameters if int(p['property_flags'],16)&0x80]))
        elif path in requested_properties:
            classes.append(dict(path=path,size=game.u32(address+0xa8)))
            reflected=fields(game,address,513)
            if len(reflected)>512:raise ValueError('control property chain exceeds bound')
            properties.extend(dict(owner=path,**p) for p in reflected if p['name'] in requested_properties[path])
        else:
            if game.header(row['class'])['name']!='Enum':raise ValueError('unexpected reflected enum kind')
            enum_declarations.append(dict(path=path,rows=enum_rows(game,address)))
    present={(p['owner'],p['name']) for p in properties}
    missing_functions=sorted(functions-found.keys())
    missing_classes=sorted(requested_properties.keys()-found.keys())
    missing_properties=sorted(owner+':'+name for owner,names in requested_properties.items()
        for name in names if (owner,name) not in present)
    missing_enums=sorted(requested_enums-found.keys())
    return dict(functions=sorted(declarations,key=lambda r:r['path']),
        properties=sorted(properties,key=lambda r:(r['owner'],r['name'])),
        classes=sorted(classes,key=lambda r:r['path']),enums=sorted(enum_declarations,key=lambda r:r['path']),
        missing_functions=missing_functions,missing_classes=missing_classes,
        missing_properties=missing_properties,missing_enums=missing_enums,
        complete_requested_declarations=not any((missing_functions,missing_classes,missing_properties,missing_enums)),
        binding_verified=False,game_functions_called=False,inventory_inspected=False,memory_written=False,
        runtime_acceptance_current=False)


def collect(receipt,role,*,capture_fn=None,report_stem='control',sources=SOURCES):
    assert report_stem in ('control','native-bundle','workbench','visual')
    receipt=Path(receipt).resolve();original=receipt.read_bytes()
    source_hashes={name:sha((ROOT/name).read_bytes()) for name in sources}
    with OnlineGameRead(receipt,role) as game:
        result=(capture_fn or capture)(game)
        # Never publish a report under a replaced receipt, expired lease or PID.
        from phantom_boss_pair_session import process_identity
        session,instance=validate_receipt(receipt,role,time.time())
        assert receipt.read_bytes()==original and instance==game.instance
        assert instance['game_identity']==process_identity(game.pid),'role process changed while capturing declarations'
        assert source_hashes=={name:sha((ROOT/name).read_bytes()) for name in sources},'collector sources changed'
        result.update(schema=1,status='declarations-only',role=role,pid=game.pid,
            session=session['session'],activation=instance['activation'],game_identity=instance['game_identity'],
            session_sha256=sha(original),collected_at=int(time.time()),
            source_sha256=source_hashes)
    target=receipt.parent/(role+'-'+report_stem+'-declarations-'+uuid.uuid4().hex+'.json')
    with target.open('xb') as stream:stream.write(canonical(result)+b'\n')
    print(json.dumps(dict(report=str(target),complete_requested_declarations=result['complete_requested_declarations'],
        functions=len(result['functions']),properties=len(result['properties']),enums=len(result['enums']),
        binding_verified=False),ensure_ascii=False))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('receipt',type=Path);parser.add_argument('--role',choices=('host','guest'),required=True)
    args=parser.parse_args();collect(args.receipt,args.role)
