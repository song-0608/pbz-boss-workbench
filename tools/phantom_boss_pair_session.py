"""Install a pinned payload only in the two research boxes and supervise official launches.

Preparation never launches. Steam clients and games are separate actions so the
native declarations can be collected once while the mod waits in its dormant gate.
Saved progress is copied only into an empty research save root and never restored.
"""
import argparse
import ctypes
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time
import uuid

from build_phantom_boss_candidate import ROOT, canonical, safe_file, sha
from check_phantom_boss_isolation import BOXES, GAME, SBIE, api, pids, virtual, verify_policy, settings, change, sections
from prepare_phantom_boss_clients import LOGICAL
from run_sandbox_baseline import formal_files
from stage_phantom_boss_pair import digest, save_snapshot, verify as verify_stage

RUNS=ROOT/'runtime/online-runs'
SOURCE_NAMES=('tools/phantom_boss_pair_session.py','tools/phantom_boss_online_readonly.py',
    'tools/collect_phantom_boss_visual_contract.py','tools/prepare_phantom_boss_clients.py',
    'tools/collect_phantom_boss_control_contract.py','tools/collect_phantom_boss_contract_bundle.py',
    'tools/collect_phantom_boss_workbench_contract.py','tools/phantom_boss_control_abi.py',
    'tools/issue_phantom_boss_control_binding.py','research/contracts/phantom-control-abi.json',
    'tools/phantom_boss_native_bootstrap.cpp','tools/phantom_boss_launch_gate.lua')


def atomic(path,value):
    path=Path(path);temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.pending')
    with temporary.open('xb') as stream:stream.write(canonical(value)+b'\n')
    temporary.replace(path)


def load_run(path):
    path=Path(path).resolve()
    assert path.parent.parent==RUNS.resolve() and path.name=='session.json'
    assert re.fullmatch('[0-9a-f]{32}',path.parent.name)
    value=json.loads(path.read_bytes())
    assert value['schema']==1 and value['mode']=='two-player-online-research'
    assert value['session']==path.parent.name and set(value['instances'])==set(BOXES)
    for role,row in value['instances'].items():assert row['box']==BOXES[role]
    return path,value


def bootstrap_exe():
    report=json.loads((ROOT/'evidence/adaptation/phantom-pact-pair-bootstrap.json').read_bytes())
    assert report['passed'] and not report['steam_started'] and not report['game_started']
    for name,value in report['source_sha256'].items():assert digest(safe_file(ROOT,name))==value
    exe=safe_file(ROOT,report['directory'])/'pair_bootstrap.exe'
    assert digest(exe)==report['exe_sha256']
    return exe


def verify_clients():
    summary=json.loads((ROOT/'evidence/adaptation/phantom-pact-client-snapshots.json').read_bytes())
    assert summary['passed'] and summary['status']=='copied-not-started'
    receipt=safe_file(ROOT,summary['receipt']);assert digest(receipt)==summary['receipt_sha256']
    copied=json.loads(receipt.read_bytes());assert copied['status']=='copied-not-started'
    layout_path=safe_file(ROOT,summary['layout_receipt']);assert digest(layout_path)==summary['layout_receipt_sha256']
    layout=json.loads(layout_path.read_bytes());assert layout['status']=='directory-layout-complete'
    for role in BOXES:
        assert copied['roles'][role]['verified'] and copied['roles'][role]['target']==str(virtual(role,LOGICAL))
        # Startup may update logs/caches; pin executable entry points rather than
        # attempting to overwrite the copied account/configuration tree.
        for name in ('steam.exe','steamclient64.dll'):
            assert digest(virtual(role,LOGICAL)/name)==copied['files'][name]['sha256']
        assert all((virtual(role,LOGICAL)/name).is_dir() for name in layout['directories'])
    return summary


