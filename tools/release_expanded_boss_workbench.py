"""Publish only after exact experience, independent profiles and ordinary World acceptance."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path

from boss_adaptation_workflow import ROOT, sha, write_json
from collect_expanded_boss_player import collect, historical_profile_base
from mod_installation import MANIFEST, assert_closed, validate_package
import build_expanded_boss_candidate as candidate
from four_boss_integration_workflow import modules


def release(package, session, flow, offline, world_sessions=()):
    with historical_profile_base(package):
        return _release(package, session, flow, offline, world_sessions)


def _release(package, session, flow, offline, world_sessions=()):
    assert_closed()
    manifest = candidate.verify(package)
    checked = json.loads(offline.read_bytes())
    assert checked['passed'] and all(row['passed'] for row in checked['checks'])
    assert checked['candidate'] == str(package) and checked['workflow'] == str(flow)
    assert checked['candidate_manifest_sha256'] == sha(package / MANIFEST)
    assert checked['workflow_manifest_sha256'] == sha(flow / 'manifest.json')
    assert all(sha(ROOT / name) == digest for name, digest in checked['source_files'].items())
    accepted_path, accepted = collect(session, flow, world_sessions)
    assert accepted['passed'] and accepted['candidate_manifest_sha256'] == sha(package / MANIFEST)
    assert [row['id'] for row in accepted['roles']] == [row['id'] for row in manifest['expansion_profiles']]
    payload = {name:(package / name).read_bytes() for name in manifest['files']}
    count = len(manifest['bosses'])
    descriptions = '；'.join(row['name'] + str(row['abilities']) + '项' for row in manifest['bosses'])
    payload['PBZBossControl/README.md'] = (
        '# Boss 工作台 v5\n\n当前核定PBZ构建的本机隔离离线版。' + descriptions + '。\n\n'
        'Insert 打开画面中的角色工作台，↑↓选择、Enter确认；F6接管、F10恢复主角。'
        '中键切换镜头锁敌，F7请求切换目标。支持WASD与Shift组合施法；保留游戏原生技能条件。\n\n'
        '弦儿当前仅开放已验证的两项原生闪避，攻击招式仍待适配；不把闪避记作伤害能力。'
        '选择界面使用不抢焦点的Windows覆盖层。联机暂停。详见74-Boss工作台v5操作说明.md。\n'
        '升级后可运行 tools/verify_boss_workbench_v5.py；历史验收固定核对其原始v4依赖与完整摘要。\n'
    ).encode('utf-8')
    files = {name:hashlib.sha256(data).hexdigest() for name, data in sorted(payload.items())}
    identifier = 'ahua-boss-workbench-v5-' + hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()[:16]
    target = ROOT / 'releases' / identifier
    report_path = ROOT / 'evidence/releases' / (identifier + '-acceptance.json')
    assert not target.exists() and not report_path.exists(), 'Preserve immutable releases'
    report = dict(schema=1, passed=True, release_id=identifier, at=datetime.now().astimezone().isoformat(),
        candidate=str(package), candidate_manifest_sha256=sha(package / MANIFEST),
        ordinary_acceptance=accepted_path.relative_to(ROOT).as_posix(), ordinary_acceptance_sha256=sha(accepted_path),
        ordinary_session=session, world_sessions=accepted['world_sessions'],
        offline=offline.relative_to(ROOT).as_posix(), offline_sha256=sha(offline),
        experience_acceptance=manifest['experience_acceptance'],
        experience_acceptance_sha256=manifest['experience_acceptance_sha256'],
        expansion_profiles=manifest['expansion_profiles'], module_source_sha256=modules(manifest),
        bosses=manifest['bosses'], ability_count=manifest['ability_count'], skill_binding_count=manifest['skill_binding_count'],
        held_key_focus_release_verified=False, native_umg=False, networking_enabled=False,
        publication_source_sha256=sha(ROOT / 'tools/release_expanded_boss_workbench.py'))
    write_json(report_path, report)
    target.mkdir(parents=True)
    for name, data in payload.items():
        output = target / name; output.parent.mkdir(parents=True, exist_ok=True); output.write_bytes(data)
    manifest.update(release_id=identifier, at=report['at'], status='release', complete_mod=True, runtime_acceptance_current=True,
        integration_only=False, experience_runtime_verified=True, files=files, pending=[],
        acceptance_report=report_path.relative_to(ROOT).as_posix(), acceptance_report_sha256=sha(report_path),
        accepted_candidate=package.name, new_playable_bosses=len(accepted['roles']),
        future_scope=['additional Boss phases and attacks', 'held-key focus-loss runtime verification', 'native UMG selector', 'networking'])
    write_json(target / MANIFEST, manifest)
    assert modules(validate_package(target)) == modules(candidate.verify(package))
    return dict(release=str(target), release_id=identifier, bosses=count,
                abilities=manifest['ability_count'], bindings=manifest['skill_binding_count'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('candidate', type=Path)
    parser.add_argument('session'); parser.add_argument('workflow', type=Path); parser.add_argument('offline', type=Path)
    parser.add_argument('--world-session', action='append', default=[])
    args = parser.parse_args()
    print(json.dumps(release(args.candidate.resolve(), args.session, args.workflow.resolve(), args.offline.resolve(), args.world_session), ensure_ascii=False))
