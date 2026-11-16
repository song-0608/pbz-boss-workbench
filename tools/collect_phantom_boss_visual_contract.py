"""Collect only reflected cosmetic actor/animation declarations from one role; never call game functions."""
import argparse
from pathlib import Path
import collect_phantom_boss_control_contract as control

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
ENUMS={'/Script/Engine.EAnimationMode','/Script/Engine.ECollisionEnabled'}
SOURCES=(*control.SOURCES,'tools/collect_phantom_boss_visual_contract.py')
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


def capture(game):
    result=control.capture(game,functions=FUNCTIONS,requested_properties=PROPERTIES,enums=ENUMS)
    result.update(domains=['visual'],manual_pose_no_notifies_accepted=False)
    return result


def collect(receipt,role):
    return control.collect(receipt,role,capture_fn=capture,report_stem='visual',sources=SOURCES)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('receipt',type=Path);parser.add_argument('--role',choices=('host','guest'),required=True)
    args=parser.parse_args();collect(args.receipt,args.role)
