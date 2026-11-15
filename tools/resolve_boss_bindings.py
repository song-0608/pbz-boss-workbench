"""用途：只读核对Boss绑定所需的名字目录与调用声明；不探图、不生成角色、不修改进度。"""
import json
from pathlib import Path
import struct
import sys
import official_validation as v
from pbz_readonly import GameRead
from pbz_candidate_rules import bride_name_match
from inspect_pbz_ai_metadata import fields, functions

FUNCTIONS = {'GetControlRotation','IsInputKeyDown','GetInputMouseDelta','IsMoveInputIgnored',
             'IsLookInputIgnored','IsGamePaused','K2_CancelAbility','K2_EndAbility',
             'GetAssetsByPath','GetAssetsByPackageName','GetAssetRegistry','GetAsset',
             'AddMovementInput','TryActivateAbilityByClass','Possess','GetViewTarget'}
TYPES = {'Key','GameplayAbilitySpec','GameplayAbility','PlayerController','Controller',
         'AssetRegistryImpl','AssetRegistryHelpers','AssetData','GameplayStatics','Vector','Rotator'}


def collect(names_only=False):
    hits, errors, declarations, registry_instances = [], [], [], []
    with GameRead() as g:
        # 用途：本构建反汇编已确认pool+8是最大块号、+10是块表，条目步长单位为2。
        pool = g.base + 0xdd86ac0
        last = g.u32(pool + 8)
        if not 0 <= last <= 2048: raise ValueError('Unexpected bounded FName block count')
        parsed = 0
        for block in range(last + 1):
            address = g.u64(pool + 0x10 + block * 8)
            data = g.read(address, 65536)
            offset = 0
            while offset + 2 <= len(data):
                header = struct.unpack_from('<H',data,offset)[0]
                length, wide = header >> 6, header & 1
                if length == 0: break # 用途：未使用尾部/未知条目格式立即停止本块，不猜测跨过去。
                size = 2 + length * (2 if wide else 1)
                if offset + size > len(data): break
                try:
                    text=data[offset+2:offset+size].decode('utf-16le' if wide else 'utf-8')
                    if bride_name_match(text) and len(hits) < 8192:
                        comparison=(block << 16) | (offset // 2)
                        if g.name(comparison) != text: raise ValueError('FName crosscheck failed')
                        hits.append({'name':text,'comparison_index':comparison,'runtime_identity_verified':False})
                except (ValueError,UnicodeError) as error:
                    if len(errors)<8: errors.append({'block':block,'offset':offset,'type':type(error).__name__})
                    break
                parsed += 1; offset += (size + 1) & ~1
        # 用途：只收集直接服务于接管、输入和技能结束的声明，不继续扩充无关AI目录。
        if names_only:
            previous=json.loads((Path(g.state['work'])/'boss-binding-evidence.json').read_text(encoding='utf-8'))
            if previous['pid']!=g.pid: raise RuntimeError('Same-process binding declarations required')
            declarations,registry_instances=previous['declarations'],previous['asset_registry_instances']
        for index in range(0 if names_only else g.count):
            try:
                obj=g.object(index)
                if not obj: continue
                raw=g.read(obj,40);comp,num=struct.unpack_from('<II',raw,24)
                name=g.name(comp,num);cls=struct.unpack_from('<Q',raw,16)[0]
                kind=g.header(cls)['name']
                if kind=='AssetRegistryImpl' and len(registry_instances)<4:
                    registry_instances.append({'path':g.path(obj),'index':index})
                if name not in TYPES or kind not in ('Class','ScriptStruct'): continue
                path=g.path(obj)
                if not path.startswith(('/Script/Engine.','/Script/CoreUObject.','/Script/InputCore.',
                    '/Script/GameplayAbilities.','/Script/AssetRegistry.')): continue
                declarations.append({'path':path,'index':index,'kind':kind,'properties':fields(g,obj),
                    'functions':[f for f in functions(g,obj) if f['name'] in FUNCTIONS] if kind=='Class' else []})
            except (OSError,ValueError,UnicodeError) as error:
                if len(errors)<16: errors.append({'object_index':index,'type':type(error).__name__})
        def priority(row):
            name=row['name'];base=name.rsplit('/',1)[-1]
            return (0 if name.startswith('/PBZCombatAsset/ActorData/Mobs/042_AHua/') and base.startswith(('BP_Monster','BP_Boss','BP_AHua')) else
                    1 if '/042_AHua/' in name and base.startswith('ActorC_') else
                    2 if '/042_AHua/' in name and base.startswith('GA_') else 3, name)
        hits.sort(key=priority)
        result={'at':v.utc8(),'pid':g.pid,'fname_blocks':last+1,'fname_entries_parsed':parsed,
            'target_name_clues':hits,'declarations':declarations,'asset_registry_instances':registry_instances,
            'errors':errors,'boss_identity_verified':False,'boss_control_verified':False,
            'scope':'Read-only FName metadata and specific reflected input/ability declarations; no map exploration, spawning, skill activation or save access'}
        target=Path(g.state['work'])/'boss-binding-evidence.json';v.save(target,result)
        v.save(v.ROOT/'evidence/adaptation/latest-boss-binding-evidence.json',result)
        return {'report':str(target),'name_entries':parsed,'name_clues':[r['name'] for r in hits[:35]],
                'declarations':[r['path'] for r in declarations],'registry_instances':registry_instances,'error_count':len(errors)}


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');print(json.dumps(collect('--names-only' in sys.argv),ensure_ascii=False,indent=2))