def prepare(stage):
    stage=Path(stage).resolve();m=verify_stage(stage)
    assert stage.parent==ROOT/'runtime/online-stages'
    dll=api()
    import preflight
    assert not preflight.games_running(),'Preserve the active game before deploying a pair'
    for role,box in BOXES.items():verify_policy(dll,role,False);assert not pids(dll,box)
    clients=verify_clients();exe=bootstrap_exe()
    before=formal_files();session=uuid.uuid4().hex;directory=RUNS/session
    directory.mkdir(parents=True,exist_ok=False);path=directory/'session.json'
    pair=json.loads((safe_file(stage,m['pair_directory'])/'pair.json').read_bytes())
    value=dict(schema=1,mode='two-player-online-research',session=session,status='preparing',
        stage=stage.relative_to(ROOT).as_posix(),stage_manifest_sha256=digest(stage/'stage.json'),
        candidate=m['candidate'],exe_sha256=pair['exe_sha256'],catalog_sha256=pair['catalog_sha256'],
        upstream_commit=pair['upstream_commit'],bosses=pair['bosses'],duration_seconds=1200,
        bootstrap=str(exe),bootstrap_sha256=digest(exe),client_receipt_sha256=clients['receipt_sha256'],
        issued_at=None,expires_at=None,instances={role:dict(box=box,game_pid=None,client_started=False,
            game_requested=False,official_existing_user=False) for role,box in BOXES.items()},
        deployed=[],save_roots=[],formal_before=before,game_started=False,steam_started=False,
        complete_mod=False,runtime_acceptance_current=False,
        source_sha256={name:digest(ROOT/name) for name in SOURCE_NAMES})
    atomic(path,value)
    try:
        plans=[]
        for role in BOXES:
            mod=virtual(role,GAME/'platform/steam/ue4ss/Mods/PBZCoop')
            assert not any((mod/name).exists() for name in ('bwb_native_lease.ini',
                'Scripts/bwb_gate.ini','Scripts/bwb_stop.txt','Scripts/bwb_current_bindings.lua')), \
                'Prior research session control files must be inspected and cleaned first'
            for relative,expected in m['files'].items():
                prefix=role+'/game/platform/steam/'
                if not relative.startswith(prefix):continue
                suffix=relative[len(role+'/game/'):]
                target=virtual(role,GAME/suffix);origin=safe_file(stage,relative)
                assert not target.exists(),'Preserve an existing research payload: '+str(target)
                plans.append((role,origin,target,expected))
            for logical in (GAME/'ProjectPBZ/Saved',Path(os.environ['LOCALAPPDATA'])/'ProjectPBZ/Saved'):
                target=virtual(role,logical)
                assert not target.is_symlink() and not target.is_junction()
                existing=save_snapshot(target) if target.is_dir() and any(target.rglob('*.sav')) else None
                value['save_roots'].append(dict(role=role,target=str(target),
                    mode='preserved-current' if existing else 'copied-current-research',
                    snapshot_sha256=sha(canonical(existing or m['research_snapshot']))))
                if not existing:
                    # Existing sentinel files are allowed; never erase or replace them.
                    for name in m['research_snapshot']:assert not (target/name).exists()
        for role,origin,target,expected in plans:
            assert digest(origin)==expected
            target.parent.mkdir(parents=True,exist_ok=True)
            # Journal responsibility before a possible partial write.
            value['deployed'].append(dict(role=role,path=str(target),sha256=expected,status='writing'));atomic(path,value)
            with origin.open('rb') as src,target.open('xb') as dst:
                import shutil
                shutil.copyfileobj(src,dst)
            assert digest(target)==expected
            value['deployed'][-1]['status']='installed';atomic(path,value)
        for row in value['save_roots']:
            if row['mode']=='preserved-current':continue
            target=Path(row['target']);target.mkdir(parents=True,exist_ok=True)
            for name,item in m['research_snapshot'].items():
                origin=stage/row['role']/'game/ProjectPBZ/Saved'/name;destination=target/name
                assert digest(origin)==item['sha256'];destination.parent.mkdir(parents=True,exist_ok=True)
                with origin.open('rb') as src,destination.open('xb') as dst:
                    import shutil
                    shutil.copyfileobj(src,dst)
                assert digest(destination)==item['sha256']
        assert formal_files()==before
        value['status']='prepared';atomic(path,value)
        print(json.dumps(dict(session=str(path),status=value['status'],deployed=len(plans),
            saves='independent copies; existing research progress preserved',game_started=False),ensure_ascii=False),flush=True)
        return path
    except Exception as error:
        value.update(status='prepare-failed-preserve-partial',error=type(error).__name__);atomic(path,value);raise


