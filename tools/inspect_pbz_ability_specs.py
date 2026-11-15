"""用途：经反射描述逐层读取角色标签和已经授予的技能列表，不激活、不授予技能。"""
import json
from pathlib import Path
import struct
import sys
import official_validation as v
from inspect_pbz_ai_metadata import fields
from pbz_readonly import GameRead


def collect():
    report=[];issues=[]
    with GameRead() as g:
        sample=json.loads((v.ROOT/'evidence/adaptation/latest-batch-character-metadata.json').read_text(encoding='utf-8'))
        if sample['pid']!=g.pid:raise RuntimeError('Collect fresh scene references before reading ability specs')
        cache={}
        def find(owner,name):
            seen=set()
            for _ in range(40):
                if not owner or owner in seen:break
                seen.add(owner)
                if owner not in cache:cache[owner]=fields(g,owner)
                p=next((p for p in cache[owner] if p['name']==name),None)
                if p:return p
                owner=g.u64(owner+0x40)
            raise ValueError('Required reflected field missing: '+name)

        def location(base,owner,name,kind):
            p=find(owner,name)
            if p['type']!=kind or p['array_dim']!=1:raise ValueError('Unexpected field declaration')
            offset=int(p['offset'],16);size=g.u32(owner+0xa8)
            if offset<0 or offset+p['element_size']>size:raise ValueError('Field exceeds owner layout')
            return base+offset,p

        def script_struct(p):
            # 用途：+70来自固定源码FStructProperty.Struct；类/数组步长另作运行时交叉核验。
            target=g.u64(int(p['descriptor'],16)+0x70)
            if g.header(g.header(target)['class'])['name']!='ScriptStruct':raise ValueError('Not a reflected script struct')
            return target

        def struct_array(base,owner,name):
            address,p=location(base,owner,name,'ArrayProperty')
            data,count,maximum=struct.unpack('<Qii',g.read(address,16))
            if not 0<=count<=maximum<=512:raise ValueError('Unexpected bounded array size')
            inner=g.u64(int(p['descriptor'],16)+0x78) # 用途：固定源码5_07的FArrayProperty.Inner。
            cls=g.u64(inner+8)
            if g.name(g.u32(cls+0x30),g.u32(cls+0x34))!='StructProperty':raise ValueError('Array inner is not a struct')
            typ=g.u64(inner+0x70);stride=g.u32(inner+0x34)
            if stride!=g.u32(typ+0xa8) or not 0<stride<=4096:raise ValueError('Reflected array stride mismatch')
            if count and not data:raise ValueError('Array data unavailable')
            return data,count,stride,typ

        def name_value(base,owner,name):
            address,p=location(base,owner,name,'NameProperty')
            comp,num=struct.unpack('<II',g.read(address,8));return g.name(comp,num)

        for row in sample['objects']:
            if row['base']!='/Script/ProjectPBZ.PBZCharacter':continue
            address=g.object(row['index'])
            if g.path(address)!=row['path']:raise RuntimeError('Object lifetime changed; reject stale sample')
            cls=g.header(address)['class'];entry={'path':row['path'],'class':row['class']}
            try:entry['character_name']=name_value(address,cls,'CharacterName')
            except (OSError,ValueError,UnicodeError) as error:issues.append({'scope':'character_name','type':type(error).__name__})
            try:
                tags_addr,p=location(address,cls,'CharacterTags','StructProperty');tags_type=script_struct(p)
                data,count,stride,typ=struct_array(tags_addr,tags_type,'GameplayTags')
                entry['character_tags']=[name_value(data+i*stride,typ,'TagName') for i in range(min(count,64))]
            except (OSError,ValueError,UnicodeError) as error:issues.append({'scope':'character_tags','type':type(error).__name__,'reason':str(error)[:120]})
            try:
                ref=row['references']['AbilitySystemComponent']
                if ref['status']!='indexed_uobject':raise ValueError('ASC not verified')
                asc=g.object(ref['index'])
                if g.path(asc)!=ref['path']:raise RuntimeError('ASC lifetime changed')
                ac=g.header(asc)['class'];container,p=location(asc,ac,'ActivatableAbilities','StructProperty')
                typ=script_struct(p);data,count,stride,spec=struct_array(container,typ,'Items')
                abilities=[]
                for i in range(min(count,64)):
                    item=data+i*stride;ability_addr,_=location(item,spec,'Ability','ObjectProperty')
                    ability=g.u64(ability_addr)
                    if not ability:continue
                    h=g.header(ability)
                    abilities.append({'ability':g.path(ability),'class':g.path(h['class'])})
                entry.update({'granted_ability_count':count,'ability_spec_stride':stride,'abilities':abilities})
            except (OSError,ValueError,UnicodeError) as error:
                issues.append({'scope':'ability_specs','type':type(error).__name__,'reason':str(error)[:160]})
            report.append(entry)
        result={'at':v.utc8(),'pid':g.pid,'characters':report,'issues':issues,
            'scope':'Read reflected existing gameplay tags and granted ability specs; no activation, spawning or writes',
            'boss_identity_verified':False,'boss_control_verified':False}
        target=Path(g.state['work'])/'character-ability-specs.json';v.save(target,result)
        v.save(v.ROOT/'evidence/adaptation/latest-character-ability-specs.json',result)
        return {'report':str(target),'characters':report,'issues':issues}


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');print(json.dumps(collect(),ensure_ascii=False,indent=2))
