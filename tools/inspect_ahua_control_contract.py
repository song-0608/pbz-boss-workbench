"""用途：核对已加载阿花角色与初始化、接管相关声明；不探图、不生成或操作角色。"""
import json
from pathlib import Path
import struct
import sys
import official_validation as v
from pbz_readonly import GameRead
from inspect_pbz_ai_metadata import fields, functions

WANTED={'BP_Monster_AHua_GuiTouDao_C','ActorC_AHua_GuiTouDao','GA_AHua_Skill_01_C',
        'PDA_ActorConfig_C','GameplayStatics','Pawn','PBZCharacter','PBZCharacter_NPC','PBZAIController','Transform'}
FUNCTION_TOKENS=('Init','Spawn','BeginPlay','Possess','ActorInfo','Ability','CharacterName','Destroy','Movement')


def collect():
    selected=[];errors=[]
    with GameRead() as g:
        for index in range(g.count):
            try:
                obj=g.object(index)
                if not obj:continue
                raw=g.read(obj,40);comp,num=struct.unpack_from('<II',raw,24)
                name=g.name(comp,num)
                if name not in WANTED:continue
                cls=struct.unpack_from('<Q',raw,16)[0];kind=g.header(cls)['name'];path=g.path(obj)
                if kind in ('Class','BlueprintGeneratedClass','LegoAbilityBlueprintGeneratedClass','ScriptStruct'):
                    selected.append({'path':path,'index':index,'kind':kind,'super':g.path(g.u64(obj+0x40)),
                        'properties':fields(g,obj),'functions':[f for f in functions(g,obj)
                            if any(token in f['name'] for token in FUNCTION_TOKENS)]})
                elif name=='ActorC_AHua_GuiTouDao':
                    selected.append({'path':path,'index':index,'kind':kind,'class':g.path(cls)})
            except (OSError,ValueError,UnicodeError) as error:
                if len(errors)<12:errors.append({'object_index':index,'type':type(error).__name__})
        report={'at':v.utc8(),'pid':g.pid,'objects':selected,'errors':errors,
                'scope':'Loaded Ahua defaults and specific initialization/control declarations only; no gameplay calls'}
        path=Path(g.state['work'])/'ahua-control-contract.json';v.save(path,report)
        v.save(v.ROOT/'evidence/adaptation/latest-ahua-control-contract.json',report)
        return {'report':str(path),'objects':[{'path':row['path'],'property_count':len(row.get('properties',[])),
            'functions':[f['name'] for f in row.get('functions',[])]} for row in selected],'error_count':len(errors)}


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');print(json.dumps(collect(),ensure_ascii=False,indent=2))
