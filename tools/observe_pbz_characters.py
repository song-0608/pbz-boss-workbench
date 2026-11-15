"""用途：只读辨识研究副本中的角色实例与控制器，不接管、不执行技能。"""
import json
from pathlib import Path
import struct
import sys
import official_validation as v
from pbz_readonly import GameRead
from inspect_pbz_ai_metadata import fields


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    with GameRead() as g:
        native=g.find_native({'PBZCharacter','PBZCharacter_Player','PBZPlayerController'})
        bases={int(h['address'],16):h['path'] for h in native if h['path'] in
            ('/Script/ProjectPBZ.PBZCharacter','/Script/ProjectPBZ.PBZPlayerController')}
        if len(bases)!=2:raise RuntimeError('Required native character/controller classes unavailable')
        ancestry={};declarations={};objects=[]
        def classify(cls):
            if cls in ancestry:return ancestry[cls]
            visited=[];current=cls;found=None
            for _ in range(40):
                if not current:break
                if current in bases:found=bases[current];break
                if current in visited:raise RuntimeError('Class inheritance cycle')
                visited.append(current);current=g.u64(current+0x40)
            for p in visited:ancestry[p]=found
            return found
        for index in range(g.count):
            try:
                address=g.object(index)
                if not address:continue
                raw=g.read(address,40);flags=struct.unpack_from('<I',raw,8)[0]
                if flags&0x30:continue # 用途：排除默认对象和原型，避免把模板当场景角色。
                cls=struct.unpack_from('<Q',raw,0x10)[0];base=classify(cls)
                if not base:continue
                links={};current=cls
                for _ in range(24):
                    if not current:break
                    if current not in declarations:declarations[current]=fields(g,current)
                    for p in declarations[current]:
                        if p['name'] not in ('Controller','Pawn','CharacterMovement','BrainComponent','AbilitySystemComponent','ModularFeatureManager'):continue
                        if p['type'] not in ('ObjectProperty','ObjectPtrProperty'):continue
                        pointer=g.u64(address+int(p['offset'],16))
                        try:links[p['name']]=g.path(pointer) if pointer else None
                        except (OSError,ValueError,UnicodeError):links[p['name']]='invalid_reference_or_unverified_layout'
                    current=g.u64(current+0x40)
                objects.append({'path':g.path(address),'class':g.path(cls),'base':base,'index':index,'links':links})
                if len(objects)>=40:break
            except (OSError,ValueError,UnicodeError):continue
        report={'at':v.utc8(),'pid':g.pid,'scope':'Bounded read-only UE character/controller metadata and object references',
            'objects':objects,'property_reference_decoding_verified':False,
            'boss_identity_verified':False,'boss_control_verified':False}
        target=Path(g.state['work'])/'live-character-observation.json';v.save(target,report)
        print(json.dumps({'report':str(target),'object_count':len(objects),'objects':objects[:12]},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
