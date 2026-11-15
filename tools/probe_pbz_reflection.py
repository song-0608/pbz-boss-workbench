"""用途：只读核对少量已命名引擎类的成员候选，不执行反射函数或写内存。"""
import json
from pathlib import Path
import struct
import sys
import official_validation as v
from pbz_readonly import GameRead


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    targets={'Actor','KismetStringLibrary','Conv_NameToString','Class','Struct','Function','Default__KismetStringLibrary','Object','Vector','Pawn','Character'}
    out=[]
    with GameRead() as g:
        objects=g.find_native(targets)
        for h in objects:
            if h['path'] not in ('/Script/Engine.Actor','/Script/Engine.KismetStringLibrary','/Script/CoreUObject.Class',
                    '/Script/CoreUObject.Struct','/Script/CoreUObject.Function','/Script/Engine.KismetStringLibrary.Conv_NameToString',
                    '/Script/Engine.Pawn','/Script/Engine.Character'):continue
            address=int(h['address'],16);fields=[];raw=g.read(address,0x220)
            for offset in range(0x28,len(raw),8):
                pointer=struct.unpack_from('<Q',raw,offset)[0]
                if not pointer:continue
                row={'offset':hex(offset),'value':hex(pointer)}
                try:row['uobject_path']=g.path(pointer)
                except (OSError,ValueError,UnicodeError):
                    try:
                        field=g.read(pointer,0x30);cls=struct.unpack_from('<Q',field,8)[0]
                        clname=g.name(g.u32(cls))
                        if clname.endswith('Property'):
                            comp,num=struct.unpack_from('<II',field,0x20)
                            row.update({'ffield_name':g.name(comp,num),'ffield_class':clname,'next':hex(struct.unpack_from('<Q',field,0x18)[0]),
                                        'ffield_dwords':{hex(i):hex(struct.unpack_from('<I',g.read(pointer,0x90),i)[0]) for i in range(0,0x90,4)}})
                    except (OSError,ValueError,UnicodeError):pass
                if 'uobject_path' in row or 'ffield_name' in row:fields.append(row)
            out.append({'path':h['path'],'address':h['address'],'class_path':g.path(h['class']),
                'dwords':{hex(i):hex(struct.unpack_from('<I',raw,i)[0]) for i in range(0x40,0x180,4)},'identified_pointer_fields':fields})
        report={'at':v.utc8(),'pid':g.pid,'scope':'Targeted native UE reflection metadata only; read-only; no gameplay','objects':out,
                'selected_objects':objects,'passed':len(out)>=6}
        work=Path(g.state['work']);v.save(work/'reflection-layout-probe.json',report)
        v.save(v.ROOT/'evidence/adaptation/latest-reflection-layout-probe.json',report)
    print(json.dumps({'report':str(work/'reflection-layout-probe.json'),'selected':[{'path':r['path'],'fields':r['identified_pointer_fields']} for r in out]},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
