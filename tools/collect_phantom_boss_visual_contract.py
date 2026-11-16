"""Collect only reflected cosmetic actor/animation declarations from one role; never call game functions."""
import argparse
import json
from pathlib import Path
import struct

from build_phantom_boss_candidate import ROOT, canonical, sha
from inspect_pbz_ai_metadata import fields
from phantom_boss_online_readonly import OnlineGameRead

FUNCTIONS={
    '/Script/Engine.Actor.AddComponentByClass',
    '/Script/Engine.Actor.GetActorEnableCollision',
    '/Script/Engine.Actor.SetActorEnableCollision',
    '/Script/Engine.Actor.SetActorTickEnabled',
    '/Script/Engine.Actor.IsActorTickEnabled',
    '/Script/Engine.Actor.SetActorHiddenInGame',
    '/Script/Engine.Actor.K2_SetActorLocationAndRotation',
    '/Script/Engine.Actor.K2_DestroyActor',
    '/Script/Engine.Actor.IsActorBeingDestroyed',
    '/Script/Engine.ActorComponent.GetOwner',
    '/Script/Engine.ActorComponent.SetComponentTickEnabled',
    '/Script/Engine.ActorComponent.IsComponentTickEnabled',
    '/Script/Engine.SceneComponent.GetAttachParent',
    '/Script/Engine.SceneComponent.GetRelativeTransform',
    '/Script/Engine.PrimitiveComponent.SetCollisionEnabled',
    '/Script/Engine.PrimitiveComponent.GetCollisionEnabled',
    '/Script/Engine.PrimitiveComponent.SetGenerateOverlapEvents',
    '/Script/Engine.PrimitiveComponent.GetGenerateOverlapEvents',
    '/Script/Engine.PrimitiveComponent.GetNumMaterials',
    '/Script/Engine.PrimitiveComponent.GetMaterial',
    '/Script/Engine.PrimitiveComponent.SetMaterial',
    '/Script/Engine.SkinnedMeshComponent.GetSkeletalMeshAsset',
    '/Script/Engine.SkeletalMeshComponent.SetSkeletalMesh',
    '/Script/Engine.SkeletalMeshComponent.SetAnimationMode',
    '/Script/Engine.SkeletalMeshComponent.GetAnimationMode',
    '/Script/Engine.SkeletalMeshComponent.SetAnimation',
    '/Script/Engine.SkeletalMeshComponent.SetPlaying',
    '/Script/Engine.SkeletalMeshComponent.IsPlaying',
    '/Script/Engine.SkeletalMeshComponent.SetPosition',
    '/Script/Engine.AnimSequenceBase.GetPlayLength',
    '/Script/Engine.AnimInstance.GetCurrentActiveMontage',
    '/Script/Engine.AnimInstance.Montage_GetPosition',
}
PROPERTIES={
    '/Script/Engine.Actor':{'RootComponent'},
    '/Script/Engine.Character':{'Mesh'},
    '/Script/Engine.SkeletalMeshActor':{'SkeletalMeshComponent'},
    '/Script/Engine.SkeletalMesh':{'Skeleton'},
    '/Script/Engine.AnimationAsset':{'Skeleton'},
    '/Script/Engine.AnimMontage':{'SlotAnimTracks'},
    '/Script/Engine.SlotAnimationTrack':{'SlotName','AnimTrack'},
    '/Script/Engine.AnimTrack':{'AnimSegments'},
    '/Script/Engine.AnimSegment':{'AnimReference','StartPos','AnimStartTime','AnimEndTime','AnimPlayRate','LoopingCount'},
}


def collect(receipt,role):
    receipt=Path(receipt).resolve()
    wanted={path.rsplit('.',1)[1] for path in FUNCTIONS|PROPERTIES.keys()}
    declarations=[];properties=[]
    with OnlineGameRead(receipt,role) as g:
        for row in g.find_native(wanted):
            path=row['path'];address=int(row['address'],16)
            if path in FUNCTIONS:
                declarations.append(dict(path=path,parameter_bytes=struct.unpack('<H',g.read(address+0x106,2))[0],
                    parameters=[p for p in fields(g,address,32) if int(p['property_flags'],16)&0x80]))
            if path in PROPERTIES:
                properties.extend(dict(owner=path,**p) for p in fields(g,address,256) if p['name'] in PROPERTIES[path])
        missing_functions=sorted(FUNCTIONS-{row['path'] for row in declarations})
        found={(p['owner'],p['name']) for p in properties}
        missing_properties=sorted(owner+':'+name for owner,names in PROPERTIES.items() for name in names if (owner,name) not in found)
        report=dict(schema=1,status='declarations-only',role=role,pid=g.pid,
            session_sha256=sha(receipt.read_bytes()),functions=declarations,properties=properties,
            missing_functions=missing_functions,missing_properties=missing_properties,
            complete_declarations=not missing_functions and not missing_properties,
            binding_verified=False,manual_pose_no_notifies_accepted=False,game_functions_called=False,
            inventory_inspected=False,memory_written=False,runtime_acceptance_current=False,
            source_sha256={name:sha((ROOT/name).read_bytes()) for name in (
                'tools/collect_phantom_boss_visual_contract.py','tools/phantom_boss_online_readonly.py')})
    target=receipt.parent/(role+'-visual-declarations.json')
    with target.open('xb') as stream:stream.write(canonical(report)+b'\n')
    print(json.dumps(dict(report=str(target),functions=len(declarations),properties=len(properties),
        missing_functions=missing_functions,missing_properties=missing_properties,binding_verified=False),ensure_ascii=False))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('receipt',type=Path);parser.add_argument('--role',choices=('host','guest'),required=True)
    args=parser.parse_args();collect(args.receipt,args.role)
