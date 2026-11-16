"""Re-read the two-container isolation receipt, policies, logs and binary identities."""
import argparse
import json
from pathlib import Path

from build_phantom_boss_candidate import ROOT, canonical, sha
from check_phantom_boss_isolation import BOXES, api, pids, sections, settings, verify_policy
from check_phantom_boss_native import verify_build


def verify(path):
    path=Path(path).resolve()
    assert path.is_relative_to(ROOT/'runtime/online-isolation') and path.name=='isolation.json'
    report=json.loads(path.read_bytes())
    assert report['schema']==1 and report['status']=='sentinel-and-relay-proven-only' and report['passed'] is True
    assert report['boxes']==BOXES
    for key in ('complete_mod','runtime_acceptance_current','game_started','installed','lease_issued',
                'game_saved_redirection_live_accepted'):
        assert report[key] is False
    for key in ('existing_box_settings_unchanged','formal_files_unchanged','independent_saved_paths_proven',
                'standalone_relay_executed'):
        assert report[key] is True
    for name,digest in report['source_sha256'].items():
        assert sha((ROOT/name).read_bytes())==digest, 'Isolation tool source drift'
    native_build=ROOT/report['native_build']
    native=verify_build(native_build)
    assert sha((native_build/'native-build.json').read_bytes())==report['native_build_manifest_sha256']
    assert native['files']==report['native_files']
    assert sha((path.parent/'isolation_probe.exe').read_bytes())==report['probe_sha256']
    assert len(report['checks'])==5 and report['relay_launch_exit_codes']==[0,0]
    dll=api()
    current=sections()
    for name,digest in report['existing_section_sha256'].items():
        assert sha(canonical(current[name]))==digest, 'Pre-existing container settings drifted'
    for role,box in BOXES.items():
        verify_policy(dll,role,False)
        assert not pids(dll,box) and not report['remaining_box_pids'][box], 'Probe process remains'
        assert report['policies'][role]==settings(role)
    for check in report['checks']:
        assert check['passed'] is True
        file=Path(check.get('report') or ROOT/check['output'])
        assert sha(file.read_bytes())==check.get('report_sha256',check.get('output_sha256'))
        if 'report' in check:
            assert json.loads(file.read_bytes())==dict(sandbox_verified=True,local_saved=True,installed_saved=True)
        else:
            assert file.read_bytes().count(b'connected=1 sample=1 event=1 reset=1')==2
    return dict(report,receipt=path.relative_to(ROOT).as_posix(),receipt_sha256=sha(path.read_bytes()),
                verifier_sha256=sha(Path(__file__).read_bytes()))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('receipt',type=Path)
    parser.add_argument('--record',action='store_true')
    args=parser.parse_args()
    result=verify(args.receipt)
    if args.record:
        (ROOT/'evidence/adaptation/phantom-pact-isolation.json').write_bytes(canonical(result)+b'\n')
    print(json.dumps(dict(passed=True,checks=5,game_started=False,saved_paths=result['saved_paths_verified']),ensure_ascii=False))
