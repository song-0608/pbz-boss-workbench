"""用途：按真实运行日志验收 PBZ 只读 Lua，缺任意一项都不算通过。"""
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import official_validation as v


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    state=json.loads(v.state_path().read_text(encoding='utf-8'))
    if state.get('restored') or time.time()>=state['deadline_unix']:
        raise RuntimeError('Need active offline experiment for live verification')
    if not state.get('offline_validation') or state.get('network_active'):
        raise RuntimeError('Offline experiment required')
    v.c.isolation.select_box('PBZSteamLab');dll=v.c.isolation.api()
    v.c.isolation.check_policy(dll,allow_offline_validation=True)
    if v.c.host_steam_pids(dll):raise RuntimeError('Host Steam session preserved')
    v.verify_build(state.get('ue4ss_loader_manifest'))
    target=v.c.isolation.virtual_file(v.c.isolation.get_root(dll),v.c.baseline.GAME/'platform/steam/ue4ss')
    log=(target/'UE4SS.log').read_text(encoding='utf-8-sig')
    prefix='PBZ_READONLY_SMOKE:'
    markers=[line.split(prefix,1)[1].strip() for line in log.splitlines() if prefix in line]
    count=next((int(x.split('=',1)[1]) for x in markers if re.fullmatch(r'PROPERTY_COUNT=\d+',x)),0)
    checks={'event_loop':'Event loop start' in log,'lua_started':'START' in markers,
        'actor_name':'ACTOR=Class /Script/Engine.Actor' in markers,'property_chain':count>0,
        'integer_property':any(re.fullmatch(r'JUMP_MAX_COUNT=\d+',x) for x in markers),
        'object_property':any(x.startswith('MOVEMENT=CharacterMovementComponent ') for x in markers),
        'world':any(x.startswith('WORLD=World ') for x in markers),
        'pass_marker':'PASS' in markers,'no_failure_marker':'FAIL' not in markers}
    now=v.c.baseline.formal_files();before=state['formal_before']
    changed=sum(now.get(p)!=before.get(p) for p in set(now)|set(before))
    checks['formal_files_unchanged']=changed==0
    report={'at':v.utc8(),'passed':all(checks.values()),'checks':checks,'markers':markers,
        'property_count':count,'formal_changed_count':changed,'gameplay_entered':False,
        'all_pbz_network_blocked':True,'boss_control_verified':False,
        'profile_sha256':hashlib.sha256((target/'MemberVariableLayout.ini').read_bytes()).hexdigest(),
        'lua_sha256':hashlib.sha256((target/'Mods/PBZReadOnlySmoke/Scripts/main.lua').read_bytes()).hexdigest(),
        'ue4ss_dll_sha256':hashlib.sha256((target/'UE4SS.dll').read_bytes()).hexdigest(),
        'work':state['work'],'scope':'Only verified checks above; does not certify full hooks, GUI or boss gameplay'}
    work=Path(state['work']);v.save(work/'lua-smoke-result.json',report)
    if report['passed']:
        v.save(v.ROOT/'evidence/adaptation/latest-passed-lua-smoke.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if not report['passed']:raise RuntimeError('Real PBZ Lua smoke incomplete or failed')


if __name__=='__main__':main()
