"""用途：统一运行游戏外回归并保存版本哈希；通过不代表Boss控制已实机成功。"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]


def main():
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    lua = ROOT.parent/'build/lua-harness/Release/lua-lab.exe'
    if not lua.is_file(): raise RuntimeError('Local Lua harness missing')
    checks = [
        ('observer_lua_fixtures',[str(lua),'tests/test_observer.lua',str(ROOT)]),
        ('candidate_and_log_parser',[sys.executable,'-m','unittest','discover','-s','tests','-p','test_*.py','-v']),
        ('control_session_mocks',[str(lua),'tests/test_session.lua',str(ROOT)]),
        ('native_control_bridge_fixtures',[str(lua),'tests/test_native_bridge.lua',str(ROOT)]),
        ('combat_identity_fixtures',[str(lua),'tests/test_combat_identity.lua',str(ROOT)]),
        ('remote_control_fixtures',[str(lua),'tests/test_remote_control.lua',str(ROOT)]),
        ('input_barrier_fixtures',[str(lua),'tests/test_input_barrier.lua',str(ROOT)]),
        ('player_protection_fixtures',[str(lua),'tests/test_player_protection.lua',str(ROOT)]),
        ('native_call_cancellation_fixtures',[str(lua),'tests/test_ue_calls.lua',str(ROOT)]),
        ('continuous_input_fixtures',[str(lua),'tests/test_input_driver.lua',str(ROOT)]),
        ('runtime_dispatch_fixtures',[str(lua),'tests/test_runtime.lua',str(ROOT)]),
    ]
    results=[]
    for name, command in checks:
        run=subprocess.run(command,cwd=ROOT,capture_output=True,timeout=45)
        out=run.stdout.decode('utf-8',errors='replace');err=run.stderr.decode('utf-8',errors='replace')
        print(out+err,end='')
        results.append({'name':name,'exit_code':run.returncode,'stdout':out,'stderr':err})
    files=['adaptation/pbz-26367565/Mods/PBZObserveAI/Scripts/main.lua',
           'tools/pbz_candidate_rules.py','tools/inspect_bride_candidates.py',
           'tools/observer_log_parser.py','tools/summarize_ai_observation.py',
           'tests/test_observer.lua','tests/test_candidate_rules.py','tests/test_observer_log_parser.py']
    files += [p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'mod/PBZBossControl/Scripts').rglob('*.lua'))]
    files += ['tests/test_native_bridge.lua','tests/test_ue_calls.lua','tests/test_input_driver.lua','tests/test_runtime.lua','tests/test_combat_identity.lua','tests/test_remote_control.lua','tests/test_input_barrier.lua','tests/test_player_protection.lua']
    result={'at':datetime.now().astimezone().isoformat(),'passed':all(r['exit_code']==0 for r in results),
            'checks':results,'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files},
            'candidate_version':3,'runtime_validation_performed':False,
            'game_started':False,'boss_control_verified':False,
            'scope':'Local fixtures and mocks only; no game process, save or Steam access'}
    target=ROOT/'evidence/adaptation/observer-v3-local-checks.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (ROOT/'evidence/adaptation/control-runtime-local-checks.json').write_text(
        json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Report: '+str(target))
    return 0 if result['passed'] else 1


if __name__=='__main__':sys.exit(main())
