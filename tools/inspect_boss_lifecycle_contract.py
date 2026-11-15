"""用途：只读核对角色生死查询和引擎伤害声明，为自建Boss退出测试准备契约；不调用伤害。"""
import json
from pathlib import Path
import re
import struct
import sys
import official_validation as v
from pbz_readonly import GameRead
from inspect_pbz_ai_metadata import fields, functions


def main():
    wanted={'PBZCharacter','PBZCharacter_Base','PBZCharacter_NPC','SGameCharacter','ApplyDamage'}
    classes=[];damage=[];seen_classes=set()
    with GameRead() as g:
        for index in range(g.count):
            address=g.object(index)
            if not address:continue
            try:
                raw=g.read(address,40);name=g.name(*struct.unpack_from('<II',raw,24))
                if name not in wanted:continue
                kind=g.header(struct.unpack_from('<Q',raw,16)[0])['name'];path=g.path(address)
                if kind=='Function' and path=='/Script/Engine.GameplayStatics.ApplyDamage':
                    damage.append({'path':path,'parameter_bytes':struct.unpack('<H',g.read(address+0x106,2))[0],
                        'parameters':[p for p in fields(g,address,32) if int(p['property_flags'],16)&0x80]})
                elif kind=='Class':
                    # 用途：沿真实继承链读取生死入口，不靠猜测父类名漏掉引擎/项目基类。
                    current=address
                    for _ in range(12):
                        if not current or current in seen_classes:break
                        seen_classes.add(current);parent=g.u64(current+0x40)
                        classes.append({'path':g.path(current),'super':g.path(parent) if parent else None,
                            'properties':[p for p in fields(g,current,512) if re.search(r'health|death|dead|dying|die|alive|attribute',p['name'],re.I)],
                            'functions':[f for f in functions(g,current) if re.search(r'health|death|dead|dying|damage|alive|suicide|kill',f['name'],re.I)]})
                        current=parent
            except (OSError,ValueError,UnicodeError):continue
        enums=[]
        for cls in classes:
            if cls['path']!='/Script/ProjectPBZ.PBZCharacter_NPC':continue
            for fn in cls['functions']:
                if fn['name']!='Kill':continue
                for param in fn['parameters']:
                    if param['type']!='EnumProperty':continue
                    enum=g.u64(int(param['descriptor'],16)+0x78)
                    assert g.path(enum)=='/Script/CharacterBasics.EPBZDieReason','death enum identity mismatch'
                    names,values,count=struct.unpack_from('<QQi',g.read(enum+0x40,24))
                    assert 0<count<128,'bounded UE5_07 enum names required'
                    rows=[{'name':g.name(*struct.unpack('<II',g.read((names&~1)+i*8,8))),
                           'value':struct.unpack('<q',g.read((values&~1)+i*8,8))[0]}for i in range(count)]
                    assert all(row['name'].startswith('EPBZDieReason::')for row in rows),'enum names mismatch'
                    enums.append({'path':g.path(enum),'rows':rows,'parameter':param['name']})
        result={'at':v.utc8(),'pid':g.pid,'classes':classes,'damage':damage,'enums':enums,'gameplay_called':False}
        target=Path(g.state['work'])/'boss-lifecycle-contract.json';v.save(target,result)
    print(json.dumps({'report':str(target),'classes':[{'path':c['path'],'functions':[f['name']for f in c['functions']]}for c in classes],
                     'damage_contracts':len(damage),'gameplay_called':False},ensure_ascii=False,indent=2))


if __name__=='__main__':sys.stdout.reconfigure(encoding='utf-8');main()
