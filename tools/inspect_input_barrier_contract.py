"""用途：只读核对空输入屏障的Actor/InputComponent字段，不能仅凭字段名字启用。"""
import json
from pathlib import Path
from pbz_readonly import GameRead
from inspect_pbz_ai_metadata import fields
import official_validation as v


def main():
    with GameRead()as g:
        contracts={}
        for row in g.find_native({'Actor','InputComponent'}):
            if row['path']in('/Script/Engine.Actor','/Script/Engine.InputComponent'):
                contracts[row['path']]={p['name']:p for p in fields(g,int(row['address'],16),256)}
        requirements={'/Script/Engine.Actor':{'bBlockInput':'BoolProperty','InputPriority':'IntProperty','InputComponent':'ObjectProperty'}}
        missing=[]
        for name,ps in requirements.items():
            for prop,kind in ps.items():
                if contracts.get(name,{}).get(prop,{}).get('type')!=kind:missing.append(name+'.'+prop)
        result={'at':v.utc8(),'pid':g.pid,'passed':not missing and '/Script/Engine.InputComponent'in contracts,'missing':missing,
            'input_component_flags_reflected':False,'runtime_consumption_verification_required':True,
            'fields':{name:{p:contracts.get(name,{}).get(p)for p in ps}for name,ps in requirements.items()}}
        path=Path(g.state['work'])/'input-barrier-contract.json';v.save(path,result)
        print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
