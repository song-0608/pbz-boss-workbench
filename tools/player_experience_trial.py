"""Read-only gate and evidence recorder for window-scoped experience trial inputs.

This tool never injects input. The selected Computer Use window must match the
returned research HWND; every action requires a fresh gate.
"""
import argparse
import ctypes
from ctypes import wintypes as w
import json
from pathlib import Path
import re
import time

import ahua_practice as practice
import official_validation as v
import player_experience_workflow as workflow
import build_player_experience_candidate as candidate
from four_boss_integration_workflow import modules
from boss_adaptation_workflow import sha, write_json
from control_action_evidence import restoration_result

ACTIONS={'enter':'F6','exit':'F10','cycle_target':'F7','lock':'MIDDLE_MOUSE_BUTTON',
         'shift_cast':'Shift_L+w+F1','cast':'F1','workbench':'Insert',
         'down':'Down','up':'Up','confirm':'Return','close':'Escape'}


def validate_action(action, owner, deployment, text):
    assert action in ACTIONS, 'Bounded trial action required'
    assert owner.get('phase')=='armed' and owner.get('player_entry')
    assert not any(owner.get(k) for k in ('skill_lab','expanded','boss_candidate'))
    assert deployment.get('player_entry') and not deployment.get('boss_candidate')
    controls=owner.get('actual_controls',{})
    assert all(controls.get(k)==v for k,v in (
        ('enter','F6'),('exit','F10'),('cycle_target','F7'),('lock_target','MIDDLE_MOUSE_BUTTON')))
    assert sum(row.get('slot')=='slot1'and row.get('skill')=='skill_01'and row.get('key')=='F1'
               for row in owner.get('actual_bindings',[]))==1
    current=text[owner['log_offset']:]
    assert not any(token in current for token in ('state=FAULTED','ISSUE_','[Lua::execute_file]'))
    entered=current.rfind('[PBZBossControl] enter success=true state=ACTIVE')
    exited=max(current.rfind('[PBZBossControl] '+name+' success=true')
               for name in ('exit','auto_exit','menu_exit'))
    active=entered>=0 and entered>exited
    if action in ('lock','cycle_target','cast','shift_cast','exit'):
        assert active, 'Current successful active takeover required'
    if action in ('enter','down','up','confirm','close'):
        assert not active, 'Restore the player before selecting or entering'
    if action in ('down','up','confirm','close'):
        assert current.rfind('WORKBENCH_INPUT_LOCKED=')>current.rfind('WORKBENCH_INPUT_RESTORED=true')
    return ACTIONS[action]


def gate(flow,action):
    frozen=workflow.verify(flow)
    owner,state=practice.owned_session()
    assert min(state['deadline_unix'],state.get('control_probe_expires_at',0))-time.time()>20
    assert state.get('boss_lifecycle_experiment') and state.get('control_probe_interactive')
    assert state.get('ue4ss_deployed') and not state.get('restored')
    assert practice.read(v.ROOT/'evidence/latest-gameplay-save-isolation.json')['passed']
    deployment=practice.read(Path(state['work'])/'control-lifecycle-deployment.json')
    package=Path(frozen['candidate']);manifest=candidate.verify(package)
    assert deployment['module_source_sha256']==modules(manifest)
    text=practice.log_path(state).read_text(encoding='utf-8',errors='replace')
    key=validate_action(action,owner,deployment,text)
    c=v.c;c.isolation.select_box('PBZSteamLab');dll=c.isolation.api()
    c.isolation.check_policy(dll,allow_offline_validation=True)
    assert not c.host_steam_pids(dll), 'Preserve host Steam'
    assert c.baseline.formal_files()==state['formal_before'], 'Formal files changed'
    v.verify_build(state['ue4ss_loader_manifest'])
    ids={p['ProcessId']for p in c.box_processes(dll)if p['Name'].lower()=='pbz.exe'}
    assert ids, 'Owned research game process required'
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.GetForegroundWindow.restype=w.HWND
    user.GetWindowThreadProcessId.argtypes=[w.HWND,ctypes.POINTER(w.DWORD)]
    callback=ctypes.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
    user.EnumWindows.argtypes=[callback,w.LPARAM]
    user.IsWindowVisible.argtypes=[w.HWND]
    user.GetClassNameW.argtypes=[w.HWND,w.LPWSTR,ctypes.c_int]
    windows=[]
    @callback
    def inspect(handle,_):
        process=w.DWORD();user.GetWindowThreadProcessId(handle,ctypes.byref(process))
        if process.value in ids and user.IsWindowVisible(handle):
            name=ctypes.create_unicode_buffer(256);user.GetClassNameW(handle,name,256)
            if name.value.endswith(':UnrealWindow'):windows.append(int(handle))
        return True
    user.EnumWindows(inspect,0)
    assert len(windows)==1, 'Unique research render window required'
    front=user.GetForegroundWindow();pid=w.DWORD()
    user.GetWindowThreadProcessId(front,ctypes.byref(pid))
    assert pid.value in ids and int(front or 0)==windows[0], 'Research game must already be foreground'
    request=dict(schema=1,at=v.utc8(),gate_expires_at=time.time()+10,
        workflow=str(flow),candidate_manifest_sha256=sha(package/'pbz-release.json'),
        state_file=state['state_file'],game_pid=pid.value,window_id=int(front),
        action=action,key=key,log_offset=len(text),input_sent=False,gameplay_verified=False)
    path=Path(state['work'])/('experience-input-'+str(time.time_ns())+'.json')
    write_json(path,request)
    print(json.dumps(dict(request=str(path),**request),ensure_ascii=False))
    return request


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workflow',type=Path)
    parser.add_argument('action',choices=ACTIONS)
    args=parser.parse_args();gate(args.workflow.resolve(),args.action)