def process_identity(pid):
    """A creation-time-bound identity; no process memory is read or modified."""
    k=ctypes.WinDLL('kernel32',use_last_error=True)
    k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];k.OpenProcess.restype=w.HANDLE
    k.CloseHandle.argtypes=[w.HANDLE]
    k.QueryFullProcessImageNameW.argtypes=[w.HANDLE,w.DWORD,w.LPWSTR,ctypes.POINTER(w.DWORD)]
    k.GetProcessTimes.argtypes=[w.HANDLE,*([ctypes.POINTER(w.FILETIME)]*4)]
    handle=k.OpenProcess(0x1000,False,pid)
    if not handle:return None
    try:
        image=ctypes.create_unicode_buffer(32768);size=w.DWORD(len(image))
        created,exited,kernel,user=(w.FILETIME() for _ in range(4))
        if not k.QueryFullProcessImageNameW(handle,0,image,ctypes.byref(size)):return None
        if not k.GetProcessTimes(handle,*map(ctypes.byref,(created,exited,kernel,user))):return None
        return dict(pid=pid,image=image.value,created=(created.dwHighDateTime<<32)|created.dwLowDateTime)
    finally:k.CloseHandle(handle)


def discover_games(dll):
    found={}
    for role,box in BOXES.items():
        bodies=[process_identity(pid) for pid in pids(dll,box)]
        bodies=[r for r in bodies if r and Path(r['image']).name.casefold()=='pbz.exe'
            and Path(r['image']).resolve()==(GAME/'platform/steam/PBZ.exe').resolve()]
        assert len(bodies)<=1,'Unexpected duplicate game body in '+box
        if bodies:found[role]=bodies[0]
    return found


def observe_games(path):
    path,value=load_run(path)
    assert value['status'] in ('games-starting','games-waiting','games-start-timeout','partial-active','active')
    assert time.time()<value['expires_at']
    observed=discover_games(api())
    for role,row in observed.items():
        previous=value['instances'][role].get('game_identity')
        assert previous is None or previous==row,'Do not substitute a restarted game in an existing lease'
        value['instances'][role].update(game_pid=row['pid'],game_identity=row)
    value.update(status='active' if len(observed)==2 else 'partial-active' if observed else 'games-waiting',
        game_started=value['game_started'] or bool(observed))
    atomic(path,value)
    print(json.dumps(dict(status=value['status'],session=str(path),roles={r:v['pid'] for r,v in observed.items()},
        mod_state='dormant: waiting for current native declarations',complete_mod=False),ensure_ascii=False),flush=True)
    return value


def retry_uninitialized_game(path,role):
    """Retry official activation only before the engine can have a gameplay World."""
    path,value=load_run(path)
    assert role in BOXES and value.get('official_game_auth') and time.time()+120<value['expires_at']
    from phantom_boss_online_readonly import OnlineGameRead
    with OnlineGameRead(path,role,require_initialized=False) as game:
        assert game.count<100,'Preserve an initialized research game; do not restart gameplay'
    for owner in BOXES:
        assert not (virtual(owner,GAME/'platform/steam/ue4ss/Mods/PBZCoop/Scripts/bwb_current_bindings.lua')).exists(), \
            'Do not restart a process after native control declarations have been supplied'
    identity=value['instances'][role]['game_identity']
    dll=api();assert terminate_owned(dll,role,identity),'The original uninitialized role game was not stopped'
    deadline=time.monotonic()+8
    while identity['pid'] in pids(dll,BOXES[role]) and time.monotonic()<deadline:time.sleep(.2)
    assert identity['pid'] not in pids(dll,BOXES[role])
    value.setdefault('retired_uninitialized_games',[]).append(dict(role=role,reason='official authentication network was enabled after startup',**identity))
    value['instances'][role].update(game_pid=None,game_identity=None)
    value['status']='games-starting';atomic(path,value)
    time.sleep(2)
    result=bootstrap(path,role,'game');assert result['official_logged_on'] and result['resumed']
    print(json.dumps(dict(role=role,official_retry_requested=True,lease_extended=False,
        initialized_game_restarted=False)),flush=True)


