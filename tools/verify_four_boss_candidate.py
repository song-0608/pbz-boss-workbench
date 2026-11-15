"""Offline four-Boss milestone; no installation or game launch."""
import json
import subprocess
import sys
from boss_adaptation_workflow import ROOT,sha,write_json
from build_four_boss_candidate import build
from mod_installation import MANIFEST,installed_package,validate_package


def main():
    target=build('20261116-073449');manifest=validate_package(target)
    relative=target.relative_to(ROOT).as_posix()
    harness=ROOT.parent/'build/lua-harness/Release/lua-lab.exe'
    checks=[]
    commands=[('four_native_profiles',[str(harness),'tests/test_four_boss_candidate.lua',relative]),
        ('selection_refusal_preserves_current',[str(harness),'tests/test_workbench_selection_preflight.lua',relative+'/PBZBossControl/Scripts/boss_workbench.lua'])]
    for pattern in ('test_youlong_attempt.py','test_youlong_profile.py'):
        commands.append((pattern,[sys.executable,'-m','unittest','discover','-s','tests','-p',pattern,'-v']))
    files=[n for n in manifest['files']if n.endswith('.lua')]
    syntax=ROOT/'runtime/four-boss-syntax.lua'
    syntax.write_text('\n'.join('assert(loadfile('+json.dumps(relative+'/'+n)+'))'for n in files)
        +'\nprint("PASS '+str(len(files))+' Lua syntax files")\n',encoding='utf-8')
    commands.append(('all_lua_syntax',[str(harness),'runtime/four-boss-syntax.lua']))
    for name,args in commands:
        result=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90)
        assert result.returncode==0,name+': '+result.stdout+result.stderr
        checks.append({'name':name,'passed':True,'output':(result.stdout+result.stderr).strip()})
    receipt,_,_=installed_package()
    assert receipt['release_id']=='ahua-boss-workbench-v1-f0bcf1323e641e03'
    sources=('tools/collect_youlong_attempt.py','tools/build_youlong_profile.py','tools/build_four_boss_candidate.py',
        'tools/verify_four_boss_candidate.py','tests/test_youlong_attempt.py','tests/test_youlong_profile.py','tests/test_four_boss_candidate.lua')
    report={'passed':True,'candidate':relative,'manifest_sha256':sha(target/MANIFEST),'checks':checks,
        'lua_files_checked':len(files),'sources':{n:sha(ROOT/n)for n in sources},
        'youlong_base_control_accepted':True,'ordinary_switching_accepted':False,'world_cycle_verified':False,
        'ability_count':40,'binding_count':41,'game_started':False,'candidate_installed':False,
        'installed_release':receipt['release_id'],'complete_mod':False}
    write_json(ROOT/'evidence/adaptation/four-boss-candidate-offline.json',report)
    print(json.dumps({k:v for k,v in report.items()if k not in ('checks','sources')},ensure_ascii=False))


if __name__=='__main__':main()
