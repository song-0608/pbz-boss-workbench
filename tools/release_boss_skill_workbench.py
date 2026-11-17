"""Publish the skill expansion only after closed native and ordinary acceptance."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import build_boss_skill_workbench as builder
from boss_adaptation_workflow import ROOT,sha,write_json
from boss_skill_player_acceptance import collect
from four_boss_integration_workflow import modules
from mod_installation import MANIFEST,assert_closed,validate_package

OFFLINE='evidence/adaptation/boss-skills-v4-offline.json'
TESTS=('test_boss_skill_workbench','test_boss_skill_campaign','test_boss_skill_retry_session',
       'test_boss_skill_player_workflow','test_boss_workbench_v4_window','test_boss_skill_release','test_mod_installation',
       'test_player_status_stream','test_performance_comparison','test_research_scene_checkpoint')
SOURCES=('tools/release_boss_skill_workbench.py','tools/boss_skill_player_acceptance.py',
    'tools/boss_skill_world_acceptance.py',
    'tools/research_scene_checkpoint.py',
    'tools/boss_skill_player_workflow.py','tools/boss_workbench_v4_window.py',
    'tests/test_boss_skill_workbench_candidate.lua',*builder.SOURCES,
    *('tests/'+name+'.py' for name in TESTS))


def inherited(manifest):
    base_path=ROOT/'releases'/builder.BASE;base=validate_package(base_path)
    assert sha(base_path/MANIFEST)==manifest['previous_release_manifest_sha256']
    acceptance=ROOT/base['acceptance_report']
    assert sha(acceptance)==base['acceptance_report_sha256']
    proof=json.loads(acceptance.read_text(encoding='utf-8'));assert proof['passed']
    before,after=modules(base),modules(manifest)
    expected={'boss_catalog.lua',*(f'profiles/{name}{suffix}.lua' for name in builder.PROFILES.values()
                                  for suffix in ('','_bindings'))}
    assert set(before)==set(after) and {n for n in before if before[n]!=after[n]}==expected
    return dict(release=builder.BASE,manifest_sha256=sha(base_path/MANIFEST),
        acceptance_sha256=sha(acceptance),unchanged_runtime_camera_input_restoration=True)


def offline(package):
    assert_closed();manifest=builder.verify(package);base=inherited(manifest)
    lua=ROOT.parent/'build/lua-harness/Release/lua-lab.exe'
    syntax=ROOT/'runtime/boss-skills-v4-syntax.lua'
    syntax.write_text('\n'.join('assert(loadfile('+json.dumps((package/n).relative_to(ROOT).as_posix())+'))'
        for n in manifest['files'] if n.endswith('.lua'))+'\n',encoding='utf-8')
    jobs=[('four_role_catalog',[str(lua),'tests/test_boss_skill_workbench_candidate.lua',str(package)]),
          ('all_lua_syntax',[str(lua),str(syntax)]),
          ('player_window_smoke',[sys.executable,'-X','utf8','tools/boss_workbench_v4_window.py','--smoke'])]
    jobs.extend((name,[sys.executable,'-X','utf8','-m','unittest','tests.'+name,'-v']) for name in TESTS)
    checks=[]
    for label,command in jobs:
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',
            errors='replace',timeout=120,creationflags=subprocess.CREATE_NO_WINDOW)
        checks.append(dict(name=label,passed=result.returncode==0,output=result.stdout+result.stderr))
        print(label+': '+('PASS' if result.returncode==0 else 'FAIL'),flush=True)
    report=dict(candidate=str(package),candidate_manifest_sha256=sha(package/MANIFEST),
        inherited=base,checks=checks,passed=all(r['passed'] for r in checks),game_started=False,
        sources={n:sha(ROOT/n) for n in sorted(set(SOURCES))})
    write_json(ROOT/OFFLINE,report);assert report['passed']
    return report


def release(package,session,flow,world_session=None):
    assert_closed();manifest=builder.verify(package)
    checks=json.loads((ROOT/OFFLINE).read_text(encoding='utf-8'))
    assert checks['passed'] and checks['candidate']==str(package)
    assert checks['candidate_manifest_sha256']==sha(package/MANIFEST)
    assert checks['sources']=={n:sha(ROOT/n) for n in sorted(set(SOURCES))}
    ordinary=collect(session,flow,world_session)
    evidence=ROOT/'evidence/official-validation'/session/'boss-skill-player-acceptance.json'
    assert json.loads(evidence.read_text(encoding='utf-8'))==ordinary
    assert ordinary['candidate']==str(package) and len(ordinary['ordinary_extra_actions'])==24
    payload={n:(package/n).read_bytes() for n in manifest['files']}
    payload['PBZBossControl/README.md']=(
        '# Boss 工作台 v4\n\n当前核定PBZ构建的本机隔离离线版。阿花28项能力；万钧、烟千岁、游龙各8项，'
        '共52项原生能力、53个技能绑定。\n\nInsert打开工作台，↑↓选择，Enter确认，F6接管，F10恢复。'
        '三名扩展角色的新增默认键为F5、F8、F9、Q。保留游戏冷却、目标和地形限制。\n\n'
        '使用根目录开始Boss工作台.cmd；详见72-四Boss技能扩展v4操作说明.md。研究运行环境位于E盘项目，'
        '源码保留D盘。联机适配暂缓。不会回写研究进度到正式存档。\n').encode('utf-8')
    files={n:hashlib.sha256(data).hexdigest() for n,data in payload.items()}
    fingerprint=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()[:16]
    identifier='ahua-boss-workbench-v4-'+fingerprint
    target=ROOT/'releases'/identifier;report_path=ROOT/'evidence/releases'/(identifier+'-acceptance.json')
    assert not target.exists() and not report_path.exists(),'Preserve immutable release'
    report=dict(schema=1,passed=True,release_id=identifier,at=datetime.now().astimezone().isoformat(),
        candidate=str(package),candidate_manifest_sha256=sha(package/MANIFEST),
        inherited=inherited(manifest),skill_campaign=manifest['skill_session'],
        skill_campaign_sha256=manifest['skill_session_sha256'],ordinary_session=session,
        ordinary_acceptance=evidence.relative_to(ROOT).as_posix(),ordinary_acceptance_sha256=sha(evidence),
        ordinary_extra_actions=24,local_checks=OFFLINE,local_checks_sha256=sha(ROOT/OFFLINE),
        module_source_sha256=modules(manifest),bosses=manifest['bosses'],ability_count=52,skill_binding_count=53,
        sources={n:sha(ROOT/n) for n in sorted(set(SOURCES))})
    write_json(report_path,report);target.mkdir(parents=True)
    for name,data in payload.items():
        path=target/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    manifest.update(release_id=identifier,status='release',complete_mod=True,runtime_acceptance_current=True,
        files=files,pending=[],integration_only=False,accepted_candidate=package.name,
        acceptance_report=report_path.relative_to(ROOT).as_posix(),acceptance_report_sha256=sha(report_path),
        local_checks_sha256=sha(ROOT/OFFLINE))
    write_json(target/MANIFEST,manifest);validate_package(target)
    return dict(release=str(target),release_id=identifier,bosses=4,abilities=52,bindings=53)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('check','release'));parser.add_argument('candidate',type=Path)
    parser.add_argument('--session');parser.add_argument('--world-session');parser.add_argument('--workflow',type=Path);args=parser.parse_args()
    package=args.candidate.resolve()
    result=offline(package) if args.action=='check' else release(package,args.session,args.workflow.resolve(),args.world_session)
    print(json.dumps({k:v for k,v in result.items() if k!='checks'},ensure_ascii=False))