def bootstrap(path,role,action,timeout=35):
    path,value=load_run(path);assert role in BOXES and action in ('probe','client','client-online','inspect','game')
    assert type(value['expires_at']) is int and time.time()<value['expires_at']
    assert digest(value['bootstrap'])==value['bootstrap_sha256']
    verify_policy(api(),role,False,value.get('official_steam_online',False),value.get('official_game_auth',False),
        compatible=value.get('compatibility_requested',False))
    output=path.parent/(role+'-'+action+'-'+uuid.uuid4().hex+'.json')
    lease=path.parent/(role+'-bootstrap.ini')
    result=subprocess.run([str(SBIE/'Start.exe'),'/box:'+BOXES[role],'/silent','/hide_window','/wait',
        value['bootstrap'],action,role,str(lease),str(output)],capture_output=True,timeout=timeout,
        creationflags=subprocess.CREATE_NO_WINDOW)
    physical=virtual(role,output)
    data=json.loads(physical.read_bytes()) if physical.is_file() else {}
    assert result.returncode==0,'Official '+role+'/'+action+' refused (exit '+str(result.returncode)+')'
    assert data.get('box_verified') and data.get('lease_verified') and data.get('role')==role
    return data


def network_policy(online,game_auth=False,compatible=False):
    dll=api();errors=[]
    for role,box in BOXES.items():
        rules=settings(role,False,online,game_auth)['NetworkAccess']
        try:
            change('set',box,'NetworkAccess',rules[0])
            for rule in rules[1:]:change('append',box,'NetworkAccess',rule)
        except Exception as error:
            if online:raise
            errors.append(role+' network rollback write: '+type(error).__name__)
    # A separate compatibility failure in one role must never leave the other
    # role's temporary public Steam exception in place. Write both first and
    # report every failed readback instead of aborting recovery at the first.
    for role in BOXES:
        try:
            if compatible:verify_policy(dll,role,False,online,game_auth,compatible=True)
            else:verify_policy(dll,role,False,online,game_auth)
        except Exception as error:
            if online:raise
            errors.append(role+' network rollback verify: '+type(error).__name__)
    if errors:raise RuntimeError('; '.join(errors))


def game_network(path):
    path,value=load_run(path)
    assert value.get('official_steam_online') is True and time.time()<value['expires_at']
    assert value['status'] in ('clients-ready','games-starting','games-waiting','games-start-timeout','partial-active','active')
    if not value.get('official_game_auth'):
        for role in BOXES:verify_policy(api(),role,False,True,False,compatible=value.get('compatibility_requested',False))
    else:
        configured=sections()
        for role,box in BOXES.items():
            rules=[line.split('=',1)[1] for line in configured[box] if line.startswith('NetworkAccess=')]
            expected=settings(role,False,True,True)['NetworkAccess']
            assert rules in (expected,expected[:-1]),'Preserve an unexpected research network policy'
    value['official_game_auth']=True;atomic(path,value)
    network_policy(True,True,compatible=value.get('compatibility_requested',False))
    print(json.dumps(dict(official_game_auth=True,scope='two research PBZ.exe processes; TCP and DNS only',
        expires_at=value['expires_at'],watchdog_restores_loopback=True)),flush=True)


