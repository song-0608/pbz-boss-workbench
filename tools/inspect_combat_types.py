"""用途：解析已核对战斗函数引用的结构体和枚举，并核对组件清理的原生查询声明。"""
import json
from pathlib import Path
import struct
import sys
import official_validation as v
from pbz_readonly import GameRead
from inspect_pbz_ai_metadata import fields


def collect():
    with GameRead()as g:
        source=json.loads((Path(g.state['work'])/'combat-native-contract.json').read_text(encoding='utf-8'))
        if source['pid']!=g.pid:raise RuntimeError('Fresh process contract required')
        selected=['FactionComponent','FactionUtils','TargetingComponent']
        properties=[]
        for row in source['classes']:
            if row['path'].rsplit('.',1)[-1]not in selected:continue
            for f in row['functions']:properties.extend(f['parameters'])
        types={};enums={}
        for p in properties:
            if p['type']not in ('StructProperty','ByteProperty','EnumProperty'):continue
            try:
                address=g.u64(int(p['descriptor'],16)+(0x78 if p['type']=='EnumProperty'else 0x70))
                if not address:continue
                h=g.header(address);kind=g.header(h['class'])['name'];path=g.path(address)
                if kind=='ScriptStruct'and path not in types:types[path]={'path':path,'size':g.u32(address+0xa8),'fields':fields(g,address)}
                elif kind=='Enum':enums[path]={'path':path}
            except(OSError,ValueError,UnicodeError):continue
        functions=[]
        for r in g.find_native({'K2_GetComponentsByClass','GetComponentsByClass'}):
            a=int(r['address'],16)
            functions.append({'path':r['path'],'parameter_bytes':struct.unpack('<H',g.read(a+0x106,2))[0],
                'parameters':[p for p in fields(g,a,32)if int(p['property_flags'],16)&0x80]})
        result={'at':v.utc8(),'pid':g.pid,'structs':list(types.values()),'enums':list(enums.values()),'component_functions':functions}
        target=Path(g.state['work'])/'combat-types.json';v.save(target,result)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':sys.stdout.reconfigure(encoding='utf-8');collect()
