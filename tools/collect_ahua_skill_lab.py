"""用途：保存本批真实技能结果与失败，核对收尾；没有通过的招式不会自动进入玩家版。"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ('attack_01', 'skill_04', 'skill_06', 'special_05_a')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prior', action='append', default=[], help='本批先前研究会话的目录名')
    args = parser.parse_args()
    owner = read(ROOT / 'runtime/ahua-practice.json')
    state = read(Path(owner['state_file']))
    post = read(ROOT / 'evidence/latest-native-diagnostic-postcheck.json')
    local = read(ROOT / 'evidence/adaptation/ahua-delivery-local-checks.json')
    if (not state.get('restored') or post['validation_state'] != owner['state_file']
            or post['formal_files_changed'] or post['host_config_files_changed']
            or not post['research_box_empty'] or not post['research_loader_removed']
            or not post['host_registry_unchanged'] or not local['passed']):
        raise RuntimeError('Matching completed session, clean formal files and local checks required')
    for name, expected in local['source_sha256'].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError('Source changed after local checks: ' + name)
    work = Path(state['work'])
    (work / 'postcheck.json').write_text(json.dumps(post, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    sessions = []
    directories = []
    for name in args.prior:
        if not re.fullmatch(r'\d{8}-\d{6}', name):
            raise ValueError('Exact evidence session directory name required')
        directories.append(ROOT / 'evidence/official-validation' / name)
    directories.append(work)
    for directory in directories:
        check = read(directory / 'postcheck.json')
        if check['formal_files_changed'] or not check['research_box_empty'] or not check['research_loader_removed']:
            raise RuntimeError('Prior session cleanup not verified: ' + str(directory))
        path = directory / 'UE4SS.log'
        text = path.read_text(encoding='utf-8', errors='replace')
        action_path = directory / 'expanded-actions.json'
        actions = read(action_path) if action_path.exists() else []
        rows = []
        pattern = (r'KEY_SKILL_END=(\w+)\|peak=(\d+)\|active=(\d+)\|natural=(true|false)'
                   r'\|health_before=([\d.-]+)\|health_after=([\d.-]+)\|distance=([\d.eE+-]+)')
        for skill, peak, active, natural, before, after, delta in re.findall(pattern, text):
            rows.append({'id': skill, 'peak': int(peak), 'active_after': int(active),
                         'natural_finish': natural == 'true', 'health_before': float(before),
                         'health_after': float(after), 'position_delta': float(delta),
                         'damage_observed_in_window': float(before) > float(after)})
        sessions.append({'directory': str(directory), 'log_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                         'samples': rows,
                         'attempted': re.findall(r'KEY_SKILL_BEGIN=(\w+)\|', text),
                         'brain_pause_reassertions': re.findall(r'PBZ_REMOTE_MAINTAIN:BRAIN_REASSERT=(\d+)', text),
                         'entered': 'enter success=true state=ACTIVE' in text,
                         'exited': 'exit success=true state=OFF' in text,
                         'original_player_stationary_at_exit': 'ORIGINAL_PLAYER_POSITION_DELTA=0.0' in text,
                         'original_player_no_new_active_at_exit': 'ORIGINAL_PLAYER_NEW_ACTIVE_COUNT=0' in text,
                         'skill06_active_cancel_verified': any(r.get('action') == 'interrupt06'
                             and r.get('active_skill06_cancelled') is True for r in actions),
                         'issues': [line for line in text.splitlines() if any(s in line for s in (
                             'state=FAULTED', 'PBZ_REMOTE_VERIFY:FAILED=', 'INITIALIZATION_ATTEMPT_REJECTED=', 'ISSUE_', 'CANCEL_RESULT=false'))],
                         'formal_file_count': check['formal_file_count'], 'formal_changed_count': 0,
                         'research_box_empty': True, 'research_loader_removed': True})
    conclusions = {}
    for candidate in CANDIDATES:
        samples = [r for s in sessions for r in s['samples'] if r['id'] == candidate]
        conclusions[candidate] = {'attempted': any(candidate in s['attempted'] for s in sessions),
                                  'sample_count': len(samples),
                                  'natural_finish_observed': any(r['peak'] > 0 and r['natural_finish'] for r in samples),
                                  'damage_observed_in_window': any(r['damage_observed_in_window'] for r in samples),
                                  'automatically_released': False}
    result = {'at': datetime.now().astimezone().isoformat(), 'sessions': sessions, 'candidates': conclusions,
              'collection_complete': True, 'complete_all_boss_mod': False,
              'candidate_release_requires_separate_review': True,
              'current_assembly_deployment': read(work / 'control-lifecycle-deployment.json'),
              'local_checks': 'evidence/adaptation/ahua-delivery-local-checks.json'}
    output = ROOT / 'evidence/adaptation/ahua-skill-lab-milestone.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'report': str(output), 'candidates': conclusions, 'game_sessions': len(sessions)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