def start_clients(path,official_online=False,compatible=False):
    path,value=load_run(path);assert value['status']=='prepared'
    dll=api();verify_clients()
    for role,box in BOXES.items():verify_policy(dll,role,False);assert not pids(dll,box)
    for row in value['deployed']:assert row['status']=='installed' and digest(row['path'])==row['sha256']
    now=int(time.time());value.update(issued_at=now,expires_at=now+value['duration_seconds'],status='clients-starting',
        official_steam_online=official_online,compatibility_requested=compatible)
    if compatible:
        from phantom_boss_pair_compatibility import probe_exe
        value['compatibility_probe']=str(probe_exe())
        configured=sections()
        value['compatibility_prior']={role:{key:[line.split('=',1)[1] for line in configured[box]
            if line.startswith(key+'=')] for key in ('UnstrippedToken','ClosedFilePath')} for role,box in BOXES.items()}
    for role in BOXES:
        lease=''.join(f'{key}={item}\n' for key,item in dict(mode=value['mode'],role=role,session=value['session'],
            issued_at=now,expires_at=value['expires_at']).items()).encode()
        (path.parent/(role+'-bootstrap.ini')).write_bytes(lease)
        mod=virtual(role,GAME/'platform/steam/ue4ss/Mods/PBZCoop')
        assert not (mod/'bwb_native_lease.ini').exists()
        (mod/'bwb_native_lease.ini').write_bytes(lease)
        gate=dict(mode=value['mode'],role=role,session=value['session'],activation=secrets.token_hex(16),
            issued_at=now,expires_at=value['expires_at'],binding='bwb_current_bindings.lua',boss_id=value['bosses'][role])
        value['instances'][role]['activation']=gate['activation']
        (mod/'Scripts/bwb_gate.ini').write_bytes(''.join(f'{key}={item}\n' for key,item in gate.items()).encode())
    atomic(path,value)
    watchdog=subprocess.Popen([sys.executable,str(Path(__file__)),'--watch',str(path)],cwd=ROOT,
        creationflags=subprocess.CREATE_NO_WINDOW,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    # Only this process owns the session journal. The watchdog writes separate
    # watch.json and stop markers so concurrent updates cannot discard receipts.
    value['watchdog_pid']=watchdog.pid;atomic(path,value)
    ready_until=time.monotonic()+10
    while not (path.parent/'watch.json').exists() and time.monotonic()<ready_until and watchdog.poll() is None:time.sleep(.1)
    assert watchdog.poll() is None and (path.parent/'watch.json').is_file(),'Independent watchdog did not become ready'
    if compatible:
        from phantom_boss_pair_compatibility import policy,probe
        try:
            policy(True)
            for role in BOXES:verify_policy(dll,role,False,compatible=True)
            proof=probe(path.parent,Path(value['compatibility_probe']))
            assert formal_files()==value['formal_before'],'Formal files changed during compatible Saved sentinel'
            atomic(path.parent/'compatibility-probe.json',proof)
            value['compatibility_probe_passed']=True;atomic(path,value)
        except Exception:
            request_stop(path,'compatible Saved sentinel failed');raise
    if official_online:network_policy(True,compatible=compatible)
    for role in BOXES:
        data=bootstrap(path,role,'client-online' if official_online else 'client')
        assert data['created'] and data['child_box_verified'] and data['resumed']
        value['instances'][role]['client_started']=True;value['steam_started']=True;atomic(path,value)
    value['status']='clients-running';atomic(path,value)
    print(json.dumps(dict(session=str(path),status=value['status'],game_started=False,
        expires_at=value['expires_at']),ensure_ascii=False),flush=True)
    return value


def inspect_clients(path):
    path,value=load_run(path);assert value['status'] in ('clients-running','clients-ready')
    results={role:bootstrap(path,role,'inspect') for role in BOXES}
    for role,row in results.items():
        value['instances'][role]['official_existing_user']=bool(row['official_existing_user'])
    ready=all(row['official_existing_user'] and row['official_logged_on'] for row in results.values())
    value['status']='clients-ready' if ready else 'clients-running';atomic(path,value)
    print(json.dumps(dict(status=value['status'],roles={role:dict(same_box=row['active_client_in_same_box'],
        official_existing_user=row['official_existing_user'],official_logged_on=row['official_logged_on'])
        for role,row in results.items()},game_started=False)),flush=True)
    return ready


def show_clients(path):
    path,value=load_run(path);assert value['status'] in ('clients-running','clients-ready')
    assert time.time()<value['expires_at']
    dll=api()
    for role in BOXES:
        verify_policy(dll,role,False,value.get('official_steam_online',False),value.get('official_game_auth',False),
            compatible=value.get('compatibility_requested',False))
        assert pids(dll,BOXES[role]),'Existing research client required'
        result=subprocess.run([str(SBIE/'Start.exe'),'/box:'+BOXES[role],'/silent',
            str(LOGICAL/'steam.exe'),'steam://open/main'],capture_output=True,timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW)
        assert result.returncode==0,'Could not show '+role+' research Steam'


def start_games(path):
    path,value=load_run(path);assert value['status']=='clients-ready'
    assert inspect_clients(path),'Two independent officially logged-on Steam clients required'
    assert time.time()+180<value['expires_at'],'Insufficient lease time for a complete acceptance pass'
    dll=api()
    assert not discover_games(dll),'Preserve an existing role game'
    value['status']='games-starting';atomic(path,value)
    for role in BOXES:
        data=bootstrap(path,role,'game');assert data['official_existing_user'] and data['resumed']
        value['instances'][role]['game_requested']=True;atomic(path,value)
    deadline=min(time.monotonic()+30,time.monotonic()+value['expires_at']-time.time())
    while time.monotonic()<deadline:
        observed=discover_games(dll)
        if len(observed)==2:
            for role,row in observed.items():value['instances'][role].update(game_pid=row['pid'],game_identity=row)
            value.update(status='active',game_started=True);atomic(path,value)
            print(json.dumps(dict(status='active',session=str(path),roles={r:v['pid'] for r,v in observed.items()},
                mod_state='dormant: waiting for current native declarations',complete_mod=False),ensure_ascii=False),flush=True)
            return value
        time.sleep(1)
    return observe_games(path) # Steam's official shader/update queue can finish later


def request_stop(path,reason='requested'):
    path,value=load_run(path)
    atomic(path.parent/'stop.json',dict(reason=reason,at=int(time.time()),session=value['session']))
    for role in BOXES:
        mod=virtual(role,GAME/'platform/steam/ue4ss/Mods/PBZCoop')
        (mod/'Scripts/bwb_stop.txt').write_bytes(b'stop\n')


def terminate_owned(dll,role,identity):
    if identity['pid'] not in pids(dll,BOXES[role]):return False
    if process_identity(identity['pid'])!=identity:return False
    k=ctypes.WinDLL('kernel32',use_last_error=True)
    k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];k.OpenProcess.restype=w.HANDLE
    k.TerminateProcess.argtypes=[w.HANDLE,w.UINT];k.CloseHandle.argtypes=[w.HANDLE]
    handle=k.OpenProcess(0x1001,False,identity['pid'])
    if not handle:return False
    try:
        # Recheck after opening a handle; creation identity prevents PID reuse.
        return bool(process_identity(identity['pid'])==identity and k.TerminateProcess(handle,0))
    finally:k.CloseHandle(handle)


