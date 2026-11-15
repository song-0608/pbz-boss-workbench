"""只读核对原生GAS效果接口；不激活能力、不写属性、不调用伤害。"""
import json
from pathlib import Path
import re
import struct
import sys
from inspect_pbz_ai_metadata import fields, functions
from pbz_readonly import GameRead
import official_validation as v


def property_schema(g, pointer, depth=0):
    raw = g.read(pointer, 0x50)
    cls = struct.unpack_from('<Q', raw, 8)[0]
    result = {'name': g.name(*struct.unpack_from('<II', raw, 0x20)), 'descriptor': hex(pointer),
              'type': g.name(g.u32(cls + 0x30), g.u32(cls + 0x34)),
              'element_size': struct.unpack_from('<i', raw, 0x34)[0]}
    if depth>=4:
        return result
    if result['type'] == 'StructProperty':
        owner = g.u64(pointer + 0x70)
        assert g.header(g.header(owner)['class'])['name'] == 'ScriptStruct'
        result.update(struct_path=g.path(owner), fields=[dict(p, schema=property_schema(g,int(p['descriptor'],16),depth+1))
            for p in fields(g,owner,128)])
    if result['type'] == 'MapProperty':
        result['key'] = property_schema(g, g.u64(pointer + 0x70), depth+1)
        result['value'] = property_schema(g, g.u64(pointer + 0x78), depth+1)
    if result['type']=='ArrayProperty':
        # UE5_07: ArrayFlags=0x70, Inner=0x78 (not the struct/map member position).
        result['inner']=property_schema(g,g.u64(pointer+0x78),depth+1)
    return result


def collect():
    names={'PBZGameplayAbility','PBZAbilityBlueprintLibrary','AbilitySystemComponent','PBZAttributeSet','GameplayAbility',
           'SGameLegoAbility','LegoAbility','SGameCharacter','SGameAbilitySystemComponent','DamageComponent','SGameDamageComponent'}
    with GameRead() as g:
        # 只筛选原生注册区的战斗元类，找到本构建实际伤害入口，避免猜类名或借用旧PBZ能力基类。
        for index in range(min(g.count,75000)):
            obj=g.object(index)
            if not obj:continue
            try:
                raw=g.read(obj,40)
                name=g.name(*struct.unpack_from('<II',raw,24))
                if re.search(r'damage|effect|combat|hit|attribute|attack',name,re.I) and g.header(g.u64(obj+16))['name']=='Class':
                    if g.path(obj).startswith(('/Script/ProjectPBZ.','/Script/SGame')):
                        names.add(name)
            except(OSError,ValueError,UnicodeError):continue
        classes=[]
        for row in g.find_native(names,('/Script/ProjectPBZ.','/Script/GameplayAbilities.','/Script/SGame',
                                        '/Script/LegoAbility.','/Script/SGameCharacter.')):
            address=int(row['address'],16)
            if g.header(g.header(address)['class'])['name']!='Class':
                continue
            declarations=[f for f in functions(g,address) if re.search('effect|damage|attribute|health|hit|attack',f['name'],re.I)
                          or re.search('damage|combat.*holder',row['path'],re.I)]
            for fn in declarations:
                for param in fn['parameters']:
                    if param['type']=='StructProperty':
                        # 本仓库UE5_07生成布局：FStructProperty.Struct=0x70；0x78是总大小。
                        struct_address=g.u64(int(param['descriptor'],16)+0x70)
                        assert g.header(g.header(struct_address)['class'])['name']=='ScriptStruct','parameter struct identity required'
                        param['struct_path']=g.path(struct_address)
                        param['struct_fields']=fields(g,struct_address,128)
            properties=fields(g,address,256)
            for prop in properties:
                if prop['name']=='EffectsLibrary':
                    prop['schema']=property_schema(g,int(prop['descriptor'],16))
            classes.append({'path':row['path'],'properties':properties,'functions':declarations})
        result={'at':v.utc8(),'pid':g.pid,'classes':classes,'gameplay_called':False}
        target=Path(g.state['work'])/'ability-damage-native-contract.json'
        v.save(target,result)
        print(json.dumps({'report':str(target),'classes':[{'path':c['path'],'functions':[
            {'name':f['name'],'parameters':[(p['name'],p['type'],p['offset'],p.get('struct_path'))
                for p in f['parameters']]} for f in c['functions']]} for c in classes]},ensure_ascii=False,indent=2))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    collect()
