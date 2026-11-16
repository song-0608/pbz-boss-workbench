"""Prepare and prove two dedicated Sandboxie containers using sentinels only."""
import argparse
import ctypes
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import uuid

from build_phantom_boss_candidate import ROOT, canonical, sha
from build_phantom_boss_native import compiler_environment
from check_phantom_boss_native import verify_build
from run_sandbox_baseline import formal_files

SBIE = Path(r'E:\Sandboxie-Plus')
GAME = Path(r'E:\SteamLibrary\steamapps\common\PBZ')
BOXES = dict(host='PBZOnlineHost', guest='PBZOnlineGuest')
PROBE_SOURCE = 'tools/phantom_boss_isolation_probe.cpp'


def settings(role, probes=False):
    box = BOXES[role]
    other = BOXES['guest' if role == 'host' else 'host']
    rules = ['*,Block', 'PBZ.exe,Allow;Address=127.0.0.1;Protocol=UDP',
        *[f'{image},Allow;Address={address};Protocol=TCP' for image in ('steam.exe','steamwebhelper.exe')
          for address in ('127.0.0.1','::1')]]
    if probes:
        rules.append('bootstrap_probe.exe,Allow;Address=127.0.0.1;Protocol=UDP')
    return dict(Enabled=['y'], AutoRecover=['n'], AutoDelete=['n'], NeverDelete=['y'],
        DropAdminRights=['y'], SeparateUserFolders=['n'], BoxNameTitle=['y'],
        BorderColor=['#48B0FF,ttl' if role == 'host' else '#B080FF,ttl'],
        Template=['BlockPorts'],
        FileRootPath=[str(SBIE / (box+'Root'))], NetworkEnableWFP=['y'], AllowNetworkAccess=['y'],
        NetworkAccess=rules, NormalFilePath=[r'\Device\NamedPipe\*steam*'],
        ClosedFilePath=[r'D:\steam\*', str(SBIE / (other+'Root'))+'\\*'])


def api():
    dll = ctypes.WinDLL(str(SBIE / 'SbieDll.dll'))
    dll.SbieApi_QueryConf.argtypes = [w.LPCWSTR,w.LPCWSTR,w.ULONG,w.LPWSTR,w.ULONG]
    dll.SbieApi_QueryConf.restype = w.LONG
    dll.SbieApi_EnumBoxes.argtypes = [ctypes.c_int,w.LPWSTR]
    dll.SbieApi_EnumBoxes.restype = ctypes.c_int
    dll.SbieApi_EnumProcessEx.argtypes = [w.LPCWSTR,ctypes.c_ubyte,w.ULONG,ctypes.POINTER(w.ULONG),ctypes.POINTER(w.ULONG)]
    dll.SbieApi_EnumProcessEx.restype = w.LONG
    return dll


def box_names(dll):
    index, result = -1, []
    for _ in range(256):
        name=ctypes.create_unicode_buffer(64)
        index=dll.SbieApi_EnumBoxes(index,name)
        if index<0:
            return result
        result.append(name.value)
    raise RuntimeError('Unexpected Sandboxie box enumeration bound')


def values(dll,box,key):
    result=[]
    for index in range(256):
        buf=ctypes.create_unicode_buffer(8192)
        if dll.SbieApi_QueryConf(box,key,index,buf,ctypes.sizeof(buf))!=0:
            return result
        result.append(buf.value)
    raise RuntimeError('Unexpected Sandboxie setting bound')


def pids(dll,box):
    out=(w.ULONG*512)()
    assert dll.SbieApi_EnumProcessEx(box,False,0xffffffff,out,None)==0 and out[0]<=511
    return list(out)[1:out[0]+1]


def change(operation,box,key,value=None):
    assert box in BOXES.values(), 'Only dedicated online research containers may change'
    command=[str(SBIE/'SbieIni.exe'),operation,box,key]
    if value is not None:
        command.append(value)
    subprocess.run(command,capture_output=True,check=True,timeout=15,creationflags=subprocess.CREATE_NO_WINDOW)


