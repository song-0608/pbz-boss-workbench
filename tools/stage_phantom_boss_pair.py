"""Assemble two inert same-PC research payloads; never install, issue a lease or launch."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import uuid

from build_phantom_boss_candidate import ROOT, SOURCES, canonical, safe_file, sha, verify_candidate, verify_release
from build_phantom_boss_native import sources
from check_phantom_boss_native import verify_build
from prepare_phantom_boss_pair import ROLES, prepare, verify as verify_pair
from pbz_ue4ss_baseline import verified_build_record
from verify_phantom_boss_backend import verify as verify_backend

MODULES=('main','lang','lang_ar','pbz','coop','status','moves','puppets','hitfx','autostart')
from research_storage import container_path
RESEARCH_SAVED=container_path()/'drive/E/SteamLibrary/steamapps/common/PBZ/ProjectPBZ/Saved'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def loader_settings(text):
    # Keep the accepted object cache; disable hot reload so recovery ownership
    # cannot be discarded by replacing Lua while a Boss is active.
    for key in re.findall(r'(?m)^(Hook\w+)\s*=',text):
        text=re.sub(r'(?m)^'+key+r'\s*=.*$',key+' = 0',text)
    values=dict(ConsoleEnabled='0',GuiConsoleEnabled='0',GuiConsoleVisible='0',
        UseCache='0',DoEarlyScan='0',SecondsToScanBeforeGivingUp='40',
        bUseUObjectArrayCache='true',bForceGUObjectArrayForIteration='true',
        EnableHotReloadSystem='0',HookEngineTick='1',EngineTickResolveMethod='Scan',HookLoadMap='1')
    for key,value in values.items():
        text,count=re.subn(r'(?m)^'+key+r'\s*=.*$',key+' = '+value,text)
        assert count==1,'Missing/ambiguous loader setting: '+key
    return text.encode('utf-8')


def save_snapshot(source):
    source=Path(source).resolve()
    assert source.is_dir() and not source.is_symlink() and not source.is_junction()
    result={}
    for path in sorted(source.rglob('*')):
        assert not path.is_symlink() and not path.is_junction(),'Linked research save is not a snapshot'
        if path.is_file() and path.suffix.lower()=='.sav':
            name=path.relative_to(source).as_posix()
            assert name.startswith('SaveGames/') or '/' not in name,'Unexpected save location'
            result[name]=dict(bytes=path.stat().st_size,sha256=digest(path))
    assert result and any(name.startswith('SaveGames/') for name in result),'Current research progress required'
    return result


def copy_snapshot(source,target,expected):
    assert save_snapshot(source)==expected,'Research progress changed before copying'
    target=Path(target)
    target.mkdir(parents=True,exist_ok=False)
    for name,row in expected.items():
        origin=safe_file(Path(source),name);destination=safe_file(target,name)
        destination.parent.mkdir(parents=True,exist_ok=True)
        with origin.open('rb') as src,destination.open('xb') as dst:
            shutil.copyfileobj(src,dst)
        assert destination.stat().st_size==row['bytes'] and digest(destination)==row['sha256']
    assert save_snapshot(source)==expected,'Research progress changed while copying'
    assert save_snapshot(target)==expected


def stage(native_build, candidate=None):
    backend=verify_backend()
    report=json.loads((ROOT/'evidence/adaptation/phantom-pact-backend.json').read_bytes())
    candidate=Path(candidate) if candidate else ROOT/report['candidate']
    manifest=verify_candidate(candidate)
    assert backend['candidate']==manifest['candidate_id']
    assert manifest['own_sources']=={name:sha((ROOT/name).read_bytes()) for name in SOURCES}
    native_build=Path(native_build).resolve();native=verify_build(native_build)
    upstream,receipt=sources()
    built,build_record=verified_build_record()
    # Copy only the current research progress, never a formal save or an old backup.
    from check_phantom_boss_isolation import api, pids, BOXES, verify_policy
    from run_sandbox_baseline import formal_files
    import preflight
    dll=api()
    assert not preflight.games_running(),'Preserve the active game; stage after it exits'
    assert not pids(dll,'PBZSteamLab'),'Research save source is in use'
    for role,box in BOXES.items():
        verify_policy(dll,role,False)
        assert not pids(dll,box),'Dedicated online container is occupied'
    formal_before=formal_files()
    snapshot=save_snapshot(RESEARCH_SAVED)
    target=ROOT/'runtime/online-stages'/uuid.uuid4().hex
    target.mkdir(parents=True)
    pair=prepare(candidate,output_parent=target/'pair')
    settings=loader_settings((ROOT.parent/'upstream/RE-UE4SS/assets/UE4SS-settings.ini').read_text(encoding='utf-8-sig'))
    profile=ROOT/'adaptation/pbz-26367565'
    profile_report=json.loads((ROOT/'evidence/adaptation/profile-verification.json').read_bytes())
    _,singleplayer=verify_release(ROOT)
    assert profile_report['passed'] and profile_report['exe_sha256']==singleplayer['exe_sha256']
    contents={'dwmapi.dll':None,'ue4ss/UE4SS.dll':None,
        'ue4ss/UE4SS-settings.ini':settings,'ue4ss/Mods/mods.txt':b'PBZCoop : 1\n',
        'ue4ss/Mods/PBZCoop/enabled.txt':b'1\n',
        'ue4ss/Mods/PBZCoop/dlls/main.dll':(native_build/'main.dll').read_bytes()}
    for name in ('dwmapi.dll','UE4SS.dll'):
        row=next(row for row in built['artifacts'] if Path(row['path']).name==name)
        contents[name if name=='dwmapi.dll' else 'ue4ss/UE4SS.dll']=Path(row['path']).read_bytes()
        assert sha(contents[name if name=='dwmapi.dll' else 'ue4ss/UE4SS.dll'])==row['sha256']
    for name in ('UE4SS_Signatures/GUObjectArray.lua','MemberVariableLayout.ini'):
        data=(profile/name).read_bytes();assert sha(data)==profile_report['files'][name]
        contents['ue4ss/'+name]=data
    for module in MODULES:
        name=module+'.lua';origin=upstream/'mod/PBZCoop/Scripts'/name
        assert sha(origin.read_bytes())==receipt['files']['mod/PBZCoop/Scripts/'+name]['sha256']
        patched=candidate/'upstream-local-patches'/name
        contents['ue4ss/Mods/PBZCoop/Scripts/'+name]=(patched if patched.is_file() else origin).read_bytes()
    for name in manifest['files']:
        if name.startswith('PBZCoop/'):
            contents['ue4ss/Mods/'+name]=safe_file(candidate,name).read_bytes()
    files={}
    for role in ROLES:
        root=target/role
        payload=root/'game/platform/steam'
        for name,data in contents.items():
            dest=safe_file(payload,name);dest.parent.mkdir(parents=True,exist_ok=True)
            with dest.open('xb') as stream:stream.write(data)
        config=(pair/role/'Mods/PBZCoop/PhantomPact.ini').read_bytes()
        (payload/'ue4ss/Mods/PBZCoop/PhantomPact.ini').write_bytes(config)
        for position in ('game/ProjectPBZ/Saved','local/ProjectPBZ/Saved'):
            copy_snapshot(RESEARCH_SAVED,root/position,snapshot)
        for path in root.rglob('*'):
            if path.is_file():files[path.relative_to(target).as_posix()]=digest(path)
    assert save_snapshot(RESEARCH_SAVED)==snapshot and formal_files()==formal_before
    staged=dict(schema=1,status='staged-inert',candidate=manifest['candidate_id'],
        candidate_directory=candidate.relative_to(ROOT).as_posix(),
        candidate_manifest_sha256=digest(candidate/'candidate.json'),
        native_build=native_build.relative_to(ROOT).as_posix(),native_manifest_sha256=digest(native_build/'native-build.json'),
        pair_directory=pair.relative_to(target).as_posix(),pair_manifest_sha256=digest(pair/'pair.json'),
        loader_verification_sha256=digest(build_record),source_sha256=digest(Path(__file__)),
        game_started=False,installed=False,lease_issued=False,complete_mod=False,runtime_acceptance_current=False,
        research_snapshot=snapshot,research_snapshot_sha256=sha(canonical(snapshot)),
        snapshot_copies=4,formal_files_unchanged=True,files=dict(sorted(files.items())))
    (target/'stage.json').write_bytes(canonical(staged)+b'\n')
    verify(target)
    print(json.dumps(dict(stage=str(target),files=len(files),research_saves=len(snapshot),
        installed=False,game_started=False,lease_issued=False),ensure_ascii=False))
    return target


def verify(target):
    target=Path(target).resolve();m=json.loads((target/'stage.json').read_bytes())
    assert m['schema']==1 and m['status']=='staged-inert'
    for name in ('game_started','installed','lease_issued','complete_mod','runtime_acceptance_current'):
        assert m[name] is False
    assert m['source_sha256']==digest(Path(__file__))
    candidate=safe_file(ROOT,m['candidate_directory']);c=verify_candidate(candidate)
    assert c['candidate_id']==m['candidate'] and digest(candidate/'candidate.json')==m['candidate_manifest_sha256']
    native=safe_file(ROOT,m['native_build']);verify_build(native)
    assert digest(native/'native-build.json')==m['native_manifest_sha256']
    pair=safe_file(target,m['pair_directory']);verify_pair(pair,candidate)
    assert digest(pair/'pair.json')==m['pair_manifest_sha256']
    assert sha(canonical(m['research_snapshot']))==m['research_snapshot_sha256'] and m['snapshot_copies']==4
    expected=set(m['files'])
    actual={p.relative_to(target).as_posix() for role in ROLES for p in (target/role).rglob('*') if p.is_file()}
    assert actual==expected
    for name,value in m['files'].items():
        assert digest(safe_file(target,name))==value,'Stage drift: '+name
    for role in ROLES:
        for position in ('game/ProjectPBZ/Saved','local/ProjectPBZ/Saved'):
            assert save_snapshot(target/role/position)==m['research_snapshot']
        script=target/role/'game/platform/steam/ue4ss/Mods/PBZCoop/Scripts/main.lua'
        assert script.read_bytes()==(candidate/'upstream-local-patches/main.lua').read_bytes()
        assert not any((target/role).rglob('bwb_native_lease.ini'))
        assert not any((target/role).rglob('net_start.txt'))
    return m


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-build',type=Path)
    parser.add_argument('--verify',type=Path)
    args=parser.parse_args()
    if args.verify:
        m=verify(args.verify);print(json.dumps(dict(passed=True,status=m['status'],files=len(m['files']))))
    else:
        assert args.native_build,'--native-build is required for staging'
        stage(args.native_build)
