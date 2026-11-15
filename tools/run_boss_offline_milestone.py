"""Single offline pipeline: collect historical evidence, prepare candidates, check and freeze."""
import ast
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys

from boss_adaptation_workflow import ROOT, OUT, collect, discover_sources, prepare, sha, write_json
from build_boss_adaptation_batch import freeze
from build_boss_identity_probe import build


def run_check(name,command):
    result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90)
    if result.returncode:
        raise RuntimeError(name+' failed:\n'+result.stdout+result.stderr)
    return {'name':name,'passed':True,'output':(result.stdout+result.stderr).strip()}


def main():
    catalog=collect(discover_sources())
    dossiers=prepare(catalog)
    checks=[]
    for name in ('boss_adaptation_workflow','boss_adaptation_batch'):
        checks.append(run_check(name,[sys.executable,'-X','utf8',str(ROOT/'tests'/('test_'+name+'.py'))]))
    batch=freeze()
    probe=build(batch)
    lua=ROOT.parent/'build/lua-harness/Release/lua-lab.exe'
    for mode in ('ok','wrong_identity','wrong_config'):
        checks.append(run_check('identity_queue_'+mode,[str(lua),str(ROOT/'tests/test_boss_identity_probe.lua'),str(probe),mode]))
    checks.append(run_check('existing_player_catalog',[str(lua),str(ROOT/'tests/test_boss_catalog.lua'),str(ROOT)]))
    manifest=json.loads((batch/'manifest.json').read_text(encoding='utf-8'))
    for name,digest in manifest['source_files'].items():
        assert sha(ROOT/name)==digest, 'source changed during milestone'
        if name.endswith('.py'):
            ast.parse((ROOT/name).read_text(encoding='utf-8'),filename=name)
    assert sha(batch/'catalog.json')==manifest['catalog_sha256']
    for name,digest in manifest['candidate_files'].items():
        assert sha(batch/name)==digest,'frozen candidate changed'
        candidate=json.loads((batch/name).read_text(encoding='utf-8'))
        assert candidate['enabled'] is False and candidate['playable'] is False
        assert all(g=='not_verified' for g in candidate['runtime_gates'].values())
    owner=json.loads((ROOT/'runtime/ahua-practice.json').read_text(encoding='utf-8'))
    postcheck_path=ROOT/'evidence/latest-native-diagnostic-postcheck.json'
    postcheck=json.loads(postcheck_path.read_text(encoding='utf-8'))
    assert owner['phase']=='closed','finish the existing research session before this milestone'
    assert postcheck['validation_state']==owner['state_file']
    for key in ('validation_restored','research_box_empty','research_loader_removed','host_registry_unchanged'):
        assert postcheck[key] is True,key
    for key in ('formal_files_changed','host_config_files_changed','remaining_games'):
        assert postcheck[key]==[],key
    first=[]
    for identifier in manifest['next_batch']['candidate_ids']:
        candidate=json.loads((batch/'candidates'/f'{identifier}.json').read_text(encoding='utf-8'))
        first.append({'id':identifier,'ability_path_candidates':len(candidate['skills']),
                      'playable':False,'identity_runtime_verified':False})
    result={'at':datetime.now().astimezone().isoformat(),'passed':True,'milestone':'M0 offline discovery and adaptation preparation',
        'resource_folders':len(catalog['candidates']),
        'unique_observed_package_paths':sum(len(c['assets']) for c in catalog['candidates']),
        'historical_source_files':len(catalog['sources']),'candidate_dossiers':len(dossiers),
        'frozen_batch':str(batch),'batch_fingerprint':manifest['fingerprint'],
        'batch_manifest_sha256':sha(batch/'manifest.json'),'checks':checks,'first_batch':first,
        'research_postcheck':{'path':str(postcheck_path),'sha256':sha(postcheck_path)},
        'game_started_by_offline_pipeline':False,'new_playable_bosses':0,
        'next_action':'Use the frozen three-candidate read-only identity batch at the next consolidated milestone; no repeat name scan.',
        'pending':'Actual Boss identity, live class/config/grants and all gameplay acceptance are separate future gates.'}
    target=ROOT/'evidence/adaptation/multi-boss-offline-milestone.json'
    write_json(target,result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('checks','research_postcheck')},ensure_ascii=False,indent=2))
    print('offline_check_groups='+str(len(checks))+'; report='+str(target))


if __name__=='__main__':
    main()