def sections():
    raw=Path(r'C:\Windows\Sandboxie.ini').read_bytes()
    text=raw.decode('utf-16' if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig')
    result={};current=None
    for line in text.splitlines():
        line=line.strip()
        if line.startswith('[') and line.endswith(']'):
            current=line[1:-1];result[current]=[]
        elif current is not None and '=' in line and not line.startswith(('#',';')):
            result[current].append(line)
    return result


def verify_policy(dll,role,probes):
    box=BOXES[role]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.QueryDosDeviceW.argtypes=[w.LPCWSTR,w.LPWSTR,w.DWORD]
    kernel.QueryDosDeviceW.restype=w.DWORD
    def native_path(text):
        if len(text)>2 and text[1:3]==':\\':
            target=ctypes.create_unicode_buffer(4096)
            assert kernel.QueryDosDeviceW(text[:2],target,len(target))
            return target.value+text[2:]
        return text
    raw=sections()[box]
    for key,expected in settings(role,probes).items():
        configured=[line.split('=',1)[1] for line in raw if line.split('=',1)[0]==key]
        assert configured==expected, 'Unexpected configured online setting: '+box+'/'+key
        actual=values(dll,box,key)
        expected=[native_path(row) for row in expected]
        if key=='NetworkEnableWFP':
            valid=bool(actual) and set(actual)=={'y'}
        elif key=='NetworkAccess':
            # The standard inherited BlockPorts template adds a denial, never an
            # extra permitted destination. Preserve and record that restriction.
            valid=actual[:len(expected)]==expected and all(row=='*,Block;Port=137,138,139,445' for row in actual[len(expected):])
        elif key=='ClosedFilePath':
            valid=all(row in actual for row in expected)
        else:
            valid=actual==expected
        assert valid, 'Unexpected effective online container setting: '+box+'/'+key
    # Sandboxie's built-in web-cache endpoints are present even without a local
    # template. They do not expose the Steam client or either Saved path.
    assert values(dll,box,'OpenIpcPath') in ([],[r'\RPC Control\webcache_*',
        r'*\BaseNamedObjects\windows_webcache_counters_*']), 'Unexpected host IPC exception'
    for key in ('OpenFilePath','OpenPipePath','BreakoutProcess','BreakoutFolder',
                'NoSecurityIsolation','UnfilteredToken','KeepTokenIntegrity','UnstrippedToken','NoUntrustedToken'):
        assert values(dll,box,key) in ([],['n']), 'Unexpected online isolation exception: '+box+'/'+key


def virtual(role,logical):
    root=Path(settings(role)['FileRootPath'][0])
    return root/'drive'/logical.drive[0]/str(logical)[3:]


def compile_probe(work):
    env,compiler=compiler_environment()
    probe=work/'isolation_probe.exe'
    cmd=[str(compiler),'/nologo','/std:c++20','/O2','/MT','/EHsc','/W3','/utf-8','/Brepro',
         '/Fo:'+str(work/'isolation_probe.obj'),str(ROOT/PROBE_SOURCE),'/Fe:'+str(probe),'/link','/Brepro']
    result=subprocess.run(cmd,cwd=work,env=env,capture_output=True,timeout=90)
    (work/'compile.txt').write_bytes(result.stdout+result.stderr)
    assert result.returncode==0, (result.stdout+result.stderr).decode('mbcs',errors='replace')[-1500:]
    return probe


def prepare(native_build, resume=None):
    native_build=Path(native_build).resolve()
    native=verify_build(native_build)
    dll=api()
    existing=sections()
    if resume is None:
        assert not any(box.casefold() in {name.casefold() for name in existing} for box in BOXES.values()), \
            'Dedicated online box already exists; preserve it for inspection, do not overwrite'
        assert not any(Path(settings(role)['FileRootPath'][0]).exists() for role in BOXES), \
            'Existing container data must not be reused without a receipt'
    else:
        resume=Path(resume).resolve()
        assert resume.is_relative_to(ROOT/'runtime/online-isolation') and resume.name=='isolation.json'
        prior=json.loads(resume.read_bytes())
        assert prior['boxes']==BOXES and prior['status'] in ('preparing','failed','cleanup-pending')
        assert prior['game_started'] is False and prior['installed'] is False and prior['lease_issued'] is False
        # A new standalone probe can add durable result output after Sandboxie's
        # launcher proved it does not forward stdout. Source verification above
        # still pins the new build; the old failed probe is retained separately.
        assert prior['source_sha256'][PROBE_SOURCE]==sha((ROOT/PROBE_SOURCE).read_bytes())
        assert all(not pids(dll,box) for box in BOXES.values()), 'Do not resume an occupied container'
    previous={name:rows for name,rows in existing.items() if name not in BOXES.values()}
    before=formal_files()
    work=ROOT/'runtime/online-isolation'/uuid.uuid4().hex
    work.mkdir(parents=True)
    if resume:
        import shutil
        old_probe=resume.parent/'isolation_probe.exe'
        assert sha(old_probe.read_bytes())==prior['probe_sha256']
        probe=work/'isolation_probe.exe';shutil.copyfile(old_probe,probe)
    else:
        probe=compile_probe(work)
    receipt=dict(schema=1,status='preparing',game_started=False,installed=False,lease_issued=False,
        complete_mod=False,runtime_acceptance_current=False,boxes=BOXES,
        native_build=native_build.relative_to(ROOT).as_posix(),
        native_build_manifest_sha256=sha((native_build/'native-build.json').read_bytes()),
        existing_section_sha256={name:sha(canonical(rows)) for name,rows in previous.items()},
        source_sha256={name:sha((ROOT/name).read_bytes()) for name in (
            PROBE_SOURCE,'tools/check_phantom_boss_isolation.py')},probe_sha256=sha(probe.read_bytes()),checks=[])
    path=work/'isolation.json'
    def save():path.write_bytes(canonical(receipt)+b'\n')
    save()
    try:
        for role,box in BOXES.items():
            change('set',box,'Enabled','y')
            # Sandboxie's UI initializes defaults for a new section. Let that
            # finish before writing the complete dedicated policy and reading it back.
            time.sleep(1)
            for key,rows in settings(role,True).items():
                change('set',box,key,rows[0])
                for row in rows[1:]:change('append',box,key,row)
            # A newly created box can receive an initial UI border after other
            # policy values; reapply this display-only setting before verification.
            change('set',box,'BorderColor',settings(role,True)['BorderColor'][0])
            verify_policy(dll,role,True)
            assert not pids(dll,box), 'New online box unexpectedly occupied'
        assert all(sections().get(name)==rows for name,rows in previous.items()), 'Existing box configuration changed'

        marker_name='BWBOnlineProbe_'+uuid.uuid4().hex+'.tmp'
        markers=[Path(os.environ['LOCALAPPDATA'])/'ProjectPBZ/Saved'/marker_name,
                 GAME/'ProjectPBZ/Saved'/marker_name]
        assert not any(p.exists() for p in markers)
        tokens={role:secrets.token_hex(16) for role in BOXES}
        for mode in ('write','read'):
            for role,box in BOXES.items():
                logical=work/(role+'-'+mode+'.json')
                result=subprocess.run([str(SBIE/'Start.exe'),'/box:'+box,'/silent','/hide_window','/wait',
                    str(probe),box,mode,*map(str,markers),tokens[role],str(logical)],
                    capture_output=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
                report=virtual(role,logical)
                assert result.returncode==0 and report.is_file(), 'Boxed Saved sentinel did not complete: '+role+'/'+mode
                data=json.loads(report.read_bytes())
                assert data==dict(sandbox_verified=True,local_saved=True,installed_saved=True), 'Saved virtualization failed'
                for marker in markers:
                    assert not marker.exists(), 'Host marker unexpectedly present'
                    assert virtual(role,marker).read_bytes()==tokens[role].encode(), 'Private Saved marker mismatch'
                receipt['checks'].append(dict(name=role+'-'+mode,passed=True,details=data,
                    report=report.as_posix(),report_sha256=sha(report.read_bytes())))
        receipt['saved_paths_verified']=[str(marker.parent) for marker in markers]
        # The relay already has host-side signed communication coverage. This
        # check now runs that exact standalone bootstrap inside both containers.
        import socket
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as port_probe:
            port_probe.bind(('127.0.0.1',0));port=port_probe.getsockname()[1]
        secret=secrets.token_hex(32);session=secrets.token_hex(16);now=int(time.time())
        from prepare_phantom_boss_pair import ini
        processes=[]
        try:
            for role,box in BOXES.items():
                folder=work/role;folder.mkdir()
                (folder/'PhantomPact.ini').write_bytes(ini(role,port,secret))
                (folder/'bwb_native_lease.ini').write_text(
                    f'mode=two-player-online-research\nissued_at={now-1}\nexpires_at={now+14}\nrole={role}\nsession={session}\n',encoding='utf-8')
                (folder/'net_start.txt').write_text(
                    f'role={"host" if role=="host" else "client"}\nport={port}\npeer=127.0.0.1\ntransport=udp\nversion=1.7.3\n',encoding='utf-8')
                processes.append(subprocess.Popen([str(SBIE/'Start.exe'),'/box:'+box,'/silent','/hide_window',
                    str(native_build/'bootstrap_probe.exe'),'exchange',str(folder)],
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW))
                # Start.exe initializes per-box helper processes through one
                # service. Wait for each scoped process to appear before asking
                # it to initialize the second box.
                launch_deadline=time.monotonic()+5
                while time.monotonic()<launch_deadline and not pids(dll,box):
                    if processes[-1].poll() not in (None,0):break
                    time.sleep(.1)
                time.sleep(.3)
            outputs=[p.communicate(timeout=25) for p in processes]
        finally:
            for p in processes:
                if p.poll() is None:p.kill();p.communicate(timeout=5)
        raw=b'\n'.join(out+err for out,err in outputs)
        receipt['relay_launch_exit_codes']=[p.returncode for p in processes]
        save()
        deadline=time.monotonic()+22
        while time.monotonic()<deadline and not all(virtual(role,work/role/'bootstrap_result.txt').is_file() for role in BOXES):
            time.sleep(.2)
        for role in BOXES:
            result=virtual(role,work/role/'bootstrap_result.txt')
            assert result.is_file(), 'Missing durable boxed bootstrap result: '+role
            raw+=b'\n'+result.read_bytes()
        (work/'boxed-relay.txt').write_bytes(raw)
        assert all(p.returncode==0 for p in processes) and raw.count(b'connected=1 sample=1 event=1 reset=1')==2, \
            'Two-container standalone relay did not pass: '+raw.decode(errors='replace')[-800:]
        receipt['checks'].append(dict(name='two-container-signed-relay',passed=True,
            output=(work/'boxed-relay.txt').relative_to(ROOT).as_posix(),output_sha256=sha(raw)))
        for role,box in BOXES.items():
            # Remove only our probe permission, retaining the real game/client scope.
            change('delete',box,'NetworkAccess','bootstrap_probe.exe,Allow;Address=127.0.0.1;Protocol=UDP')
            verify_policy(dll,role,False)
            for marker in markers:
                physical=virtual(role,marker)
                assert physical.read_bytes()==tokens[role].encode()
                physical.unlink()
        assert formal_files()==before, 'Formal files changed during sentinel test'
        assert all(sections().get(name)==rows for name,rows in previous.items()), 'Existing box configuration changed'
        receipt.update(status='sentinel-and-relay-proven-only',passed=True,formal_files_unchanged=True,
            existing_box_settings_unchanged=True,independent_saved_paths_proven=True,
            game_saved_redirection_live_accepted=False,standalone_relay_executed=True,
            policies={role:settings(role) for role in BOXES},native_files=native['files'])
    except BaseException as error:
        receipt.update(status='failed',passed=False,error=str(error))
        save()
        # Only these newly created containers are disabled; never alter old boxes.
        for box in BOXES.values():
            change('set',box,'AllowNetworkAccess','n')
            change('set',box,'Enabled','n')
        raise
    finally:
        for box in BOXES.values():
            if pids(dll,box):
                try:
                    subprocess.run([str(SBIE/'Start.exe'),'/box:'+box,'/silent','/hide_window','/terminate'],
                        capture_output=True,timeout=15,creationflags=subprocess.CREATE_NO_WINDOW)
                except subprocess.TimeoutExpired:
                    receipt.setdefault('cleanup_errors',[]).append(box+' terminate request timed out')
        receipt['remaining_box_pids']={box:pids(dll,box) for box in BOXES.values()}
        if any(receipt['remaining_box_pids'].values()):
            receipt.update(passed=False,status='cleanup-pending')
        save()
    assert receipt['passed'] is True, 'Dedicated probe process cleanup incomplete'
    print(json.dumps(dict(receipt=str(path),passed=True,game_started=False),ensure_ascii=False))
    return path


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('native_build',type=Path)
    parser.add_argument('--prepare-and-probe',action='store_true')
    parser.add_argument('--resume',type=Path)
    args=parser.parse_args()
    if args.prepare_and_probe:prepare(args.native_build,args.resume)
    else:print(json.dumps({role:settings(role) for role in BOXES},ensure_ascii=False,indent=2))
