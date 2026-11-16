"""Copy the current authorized research Steam client into two new role containers; never launch."""
import argparse
import json
from pathlib import Path
import shutil
import time
import uuid

from build_phantom_boss_candidate import ROOT,canonical,sha
from check_phantom_boss_isolation import BOXES,api,pids,virtual,verify_policy
from run_sandbox_baseline import formal_files
from stage_phantom_boss_pair import digest

SOURCE=ROOT/'sandbox/PBZSteamLab/drive/E/PBZSteamLabClient'
LOGICAL=Path(r'E:\PBZSteamLabClient')


def inventory(directory):
    directory=Path(directory).resolve()
    assert directory.is_dir() and not directory.is_symlink() and not directory.is_junction()
    result={}
    for path in sorted(directory.rglob('*')):
        assert not path.is_symlink() and not path.is_junction(),'Linked client content refused'
        if path.is_file():
            stat=path.stat();value=digest(path);after=path.stat()
            assert (stat.st_size,stat.st_mtime_ns)==(after.st_size,after.st_mtime_ns),'Client changed during snapshot'
            result[path.relative_to(directory).as_posix()]=dict(bytes=stat.st_size,sha256=value)
    assert 'steam.exe' in result and 'steamclient64.dll' in result and len(result)<=30000
    return result


def directory_layout(directory):
    directory=Path(directory).resolve();result=[]
    for path in sorted(directory.rglob('*')):
        assert not path.is_symlink() and not path.is_junction(),'Linked client layout refused'
        if path.is_dir():result.append(path.relative_to(directory).as_posix())
    return result


def complete_layout():
    """Add omitted empty directories to an already copied client; never copy files."""
    path=ROOT/'evidence/adaptation/phantom-pact-client-snapshots.json'
    summary=json.loads(path.read_bytes());receipt=ROOT/summary['receipt']
    assert digest(receipt)==summary['receipt_sha256']
    copied=json.loads(receipt.read_bytes());assert copied['status']=='copied-not-started'
    dll=api();before=formal_files();layout=directory_layout(SOURCE);created={}
    for role,box in BOXES.items():
        verify_policy(dll,role,False);assert not pids(dll,box)
        target=virtual(role,LOGICAL);assert target.is_dir()
        for name in ('steam.exe','steamclient64.dll'):assert digest(target/name)==copied['files'][name]['sha256']
        created[role]=[]
        for name in layout:
            destination=target/name
            assert not destination.is_symlink() and not destination.is_junction()
            if not destination.exists():destination.mkdir();created[role].append(name)
            assert destination.is_dir()
        assert all((target/name).is_dir() for name in layout)
    assert directory_layout(SOURCE)==layout and formal_files()==before
    directory=ROOT/'runtime/online-client-layouts'/uuid.uuid4().hex;directory.mkdir(parents=True)
    record=dict(schema=1,status='directory-layout-complete',source_receipt=summary['receipt'],
        source_receipt_sha256=summary['receipt_sha256'],directories=layout,created=created,
        files_overwritten=False,game_started=False,formal_files_unchanged=True,
        source_sha256=sha(Path(__file__).read_bytes()))
    target=directory/'layout.json';target.write_bytes(canonical(record)+b'\n')
    summary.update(layout_receipt=target.relative_to(ROOT).as_posix(),layout_receipt_sha256=digest(target))
    path.write_bytes(canonical(summary)+b'\n')
    print(json.dumps(dict(status=record['status'],source_directories=len(layout),
        created={role:len(rows) for role,rows in created.items()},files_overwritten=False,game_started=False)),flush=True)
    return record


def run():
    dll=api()
    assert not pids(dll,'PBZSteamLab'),'Current research Steam must be closed before copying'
    for role,box in BOXES.items():
        verify_policy(dll,role,False);assert not pids(dll,box)
        assert not virtual(role,LOGICAL).exists(),'Preserve an existing role client; do not overwrite'
    before=formal_files()
    directory=ROOT/'runtime/online-client-snapshots'/uuid.uuid4().hex;directory.mkdir(parents=True)
    path=directory/'clients.json'
    record=dict(schema=1,status='copying',source=str(SOURCE),roles={},
        steam_started=False,game_started=False,game_loader_installed=False,
        complete_mod=False,runtime_acceptance_current=False,
        source_sha256={name:sha((ROOT/name).read_bytes()) for name in ('tools/prepare_phantom_boss_clients.py',)})
    def save():
        pending=path.with_suffix('.pending');pending.write_bytes(canonical(record)+b'\n');pending.replace(path)
    save()
    try:
        print('Hashing current research client; account/config contents stay local and are not printed',flush=True)
        files=inventory(SOURCE);directories=directory_layout(SOURCE)
        record.update(files=files,source_tree_sha256=sha(canonical(files)),bytes=sum(row['bytes'] for row in files.values()))
        save()
        for role in BOXES:
            target=virtual(role,LOGICAL)
            record['roles'][role]=dict(target=str(target),copied=0,verified=False);save()
            target.mkdir(parents=True,exist_ok=False)
            for name in directories:(target/name).mkdir()
            for index,(name,row) in enumerate(files.items(),1):
                origin=SOURCE/name;destination=target/name;destination.parent.mkdir(parents=True,exist_ok=True)
                with origin.open('rb') as src,destination.open('xb') as dst:shutil.copyfileobj(src,dst)
                shutil.copystat(origin,destination)
                assert digest(destination)==row['sha256'] and destination.stat().st_size==row['bytes'],'Independent copy mismatch'
                if index%1000==0:print(role+': '+str(index)+'/'+str(len(files))+' files verified',flush=True)
            record['roles'][role].update(copied=len(files),verified=True);save()
        assert inventory(SOURCE)==files,'Research client changed during independent copying'
        assert formal_files()==before,'Formal files changed while preparing clients'
        assert not pids(dll,'PBZSteamLab') and all(not pids(dll,box) for box in BOXES.values())
        record.update(status='copied-not-started',formal_files_unchanged=True,
            cloud_setting_source='Exact copy of the existing research client configuration; no flags edited',
            cloud_ui_verified_for_new_instances=False,official_user_validated_for_new_instances=False)
        save()
        summary=dict(schema=1,status=record['status'],passed=True,roles=list(BOXES),
            files_per_client=len(files),bytes_per_client=record['bytes'],
            receipt=path.relative_to(ROOT).as_posix(),receipt_sha256=digest(path),
            source_sha256=record['source_sha256'],formal_files_unchanged=True,
            steam_started=False,game_started=False,game_loader_installed=False,
            cloud_ui_verified_for_new_instances=False,official_user_validated_for_new_instances=False,
            complete_mod=False,runtime_acceptance_current=False)
        (ROOT/'evidence/adaptation/phantom-pact-client-snapshots.json').write_bytes(canonical(summary)+b'\n')
        print(json.dumps(summary,ensure_ascii=False),flush=True)
        return summary
    except Exception as error:
        record.update(status='failed-preserve-partial',error=type(error).__name__);save();raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--complete-layout',action='store_true');args=parser.parse_args()
    if args.complete_layout:complete_layout()
    else:run()
