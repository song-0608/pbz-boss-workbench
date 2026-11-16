"""Compile and probe the role-bound official Steam entry; never start Steam or a game."""
import ctypes
import json
from pathlib import Path
import subprocess
import time
import uuid

from build_phantom_boss_candidate import ROOT,canonical,sha
from build_phantom_boss_native import compiler_environment
from check_phantom_boss_isolation import SBIE,BOXES,api,pids,virtual,verify_policy

SOURCE='tools/phantom_boss_pair_bootstrap.cpp'


def run():
    env,compiler=compiler_environment()
    directory=ROOT/'runtime/pair-bootstrap'/uuid.uuid4().hex
    directory.mkdir(parents=True)
    exe=directory/'pair_bootstrap.exe'
    command=[str(compiler),'/nologo','/std:c++20','/O2','/MT','/EHsc','/W3','/utf-8','/Brepro',
        '/Fo:'+str(directory/'pair_bootstrap.obj'),str(ROOT/SOURCE),'/Fe:'+str(exe),
        '/link','/Brepro','advapi32.lib']
    compiled=subprocess.run(command,cwd=directory,env=env,capture_output=True,timeout=90)
    (directory/'compile.txt').write_bytes(compiled.stdout+compiled.stderr)
    assert compiled.returncode==0,(compiled.stdout+compiled.stderr).decode('mbcs',errors='replace')[-1800:]
    print('Compiled role-bound Steam entry; no client/game started',flush=True)
    dll=api();checks=[]
    for role,box in BOXES.items():
        verify_policy(dll,role,False);assert not pids(dll,box)
    def lease(role,name,**changes):
        now=int(time.time())
        fields=dict(mode='two-player-online-research',role=role,session='a'*32,issued_at=str(now-1),expires_at=str(now+60))
        fields.update(changes)
        path=directory/(name+'.ini');path.write_bytes(''.join(f'{k}={v}\n' for k,v in fields.items()).encode())
        return path
    def probe(name,role,box_role=None,expected=0,fields=None,action='probe'):
        request=lease(role,name,**(fields or {}));output=directory/(name+'.json')
        if box_role:
            command=[str(SBIE/'Start.exe'),'/box:'+BOXES[box_role],'/silent','/hide_window','/wait',
                str(exe),action,role,str(request),str(output)]
            physical=virtual(box_role,output)
        else:
            command=[str(exe),action,role,str(request),str(output)];physical=output
        result=subprocess.run(command,capture_output=True,timeout=20,creationflags=subprocess.CREATE_NO_WINDOW)
        assert result.returncode==expected,f'{name}: unexpected exit {result.returncode} (expected {expected})'
        if expected==0:
            observed=json.loads(physical.read_bytes())
            assert observed==dict(box_verified=True,lease_verified=True,role=role,probe_only=True,
                active_client_in_same_box=False,official_existing_user=False,registry_error=0,
                created=False,child_pid=0,child_box_verified=False,resumed=False,win32_error=0)
            checks.append(dict(name=name,passed=True,exit_code=0,output=str(physical),output_sha256=sha(physical.read_bytes())))
        else:
            assert not physical.exists(),'Refused entry must not write a success report'
            checks.append(dict(name=name,passed=True,exit_code=expected))
        print('PASS '+name,flush=True)
        if box_role:
            deadline=time.monotonic()+8
            while pids(dll,BOXES[box_role]) and time.monotonic()<deadline:time.sleep(.2)
            assert not pids(dll,BOXES[box_role]),'Probe did not exit its container'
    probe('host_execution_refused','host',expected=65)
    probe('unknown_role_refused','other',expected=64)
    probe('host_container_verified','host','host')
    probe('guest_container_verified','guest','guest')
    probe('cross_role_refused','guest','host',expected=65)
    probe('expired_lease_refused','host',expected=66,fields=dict(expires_at='1'),action='leasecheck')
    probe('trailing_timestamp_refused','guest',expected=66,fields=dict(expires_at=str(int(time.time())+60)+'junk'),action='leasecheck')
    probe('oversized_lease_refused','host',expected=66,fields=dict(expires_at=str(int(time.time())+1205)),action='leasecheck')
    probe('wrong_mode_refused','guest',expected=66,fields=dict(mode='offline'),action='leasecheck')
    probe('wrong_session_refused','host',expected=66,fields=dict(session='bad'),action='leasecheck')
    # Observe natural exit. Do not terminate a container which may have acquired
    # an unrelated process while the standalone probes were running.
    deadline=time.monotonic()+12
    while any(pids(dll,box) for box in BOXES.values()) and time.monotonic()<deadline:time.sleep(.2)
    assert all(not pids(dll,box) for box in BOXES.values()),'Probe process remains'
    report=dict(schema=1,status='role-bound-entry-probed',passed=True,checks=checks,
        directory=directory.relative_to(ROOT).as_posix(),exe_sha256=sha(exe.read_bytes()),
        compiler_sha256=sha(compiler.read_bytes()),compile_log_sha256=sha((directory/'compile.txt').read_bytes()),
        source_sha256={name:sha((ROOT/name).read_bytes()) for name in (SOURCE,'tools/check_phantom_boss_pair_bootstrap.py')},
        steam_started=False,game_started=False,installed=False,complete_mod=False,runtime_acceptance_current=False)
    (directory/'bootstrap.json').write_bytes(canonical(report)+b'\n')
    (ROOT/'evidence/adaptation/phantom-pact-pair-bootstrap.json').write_bytes(canonical(report)+b'\n')
    print(json.dumps(dict(passed=True,checks=len(checks),directory=str(directory),steam_started=False,game_started=False),ensure_ascii=False))
    return report


if __name__=='__main__':run()
