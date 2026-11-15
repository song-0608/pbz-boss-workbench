"""用途：一次只读会话集中采集角色、组件和函数声明；错误入清单，不执行游戏函数。"""
import json
from pathlib import Path
import re
import struct
import sys
import official_validation as v
from inspect_pbz_ai_metadata import fields, functions
from pbz_readonly import GameRead


LINKS = {'Controller','Pawn','CharacterMovement','AbilitySystemComponent','BrainComponent',
         'Blackboard','StateTreeComponent','PlayerCameraManager','PlayerState','TargetActor','CurrentTarget',
         'BP_PBZHatredManagerComponent','Actor Config','SGameAIComponent','BlackboardAsset','TreeAsset','BehaviorTree'}
FUNCTIONS = re.compile(r'possess|unpossess|getpawn|getcontroller|getcharacter|getability|viewtarget|camera|'
    r'getactorlocation|getactorrotation|steer|input|logic|running|statetree|skill|abilit|target|boss|hatred|threat',re.I)


def collect():
    failures=[];objects=[];metadata={};addresses={};ancestry={}
    with GameRead() as g:
        native=g.find_native({'PBZCharacter','PBZPlayerController'})
        bases={int(h['address'],16):h['path'] for h in native
            if h['path'] in ('/Script/ProjectPBZ.PBZCharacter','/Script/ProjectPBZ.PBZPlayerController')}
        if len(bases)!=2:raise RuntimeError('Required native base classes unavailable')

        def lineage(cls):
            result=[]
            for _ in range(40):
                if not cls:return result
                if cls in result:raise ValueError('Inheritance cycle')
                result.append(cls);cls=g.u64(cls+0x40)
            raise ValueError('Inheritance depth exceeds bounded scope')

        def category(cls):
            if cls not in ancestry:
                chain=lineage(cls);base=next((bases[x] for x in chain if x in bases),None)
                ancestry[cls]=(base,chain if base else [])
            return ancestry[cls]

        def declaration(cls):
            if cls not in metadata:
                if len(metadata)>=80:raise ValueError('Class collection budget reached')
                props=fields(g,cls)
                size=g.u32(cls+0xa8)
                # 用途：数值不合理就拒绝读取对应实例，避免再把属性标志当成员偏移。
                for p in props:
                    off=int(p['offset'],16)
                    p['numeric_sanity_passed']=(1<=p['array_dim']<=4096 and 0<=p['element_size']<=65536
                        and 0<=off<=size and off+p['array_dim']*p['element_size']<=size)
                metadata[cls]={'path':g.path(cls),'properties_size':size,'properties':props,
                    'relevant_functions':[f for f in functions(g,cls) if FUNCTIONS.search(f['name'])][:96]}
            return metadata[cls]

        def references(address,chain):
            result={}
            for cls in chain:
                for p in declaration(cls)['properties']:
                    if p['name'] not in LINKS or p['name'] in result:continue
                    row={'declared_owner':g.path(cls),'offset':p['offset'],'type':p['type']}
                    result[p['name']]=row
                    if not p['numeric_sanity_passed'] or p['element_size']!=8 or p['array_dim']!=1:
                        row['status']='invalid_numeric_metadata';continue
                    if p['type'] not in ('ObjectProperty','ObjectPtrProperty'):
                        row['status']='unsupported_reference_type';continue
                    pointer=g.u64(address+int(p['offset'],16))
                    if not pointer:row['status']='null';continue
                    try:
                        h=g.header(pointer)
                        row.update({'status':'indexed_uobject','path':g.path(pointer),'class':g.path(h['class']),'index':h['index']})
                        addresses[row['path']]=pointer
                    except (OSError,ValueError,UnicodeError) as error:
                        row.update({'status':'unresolved','error_type':type(error).__name__})
            return result

        for index in range(g.count):
            try:
                address=g.object(index)
                if not address:continue
                raw=g.read(address,40)
                if struct.unpack_from('<I',raw,8)[0]&0x30:continue
                cls=struct.unpack_from('<Q',raw,0x10)[0];base,chain=category(cls)
                if not base:continue
                path=g.path(address);addresses[path]=address
                objects.append({'path':path,'class':g.path(cls),'index':index,'base':base,
                    'lineage':[g.path(c) for c in chain],'references':references(address,chain)})
                if len(objects)>=40:break
            except (OSError,ValueError,UnicodeError) as error:
                # 用途：单个对象读失败只停止该分支；保存有限错误，不为它重启游戏。
                if len(failures)<40:failures.append({'object_index':index,'error_type':type(error).__name__})

        # 用途：在同一进程内继续采集已验证引用的组件与AI控制器，避免为每个组件重启。
        linked=[];seen={row['path'] for row in objects}
        pending=[(ref,1) for row in objects for ref in row['references'].values()]
        while pending and len(linked)<24:
            ref,depth=pending.pop(0)
            if ref.get('status')!='indexed_uobject' or ref['path'] in seen:continue
            seen.add(ref['path']);address=addresses[ref['path']]
            try:
                cls=g.header(address)['class'];chain=lineage(cls)
                item={'path':ref['path'],'class':g.path(cls),'depth':depth,'references':references(address,chain)}
                linked.append(item)
                if depth<2:pending.extend((child,depth+1) for child in item['references'].values())
            except (OSError,ValueError,UnicodeError) as error:
                failures.append({'scope':'linked_component','error_type':type(error).__name__})
        by_path={r['path']:r for r in objects}
        reciprocal=[]
        for row in objects:
            if not row['base'].endswith('.PBZPlayerController'):continue
            pawn=row['references'].get('Pawn',{});target=by_path.get(pawn.get('path'))
            back=target['references'].get('Controller',{}) if target else {}
            reciprocal.append({'controller':row['path'],'pawn':pawn.get('path'),
                'reciprocal_reference_verified':bool(target and back.get('status')=='indexed_uobject' and back.get('path')==row['path'])})
        report={'at':v.utc8(),'pid':g.pid,'scope':'Single-handle bounded read-only metadata batch; no game calls, writes or input',
            'objects':objects,'linked_objects':linked,'class_metadata':list(metadata.values()),'failures':failures,
            'player_controller_pawn_checks':reciprocal,
            'player_controller_pawn_verified':bool(reciprocal) and all(r['reciprocal_reference_verified'] for r in reciprocal),
            'boss_identity_verified':False,'boss_control_verified':False}
        target=Path(g.state['work'])/'batch-character-metadata.json';v.save(target,report)
        v.save(v.ROOT/'evidence/adaptation/latest-batch-character-metadata.json',report)
        return {'report':str(target),'actor_count':len(objects),'linked_count':len(linked),'class_count':len(metadata),
            'player_controller_pawn_verified':report['player_controller_pawn_verified'],
            'objects':[{'class':r['class'],'references':{k:x['status'] for k,x in r['references'].items()}} for r in objects],
            'failure_count':len(failures)}


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');print(json.dumps(collect(),ensure_ascii=False,indent=2))