def watch(path):
    path,value=load_run(path);assert type(value['expires_at']) is int
    dll=api();known={role:{} for role in BOXES};reason='lease expired'
    try:
        while time.time()<value['expires_at']:
            for role,box in BOXES.items():
                for pid in pids(dll,box):
                    row=process_identity(pid)
                    if row and Path(row['image']).name.casefold() in ('steam.exe','steamwebhelper.exe','pbz.exe','crashreportclient.exe','isolation_probe.exe'):
                        image=Path(row['image']).resolve()
                        if image.is_relative_to(LOGICAL.resolve()) or image.is_relative_to(virtual(role,LOGICAL).resolve()) \
                                or image in ((GAME/'steam/PBZ.exe').resolve(),(GAME/'platform/steam/PBZ.exe').resolve()) \
                                or (value.get('compatibility_probe') and image==Path(value['compatibility_probe']).resolve()):
                            known[role][pid]=row
            atomic(path.parent/'watch.json',dict(status='watching',at=int(time.time()),
                processes={role:list(rows.values()) for role,rows in known.items()},expires_at=value['expires_at']))
            if (path.parent/'stop.json').exists():reason='launcher stop requested';break
            time.sleep(1)
    except Exception as error:reason='watch failed: '+type(error).__name__
    try:request_stop(path,reason)
    except Exception as error:reason+='; stop marker failed: '+type(error).__name__
    # Allow the Lua game-thread owner to restore player/camera/input first.
    time.sleep(10)
    terminated=[]
    cleanup_errors=[]
    for role,rows in known.items():
        for row in sorted(rows.values(),key=lambda r:Path(r['image']).name.casefold()!='pbz.exe'):
            try:
                if terminate_owned(dll,role,row):terminated.append(dict(role=role,**row))
            except Exception as error:cleanup_errors.append(type(error).__name__)
    compatibility_restored=not value.get('compatibility_requested')
    if not compatibility_restored:
        from phantom_boss_pair_compatibility import policy
        for attempt in range(3):
            try:policy(False,value.get('compatibility_prior'));compatibility_restored=True;break
            except Exception as error:
                cleanup_errors.append('compatibility rollback: '+type(error).__name__);time.sleep(1)
    restored=not value.get('official_steam_online')
    if not restored:
        for attempt in range(3):
            try:network_policy(False);restored=True;break
            except Exception as error:
                cleanup_errors.append('network rollback: '+type(error).__name__);time.sleep(1)
    atomic(path.parent/'watch.json',dict(status='stopped',reason=reason,at=int(time.time()),
        terminated=terminated,saves_restored=False,temporary_steam_network_restored=restored,
        compatibility_restored=compatibility_restored,cleanup_errors=cleanup_errors,
        formal_files_unchanged=formal_files()==value['formal_before']))


