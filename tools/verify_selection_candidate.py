"""Run one offline selection milestone; never launch or install a game candidate."""
import ast
from datetime import datetime
import json
import subprocess
import sys
from build_selection_candidate import ROOT,SOURCES,build
from boss_adaptation_workflow import sha,write_json
from mod_installation import MANIFEST,installed_package,validate_package,assert_closed


def main():
    assert_closed();target=build();manifest=validate_package(target)
    relative=target.relative_to(ROOT).as_posix()
    harness=ROOT.parent/'build/lua-harness/Release/lua-lab.exe'
    checks=[]
    def run(name,args):
        result=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90)
        assert result.returncode==0,name+': '+result.stdout+result.stderr
        checks.append({'name':name,'passed':True,'output':(result.stdout+result.stderr).strip()})
    run('selection_and_real_refusal',[sys.executable,'-m','unittest','discover','-s','tests','-p','test_selection_candidate.py','-v'])
    for name,args in (
        ('native_preflight',['tests/test_boss_selection_preflight.lua','.']),
        ('workbench_rejection_preserves_assembly',['tests/test_workbench_selection_preflight.lua',relative+'/PBZBossControl/Scripts/boss_workbench.lua']),
        ('three_boss_catalog',['tests/test_three_boss_candidate.lua',relative]),
        ('published_workbench_regression',['tests/test_boss_workbench.lua','.']),
        ('terrain_clearance',['tests/test_yanqiansui_clearance.lua','.'])):
        run(name,[str(harness),*args])
    lua_files=[n for n in manifest['files']if n.endswith('.lua')]
    syntax=ROOT/'runtime/selection-syntax.lua'
    syntax.write_text('\n'.join('assert(loadfile('+json.dumps(relative+'/'+n)+'))'for n in lua_files)
        +'\nprint("PASS '+str(len(lua_files))+' Lua syntax files")\n',encoding='utf-8')
    run('all_candidate_lua_syntax',[str(harness),'runtime/selection-syntax.lua'])
    sources=(*SOURCES,'tools/collect_clearance_rejection.py','tools/verify_selection_candidate.py')
    for n in sources:
        if n.endswith('.py'):ast.parse((ROOT/n).read_text(encoding='utf-8'),filename=n)
    receipt,_,_=installed_package()
    assert receipt['release_id']=='ahua-boss-workbench-v1-f0bcf1323e641e03'
    report={'at':datetime.now().astimezone().isoformat(),'passed':True,
        'candidate':relative,'manifest_sha256':sha(target/MANIFEST),'checks':checks,
        'lua_files_checked':len(lua_files),'sources':{n:sha(ROOT/n)for n in sources},
        'closed_refusal_receipt_sha256':sha(ROOT/'research/boss-adaptation/developer-attempt-receipts/20261116-070127.json'),
        'installed_release':receipt['release_id'],'game_started':False,'candidate_installed':False,
        'live_preflight_verified':False,'new_playable_bosses':0,'complete_mod':False}
    write_json(ROOT/'evidence/adaptation/workbench-selection-preflight-offline.json',report)
    print(json.dumps({k:v for k,v in report.items()if k not in ('checks','sources')},ensure_ascii=False))


if __name__=='__main__':main()
