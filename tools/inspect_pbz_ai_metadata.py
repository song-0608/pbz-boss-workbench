"""用途：只读筛选游戏 AI/角色相关反射类；不调用函数、不枚举存档内容。"""
import json
from pathlib import Path
import re
import struct
import sys
import official_validation as v
from pbz_readonly import GameRead


def fields(g, owner, maximum=160):
    """用途：按已验证的 FField 链读取属性声明，不读取对应实例的业务数据。"""
    pointer = g.u64(owner + 0x50)
    result, seen = [], set()
    while pointer and len(result) < maximum:
        if pointer in seen:
            raise RuntimeError('Property chain cycle')
        seen.add(pointer)
        raw = g.read(pointer, 0x50)
        cls = struct.unpack_from('<Q', raw, 8)[0]
        comp, num = struct.unpack_from('<II', raw, 0x20)
        result.append({'name':g.name(comp,num),
            'descriptor':hex(pointer),
            'type':g.name(g.u32(cls+0x30),g.u32(cls+0x34)),
            # 用途：沿用本项目已成功运行Lua的5_07布局；旧工具误用了5_00字段偏移。
            # 这些是属性声明的位置；具体实例引用仍须独立核验，不能仅凭名称调用。
            'array_dim':struct.unpack_from('<i',raw,0x30)[0],
            'element_size':struct.unpack_from('<i',raw,0x34)[0],
            'property_flags':hex(struct.unpack_from('<Q',raw,0x38)[0]),
            'offset':hex(struct.unpack_from('<i',raw,0x44)[0])})
        pointer = struct.unpack_from('<Q',raw,0x10)[0]
    return result


def functions(g, owner):
    """用途：只读取函数名和参数声明；名称存在不代表已能安全执行。"""
    pointer=g.u64(owner+0x48)
    result,seen=[],set()
    while pointer and len(seen)<256:
        if pointer in seen:raise RuntimeError('Function chain cycle')
        seen.add(pointer)
        h=g.header(pointer)
        kind=g.header(h['class'])['name']
        if kind in ('Function','DelegateFunction','SparseDelegateFunction'):
            result.append({'name':h['name'],'flags':hex(g.u32(pointer+0x100)),
                'parameter_count':g.read(pointer+0x104,1)[0],
                'parameter_bytes':struct.unpack('<H',g.read(pointer+0x106,2))[0],
                'return_offset':struct.unpack('<H',g.read(pointer+0x108,2))[0],
                'parameters':fields(g,pointer,32)})
        pointer=g.u64(pointer+0x28)
    return result


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    # 用途：关键词只筛选已确认的 UE 类元数据；不进行任意内存字串搜索。
    wanted=re.compile(r'boss|enemy|character|pawn|brain|skill|ability|hate|aggro|threat|target|player|controller|blackboard|behavior|save|checkpoint',re.I)
    classes, packages, failures, candidates = [], set(), 0, []
    with GameRead() as g:
        for index in range(g.count):
            try:
                address=g.object(index)
                if not address:continue
                raw=g.read(address,40)
                cls=struct.unpack_from('<Q',raw,0x10)[0]
                kind=g.header(cls)['name']
                if kind not in ('Class','BlueprintGeneratedClass','AnimBlueprintGeneratedClass','WidgetBlueprintGeneratedClass'):continue
                comp,num=struct.unpack_from('<II',raw,0x18)
                name=g.name(comp,num)
                if not wanted.search(name):continue
                path=g.path(address)
                if not path.startswith(('/Script/','/Game/')):continue
                if path.startswith('/Script/'):
                    packages.add(path.split('.',1)[0])
                if path.startswith(('/Script/Engine.','/Script/AIModule.','/Script/UMG.','/Script/GameplayAbilities.')):continue
                candidates.append({'path':path,'index':index,'class_kind':kind,'address':address})
            except (OSError,ValueError,UnicodeError):
                failures+=1
        # 用途：先完成筛选再优先读取游戏相关类，避免前面的引擎插件占满数量上限。
        def priority(row):
            p=row['path']
            return (0 if p.startswith(('/Script/ProjectPBZ.','/Script/PBZ.')) else
                    1 if p.startswith('/Game/') else
                    2 if p.startswith(('/Script/SGame','/Script/Lego')) else 3,
                    0 if re.search('boss|enemy|threat|aggro',p,re.I) else 1,p)
        for row in sorted(candidates,key=priority)[:160]:
            address=row['address']
            classes.append({k:val for k,val in row.items() if k!='address'} |
                {'size':g.u32(address+0xa8),'super':g.path(g.u64(address+0x40)),
                 'own_properties':fields(g,address),'own_functions':functions(g,address)})
        report={'at':v.utc8(),'pid':g.pid,'object_count':g.count,'classes':classes,'candidate_class_count':len(candidates),
            'related_script_packages':sorted(packages),'unreadable_or_invalid_metadata':failures,
            'scope':'UE class and property declarations only; no game function calls, gameplay, save parsing or memory writes',
            'boss_identity_verified':False,'boss_control_verified':False}
        target=Path(g.state['work'])/'ai-class-metadata.json'
        v.save(target,report);v.save(v.ROOT/'evidence/adaptation/latest-ai-class-metadata.json',report)
        print(json.dumps({'report':str(target),'selected_class_count':len(classes),
            'examples':[{'path':r['path'],'property_count':len(r['own_properties'])} for r in classes[:18]]},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