def cleanup(path):
    path,value=load_run(path);dll=api()
    assert all(not pids(dll,box) for box in BOXES.values()),'Exit both research containers before cleanup'
    controls=[]
    from issue_phantom_boss_control_binding import owned_files
    for role in BOXES:
        mod=virtual(role,GAME/'platform/steam/ue4ss/Mods/PBZCoop')
        lease=mod/'bwb_native_lease.ini';gate=mod/'Scripts/bwb_gate.ini'
        if lease.exists():
            pairs=dict(line.split('=',1) for line in lease.read_text(encoding='ascii').splitlines())
            assert pairs['session']==value['session'] and pairs['role']==role
            controls.append(lease)
        if gate.exists():
            pairs=dict(line.split('=',1) for line in gate.read_text(encoding='ascii').splitlines())
            assert pairs['session']==value['session'] and pairs['role']==role
            controls.append(gate)
        # The issuer records both final and pending ownership before publishing.
        # Refuse unknown or changed declarations before removing any payload.
        controls.extend(owned_files(path,value,role,resolver=virtual))
        stop=mod/'Scripts/bwb_stop.txt'
        if stop.exists():assert stop.read_bytes()==b'stop\n';controls.append(stop)
    for row in value['deployed']:
        target=Path(row['path']);assert target.is_relative_to(Path(virtual(row['role'],GAME)))
        if target.exists():assert digest(target)==row['sha256'],'Preserve changed research payload: '+str(target)
    for row in reversed(value['deployed']):
        target=Path(row['path'])
        if target.exists():target.unlink()
    for target in controls:
        if target.exists():target.unlink()
    value.update(status='cleaned',saves_restored=False,formal_files_unchanged=formal_files()==value['formal_before'])
    atomic(path,value)
    print(json.dumps(dict(status='cleaned',research_progress='preserved',formal_files_unchanged=value['formal_files_unchanged'])),flush=True)


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    parser=argparse.ArgumentParser(description=__doc__)
    actions=parser.add_mutually_exclusive_group(required=True)
    for action in ('prepare','clients','clients-online','clients-online-compatible','inspect','show','games','observe','game-network','retry-uninitialized','stop','watch','cleanup'):actions.add_argument('--'+action,type=Path)
    parser.add_argument('--role',choices=tuple(BOXES))
    args=parser.parse_args()
    if args.prepare:prepare(args.prepare)
    elif args.clients:start_clients(args.clients)
    elif args.clients_online:start_clients(args.clients_online,official_online=True)
    elif args.clients_online_compatible:start_clients(args.clients_online_compatible,official_online=True,compatible=True)
    elif args.inspect:inspect_clients(args.inspect)
    elif args.show:show_clients(args.show)
    elif args.games:start_games(args.games)
    elif args.observe:observe_games(args.observe)
    elif args.game_network:game_network(args.game_network)
    elif args.retry_uninitialized:
        assert args.role,'Explicit --role required for an uninitialized official retry'
        retry_uninitialized_game(args.retry_uninitialized,args.role)
    elif args.stop:request_stop(args.stop)
    elif args.watch:watch(args.watch)
    elif args.cleanup:cleanup(args.cleanup)
