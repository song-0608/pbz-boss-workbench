"""用途：一批读取镜头所需原生函数和字段声明；不探图、不写内存、不调用游戏函数。"""
import json
from pathlib import Path
import struct
import sys
import official_validation as v
from pbz_readonly import GameRead
from inspect_pbz_ai_metadata import fields

FUNCTIONS={
    '/Script/Engine.Actor.AddComponentByClass',
    '/Script/Engine.SceneComponent.K2_AttachToComponent',
    '/Script/Engine.SceneComponent.SetAbsolute',
    '/Script/Engine.SceneComponent.K2_SetWorldRotation',
    '/Script/Engine.SceneComponent.K2_GetComponentLocation',
    '/Script/Engine.SceneComponent.K2_GetComponentRotation',
    '/Script/Engine.ActorComponent.K2_DestroyComponent',
    '/Script/Engine.ActorComponent.IsBeingDestroyed',
    '/Script/Engine.ActorComponent.IsComponentTickEnabled',
    '/Script/Engine.ActorComponent.SetComponentTickEnabled',
    '/Script/Engine.KismetSystemLibrary.IsValid',
    '/Script/Engine.Actor.IsActorBeingDestroyed',
    '/Script/Engine.SceneComponent.GetAttachParent',
    '/Script/Engine.CameraComponent.SetFieldOfView',
    '/Script/Engine.PlayerCameraManager.GetCameraLocation',
    '/Script/Engine.PlayerCameraManager.GetCameraRotation',
    '/Script/Engine.SpringArmComponent.IsCollisionFixApplied',
    '/Script/Engine.GameplayStatics.BeginDeferredActorSpawnFromClass',
    '/Script/Engine.GameplayStatics.FinishSpawningActor',
    '/Script/Engine.KismetMathLibrary.MakeTransform',
    '/Script/Engine.Actor.GetLocalRole',
    '/Script/Engine.Actor.GetActorScale3D',
    '/Script/Engine.CapsuleComponent.GetScaledCapsuleHalfHeight',
    '/Script/Engine.CapsuleComponent.GetScaledCapsuleRadius',
}
PROPERTIES={
    '/Script/Engine.SpringArmComponent':{'TargetArmLength','TargetOffset','SocketOffset','bUsePawnControlRotation','bDoCollisionTest','ProbeSize','ProbeChannel'},
    '/Script/Engine.CameraActor':{'CameraComponent'},
    '/Script/Engine.CameraComponent':{'bConstrainAspectRatio','bUsePawnControlRotation'},
    '/Script/Engine.Actor':{'RootComponent','Role','RemoteRole'},
    '/Script/Engine.Character':{'CapsuleComponent'},
    '/Script/Engine.CapsuleComponent':{'CapsuleHalfHeight','CapsuleRadius'},
}


def collect():
    names={p.rsplit('.',1)[1] for p in FUNCTIONS|PROPERTIES.keys()}
    declarations=[];properties=[]
    with GameRead() as g:
        for row in g.find_native(names):
            path=row['path'];address=int(row['address'],16)
            if path in FUNCTIONS:
                declarations.append({'path':path,'parameter_bytes':struct.unpack('<H',g.read(address+0x106,2))[0],
                    'parameters':[p for p in fields(g,address,32) if int(p['property_flags'],16)&0x80]})
            if path in PROPERTIES:
                for p in fields(g,address,256):
                    if p['name'] in PROPERTIES[path]:properties.append({'owner':path,**p})
        missing_functions=sorted(FUNCTIONS-{f['path'] for f in declarations})
        found={(p['owner'],p['name']) for p in properties}
        missing_properties=sorted(f'{owner}:{name}' for owner,names in PROPERTIES.items() for name in names if (owner,name)not in found)
        report={'at':v.utc8(),'pid':g.pid,'functions':declarations,'properties':properties,
            'missing_functions':missing_functions,'missing_properties':missing_properties,'passed':not missing_functions and not missing_properties,
            'scope':'Native camera declarations only; no camera creation or gameplay calls'}
        target=Path(g.state['work'])/'camera-native-contract.json';v.save(target,report)
        v.save(v.ROOT/'evidence/adaptation/latest-camera-native-contract.json',report)
    print(json.dumps({'report':str(target),'missing_functions':missing_functions,'missing_properties':missing_properties,
        'functions':[{'path':f['path'],'bytes':f['parameter_bytes'],'params':[p['name']+':'+p['type'] for p in f['parameters']]} for f in declarations]},ensure_ascii=False,indent=2))
    return 0 if report['passed'] else 1


if __name__=='__main__':sys.stdout.reconfigure(encoding='utf-8');sys.exit(collect())
