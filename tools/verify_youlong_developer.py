"""Offline milestone for one native YouLong candidate and its isolated test workflow."""
from datetime import datetime
import json
import subprocess
import sys
from boss_adaptation_workflow import ROOT,sha,write_json
import youlong_developer_bundle as bundle
import youlong_developer_workflow as workflow
from mod_installation import installed_package,assert_closed


def main():
    assert_closed();candidate=bundle.build();target=workflow.build(candidate)
    manifest=workflow.verify(target);grant=manifest['candidate_grant'];checks=[]
    def run(name,args):
        result=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90)
        assert result.returncode==0,name+': '+result.stdout+result.stderr
        checks.append({'name':name,'passed':True,'output':(result.stdout+result.stderr).strip()})
    for name in ('youlong_developer_bundle','youlong_developer_workflow'):
        run(name,[sys.executable,'-m','unittest','discover','-s','tests','-p','test_'+name+'.py','-v'])
    run('native_grant_boundaries',[str(ROOT.parent/'build/lua-harness/Release/lua-lab.exe'),
        'tests/test_youlong_developer_candidate.lua',candidate.relative_to(ROOT).as_posix()+'/boss_candidate.lua',
        grant['identity_receipt_sha256'],grant['ability_metadata_receipt_sha256']])
    for name in ('ahua_practice.py','run_control_lifecycle_probe.py','test_player_skill_batch.py',
                 'run_boss_candidate_milestone.py','collect_boss_candidate_acceptance.py'):
        run(name+'_cli_import',[sys.executable,str(target/name),'--help'])
    workflow.verify(target)
    receipt,_,_=installed_package()
    assert receipt['release_id']=='ahua-boss-workbench-v1-f0bcf1323e641e03'
    result={'at':datetime.now().astimezone().isoformat(),'passed':True,'id':bundle.ID,
        'bundle':candidate.relative_to(ROOT).as_posix(),'bundle_manifest_sha256':sha(candidate/'manifest.json'),
        'workflow':target.relative_to(ROOT).as_posix(),'workflow_manifest_sha256':sha(target/'manifest.json'),
        'checks':checks,'candidate_action_pool':8,'excluded_metadata_paths':24,
        'source_files':{n:sha(ROOT/n)for n in (*bundle.SOURCES,*workflow.SOURCES,'tools/verify_youlong_developer.py')},
        'historical_source_sha256':workflow.FROZEN,'game_started':False,'playable':False,
        'live_grants_verified':False,'activation_verified':False,'complete_mod':False,
        'installed_release':receipt['release_id']}
    write_json(ROOT/'evidence/adaptation/youlong-developer-offline.json',result)
    print(json.dumps({k:v for k,v in result.items()if k not in('checks','source_files','historical_source_sha256')},ensure_ascii=False))


if __name__=='__main__':main()
