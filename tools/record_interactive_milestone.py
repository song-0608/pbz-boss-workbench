"""用途：只解析已完成的保护后实机记录，分开记录按键成功、伤害和仍未验收的部分。"""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def collect():
    pointer = json.loads((ROOT / 'runtime/latest-official-validation.json').read_text(encoding='utf-8'))
    state = json.loads(Path(pointer['state_file']).read_text(encoding='utf-8'))
    work = Path(state['work'])
    log_path = work / 'UE4SS.log'
    text = log_path.read_text(encoding='utf-8', errors='replace')
    # 用途：只使用最后一次角色实验，不能把前一轮失败或死亡的记录拼到通过的一轮。
    segment = text[text.rfind('PBZ_CONTROL_LIFECYCLE:DEFERRED_ACTOR='):]
    post = json.loads((ROOT / 'evidence/latest-native-diagnostic-postcheck.json').read_text(encoding='utf-8'))
    if not state.get('restored') or post['validation_state'] != state['state_file']:
        raise RuntimeError('Matching finished session and postcheck required')
    actions = {name: bool(re.search(r'\[PBZBossControl\] ' + name + r' success=true\b', segment))
               for name in ('enter', 'slot1', 'heavy_01', 'skill_02', 'dash', 'exit', 'stop')}
    required = {'input_barrier': 'INPUT_BARRIER_CONSTRUCTED=true',
                'player_position_unchanged': 'ORIGINAL_PLAYER_POSITION_DELTA=0.0',
                'player_no_new_active_ability': 'ORIGINAL_PLAYER_NEW_ACTIVE_COUNT=0',
                'bounded_cleanup_reached': 'INTERACTIVE_END=bounded input probe complete'}
    checks = {key: 'PBZ_CONTROL_LIFECYCLE:' + token in segment for key, token in required.items()}
    passed = (all(actions.values()) and all(checks.values()) and post['research_box_empty']
              and post['research_loader_removed'] and not post['formal_files_changed']
              and not post['host_config_files_changed'] and post['host_registry_unchanged'])
    result = {'session': state['state_file'], 'log_sha256': hashlib.sha256(log_path.read_bytes()).hexdigest(),
              'passed': bool(passed), 'actions': actions, 'checks': checks,
              'formal_file_count': post['formal_file_count'], 'formal_files_changed': post['formal_files_changed'],
              'research_box_empty': post['research_box_empty'],
              'research_loader_removed': post['research_loader_removed'],
              'health_evidence': 'player protection restoration verifies captured health; no standalone health value in interactive log',
              'skill_damage_evidence': 'See earlier paired per-skill remote-control milestone; interactive key success alone is not a damage measurement',
              'remaining': ['camera component unregistration / garbage collection', 'death and map transition full runtime acceptance',
                            'all Ahua skills and additional bosses', 'new practice launcher runtime acceptance'],
              'complete_all_boss_mod': False}
    if not passed:
        raise RuntimeError('Final protected interactive segment did not satisfy evidence requirements')
    target = ROOT / 'evidence/adaptation/ahua-protected-interactive-milestone.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': passed, 'report': str(target), 'actions': actions}, ensure_ascii=False))
    return result


if __name__ == '__main__':
    collect()
