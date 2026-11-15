"""用途：只读寻找用户指定新娘阿花的已加载类/资产线索；不把名称命中当成Boss身份。"""
import json
from pathlib import Path
import struct
import sys
import official_validation as v
from pbz_readonly import GameRead
from pbz_candidate_rules import bride_name_match, npc_lineage, useful_character_class


def collect():
    clues, classes, failures, instances = [], [], [], []
    with GameRead() as g:
        lineage_cache = {}
        def lineage(address):
            # 用途：有界追溯真实父类；只在本次只读采样中缓存字符串，不跨进程复用地址。
            if address not in lineage_cache:
                paths, visited = [], set()
                current = address
                for _ in range(24):
                    if not current or current in visited: break
                    visited.add(current); paths.append(g.path(current))
                    current = g.u64(current + 0x40)
                lineage_cache[address] = paths
            return lineage_cache[address]
        for index in range(g.count):
            try:
                obj=g.object(index)
                if not obj: continue
                raw=g.read(obj,40);comp,num=struct.unpack_from('<II',raw,24)
                name=g.name(comp,num);cls=struct.unpack_from('<Q',raw,16)[0]
                kind=g.header(cls)['name']
                is_class = kind in ('Class','BlueprintGeneratedClass')
                ancestry = lineage(obj if is_class else cls) if is_class or kind.endswith('_C') or 'NPC' in kind else []
                is_npc = npc_lineage(ancestry)
                if not bride_name_match(name) and not is_class and not is_npc: continue
                path=g.path(obj)
                if not path.startswith(('/Game/','/PBZCombatAsset/','/Script/ProjectPBZ.')): continue
                if bride_name_match(path):
                    clues.append({'path':path,'index':index,'kind':kind,'class':g.path(cls),
                                  'npc_ancestry':is_npc,'runtime_instance':'.PersistentLevel.' in path})
                if is_class and useful_character_class(path, ancestry):
                    classes.append({'path':path,'index':index,'super':ancestry[1] if len(ancestry)>1 else '',
                                    'npc_ancestry':is_npc,'target_name_clue':bride_name_match(path)})
                if not is_class and is_npc and '.PersistentLevel.' in path:
                    instances.append({'path':path,'index':index,'class':g.path(cls),
                                      'target_name_clue':bride_name_match(path) or bride_name_match(g.path(cls))})
            except (OSError,ValueError,UnicodeError) as error:
                if len(failures)<12:failures.append({'index':index,'type':type(error).__name__})
        clues.sort(key=lambda row:(not row['npc_ancestry'],not row['runtime_instance'],row['path']))
        classes.sort(key=lambda row:(not row['target_name_clue'],not row['npc_ancestry'],row['path']))
        instances.sort(key=lambda row:(not row['target_name_clue'],row['path']))
        result={'at':v.utc8(),'pid':g.pid,'target_boss':'新娘阿花','candidate_name_matches':clues[:160],
            'loaded_actor_data_classes':classes[:80],'loaded_npc_instances':instances[:256],'failures':failures,
            'counts_before_output_limits':{'name_matches':len(clues),'character_classes':len(classes),'npc_instances':len(instances)},
            'scope':'Bounded loaded UE metadata only; no writes, spawns, function calls or save parsing',
            'boss_identity_verified':False,'boss_control_verified':False}
        path=Path(g.state['work'])/'bride-candidate-catalog.json';v.save(path,result)
        v.save(v.ROOT/'evidence/adaptation/latest-bride-candidates.json',result)
        return {'report':str(path),'counts':result['counts_before_output_limits'],
                'target_npc_instances':[r for r in instances if r['target_name_clue']][:8],
                'character_class_examples':[r['path'] for r in classes[:12]],
                'identity_verified':False}

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');print(json.dumps(collect(),ensure_ascii=False,indent=2))
