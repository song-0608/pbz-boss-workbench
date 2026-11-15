"""用途：整理同一游戏线程已只读导出的精确连招子树；不激活能力、不解读存档。"""
import hashlib
import json
from pathlib import Path
import re
import sys
import official_validation as v

TREE = '/PBZCombatAsset/ActorData/Mobs/042_AHua/BehaviorTree/GuiTouDao/BT_AHua_TeleportAttack_01.BT_AHua_TeleportAttack_01'
PREFIX = 'PBZ_ATTACK_CONTRACT:'


def parse_contract(text):
    """用途：只接受最后一轮完整导出；节点引用只表示声明关系，不代表实际执行顺序。"""
    start = text.rfind(PREFIX + 'CLASS=BlueprintGeneratedClass /PBZCombatAsset/ActorData/Mobs/042_AHua/Ability/GuiTouDao/Abilities/New/GA_AHua_Attack_01.')
    segment = text[start:] if start >= 0 else ''
    if PREFIX + 'READY=classes only; no ability activation' not in segment or PREFIX + 'REJECTED=' in segment:
        raise ValueError('No complete current contract block')
    trees = re.findall(PREFIX + r'COMBO_TREE=BehaviorTree ([^|\r\n]+)\|weight=([^\r\n]+)', segment)
    if len(trees) != 1 or trees[0][0] != TREE:
        raise ValueError('Exact known combo tree required')
    nodes = re.findall(PREFIX + r'TREE_NODE=([^\r\n]+)', segment)
    if not 1 <= len(nodes) <= 128:
        raise ValueError('Nonempty bounded node list required')
    if any(not n.partition(' ')[2].startswith(TREE + ':') for n in nodes):
        raise ValueError('Foreign node refused')
    refs = []
    for node, prop, value in re.findall(PREFIX + r'NODE_REF=([^|\r\n]+)\|([^|\r\n]+)\|([^\r\n]+)', segment):
        if node not in nodes:
            raise ValueError('Reference owner is not a declared node')
        refs.append({'node': node, 'property': prop, 'value': value})
    leaves = sorted({r['value'].partition(' ')[2] for r in refs if r['property'] == 'AbilityToActivate'})
    if not leaves or any(not p.startswith('/PBZCombatAsset/ActorData/Mobs/042_AHua/Ability/') for p in leaves):
        raise ValueError('Expected Ahua leaf ability references required')
    return {'tree': TREE, 'weight': float(trees[0][1]), 'nodes': nodes,
            'references': refs, 'leaf_abilities': leaves,
            'execution_order_proven': False, 'ability_activation_performed': False}


def main():
    state = json.loads(v.state_path().read_text(encoding='utf-8'))
    if state.get('restored') or not state.get('offline_validation') or state.get('network_active'):
        raise RuntimeError('Live offline research state required')
    v.verify_build(state['ue4ss_loader_manifest'])
    row = next(r for r in state['ue4ss_loader_manifest'] if r['physical_path'].endswith('UE4SS.dll'))
    log = Path(row['physical_path']).parent / 'UE4SS.log'
    raw = log.read_bytes()
    result = {'at': v.utc8(), **parse_contract(raw.decode('utf-8', errors='replace')),
              'source_log_sha256': hashlib.sha256(raw).hexdigest(),
              'scope': 'same-thread reflected CDO map and tree node references; no gameplay activation'}
    work = Path(state['work'])
    (work / 'attack-readonly-evidence.log').write_bytes(raw)
    v.save(work / 'ahua-combo-tree-contract.json', result)
    v.save(v.ROOT / 'evidence/adaptation/latest-ahua-combo-tree-contract.json', result)
    print(json.dumps({'node_count': len(result['nodes']), 'leaf_abilities': result['leaf_abilities']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    main()
