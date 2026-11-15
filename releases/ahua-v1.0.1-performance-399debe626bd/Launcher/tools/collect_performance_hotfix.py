"""Publish a cache hotfix acceptance record only after measured and lifecycle regressions pass."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from mod_installation import ROOT,active_mod_root,assert_closed,digest


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def closed(session):
    if not re.fullmatch(r'\d{8}-\d{6}',session):raise ValueError('Exact session required')
    work=ROOT/'evidence/official-validation'/session
    state=read(ROOT/'runtime'/('official-validation-'+session)/'state.json');post=read(work/'postcheck.json')
    assert state['restored'] and post['validation_state']==state['state_file']
    assert not post['formal_files_changed'] and not post['host_config_files_changed'] and post['host_registry_unchanged']
    assert post['research_box_empty'] and post['research_loader_removed']
    raw=(work/'UE4SS.log').read_bytes();text=raw.decode('utf-8',errors='replace')
    return work,state,text,hashlib.sha256(raw).hexdigest()


def active_duration(text):
    start=last=None;longest=0
    for line in text.splitlines():
        if 'PBZ_PLAYER_UI:STATUS='not in line:continue
        row=json.loads(line.split('PBZ_PLAYER_UI:STATUS=',1)[1]);at=row['at']
        if row['text'].startswith('新娘阿花 | ACTIVE\n'):
            if start is None or at-last>3 or at<last:start=at
            longest=max(longest,at-start);last=at
        else:start=last=None
    return longest


def collect(reload_session):
    assert_closed();comparison=read(ROOT/'evidence/adaptation/ahua-performance-comparison.json')
    assert comparison['passed']
    fixed=comparison['fixed'];work,state,text,sha=closed(fixed['session'])
    assert sha==fixed['log_sha256']
    source=active_mod_root();modules={p.relative_to(source/'Scripts').as_posix():digest(p)for p in(source/'Scripts').rglob('*.lua')if p.name!='main.lua'}
    assert modules==fixed['module_source_sha256']
    assert digest(source/'Experiments/spawn_lifecycle.lua')==fixed['assembly_source_sha256']
    skills=read(work/'player-skill-acceptance-evidence.json');assert skills['log_sha256']==sha
    assert any(r['skill']=='skill_01'and r['natural_completion']and r['restoration']['passed']for r in skills['actions'])
    assert any(r['skill']=='skill_08'and r['active_cancel_and_restoration']for r in skills['actions'])
    gc=read(work/'owned-camera-gc.json');assert any(r['all_released']for r in gc['checks'])
    duration=active_duration(text);assert duration>=300
    costs=[r['costs']for r in fixed['summary']['selected_windows']]
    assert all(any(r.get(name,{}).get('calls',0)>0 for r in costs)for name in('bridge.move','bridge.look'))
    reload_work,reload_state,reload_text,reload_sha=closed(reload_session)
    cache=read(reload_work/'cache-world-probe.json')
    assert cache['passed']and cache['read_only']and cache['state_file']==reload_state['state_file']
    assert cache['script_sha256']==digest(reload_work/'cache-world-probe.lua')
    cache_tail=reload_text[cache['log_offset']:]
    assert re.search(r'PBZ_CACHE_WORLD:PASS=old=(\d+)\|new=(\d+)\|queries=25\|input_restored=true\|old_receipt_rejected=true',cache_tail)
    retired=reload_text.rfind('IDLE_WORLD_OBJECTS_RETIRED=')
    assert retired>0 and 'WORLD_REASSEMBLY_AWAITING_GAMEPLAY=true'in reload_text[retired:]
    from control_action_evidence import restoration_result
    assert restoration_result(reload_text[:retired])['passed']
    assert 'END=initialization rejected before takeover; original player restoration verified'in reload_text[retired:]
    assert '[PBZBossControl] enter success=true'not in reload_text[retired:]
    deployment=read(reload_work/'control-lifecycle-deployment.json')
    assert deployment['module_source_sha256']==modules
    assert not deployment.get('performance_profile')and deployment['assembly_source_sha256']==fixed['assembly_source_sha256']
    loader=read(reload_work/'selfbuilt-baseline-deployment.json')
    assert loader['object_lookup_cache_enabled']and loader['loader_settings_sha256']==digest(reload_work/'loader-settings.ini')
    settings=(reload_work/'loader-settings.ini').read_text(encoding='utf-8')
    assert settings==fixed['loader_settings']
    baseline_source=ROOT/'tools/pbz_ue4ss_baseline.py'
    evidence={'at':datetime.now().astimezone().isoformat(),'passed':True,'kind':'launcher-object-cache-hotfix',
              'gameplay_release':'ahua-28-v1-b823a4c9b91b404a','gameplay_lua_unchanged':True,
              'comparison_sha256':digest(ROOT/'evidence/adaptation/ahua-performance-comparison.json'),
              'cache_enabled':True,'continuous_active_seconds':duration,'skill_natural_and_cancel_verified':True,
              'owned_camera_gc_released_or_reused':True,'native_menu_new_world_cache_identity_without_profiler':True,
              'new_world_old_receipt_rejected':True,'full_gameplay_reassembly_on_new_config_verified':False,
              'new_world_layout_result':'Three local layouts rejected by unchanged line-of-sight gate; owned Actors cleaned, no takeover',
              'diagnostic_repairs':'Read-only probe first had a Lua numeric concatenation syntax error, then rejected a reused old address; final probe checks full identity and rejects old receipts. All original records retained.',
              'reload_session':reload_session,'reload_log_sha256':reload_sha,
              'launcher_source_sha256':{baseline_source.relative_to(ROOT).as_posix():digest(baseline_source)},
              'module_source_sha256':modules,'dll_sha256':loader['dll_sha256'],
              'scope':'Current fixed PBZ build and existing local protected offline launcher; GPU present FPS not measured'}
    target=ROOT/'evidence/adaptation/ahua-performance-hotfix-acceptance.json'
    target.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in evidence.items()if k not in('module_source_sha256','launcher_source_sha256')},ensure_ascii=False,indent=2))
    return evidence


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('reload_session');args=parser.parse_args();collect(args.reload_session)
