"""Read-only evidence for an idle focus roundtrip; no input injection or held-key claim."""
import argparse
import contextlib
import ctypes
from ctypes import wintypes
import io
import json
import math
from pathlib import Path
import time

import ahua_practice as practice
from boss_adaptation_workflow import ROOT,sha,write_json
from control_action_evidence import control_identity,restoration_result
from inspect_owned_participants import collect as participant_sample
import player_experience_workflow as workflow
from four_boss_integration_workflow import modules
import build_player_experience_candidate as candidate

TAGS=('before','background_first','background_last','returned')


def analyze(samples,raw):
    assert [s['tag']for s in samples]==list(TAGS)
    assert len({s['state_file']for s in samples})==len({s['candidate_manifest_sha256']for s in samples})==1
    assert [s['foreground_game']for s in samples]==[True,False,False,True]
    assert all(b['at']>a['at']and b['log_offset']>=a['log_offset']for a,b in zip(samples,samples[1:]))
    assert samples[2]['at']-samples[1]['at']>=2,'At least two seconds of observed background state required'
    baseline=samples[0]['participants'];changes=[]
    for sample in samples[1:]:
        rows=sample['participants'];assert len(rows)==len(baseline)==4
        for before,after in zip(baseline,rows):
            assert (before['path'],before['address'],before['health'])==(after['path'],after['address'],after['health'])
            delta=math.dist(before['position'],after['position']);assert math.isfinite(delta)
            changes.append(delta)
    tail=raw[samples[-1]['log_offset']:]
    result=dict(idle_background_max_displacement_cm=max(changes,default=0),same_participants_and_health=True,
        foreground_sequence=[s['foreground_game']for s in samples],background_seconds=samples[2]['at']-samples[1]['at'],
        restoration=restoration_result(tail,'exit'),held_key_release_tested=False)
    result['passed']=result['idle_background_max_displacement_cm']<=1 and result['restoration']['passed']
    return result


def sample(flow,tag):
    assert tag in TAGS;frozen=workflow.verify(flow);package=Path(frozen['candidate']);manifest=candidate.verify(package)
    owner,state=practice.owned_session();work=Path(state['work']);path=practice.log_path(state)
    assert owner['phase']=='armed'and owner['player_entry']and state['control_probe_expires_at']-time.time()>35
    assert practice.read(work/'control-lifecycle-deployment.json')['module_source_sha256']==modules(manifest)
    raw=path.read_text(encoding='utf-8',errors='replace');last=raw.rfind('[PBZBossControl] enter success=true state=ACTIVE')
    assert last>=0 and not restoration_result(raw[last:])['passed']and control_identity(raw[last:])
    assert not any(t in raw[last:]for t in ('state=FAULTED','PBZ_CONTROL_RESTORE:FAILED=','KEY_SKILL_BEGIN='))
    output=work/('player-focus-'+tag+'.json');assert not output.exists(),'Preserve every observed sample'
    before=set(work.glob('owned-participants-*.json'))
    with contextlib.redirect_stdout(io.StringIO()):participant_sample()
    added=set(work.glob('owned-participants-*.json'))-before;assert len(added)==1
    snapshot_path=added.pop();snapshot=practice.read(snapshot_path)
    user=ctypes.WinDLL('user32');user.GetForegroundWindow.restype=wintypes.HWND
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    pid=wintypes.DWORD();user.GetWindowThreadProcessId(user.GetForegroundWindow(),ctypes.byref(pid))
    front=pid.value==snapshot['pid'];assert front is (tag in ('before','returned'))
    result=dict(schema=1,tag=tag,at=time.time(),state_file=state['state_file'],candidate_manifest_sha256=sha(package/'pbz-release.json'),
        workflow=str(flow),foreground_game=front,game_pid=snapshot['pid'],participants=snapshot['rows'],
        participant_file=snapshot_path.relative_to(ROOT).as_posix(),participant_sha256=sha(snapshot_path),log_offset=len(raw))
    write_json(output,result);print(json.dumps(dict(tag=tag,foreground_game=front,sample=str(output)),ensure_ascii=False))


def collect(session,flow):
    import re
    assert re.fullmatch(r'\d{8}-\d{6}',session)
    frozen=workflow.verify(flow);package=Path(frozen['candidate']);work=ROOT/'evidence/official-validation'/session
    state_path=ROOT/'runtime'/('official-validation-'+session)/'state.json';state=practice.read(state_path);post=practice.read(work/'postcheck.json')
    assert state['restored']and Path(state['work'])==work and post['validation_state']==str(state_path)
    assert all(post[k]is True for k in ('research_box_empty','research_loader_removed','host_registry_unchanged'))
    assert not post['formal_files_changed']and not post['host_config_files_changed']
    paths=[work/('player-focus-'+tag+'.json')for tag in TAGS];samples=[practice.read(p)for p in paths]
    for sample in samples:
        assert sample['state_file']==str(state_path)and sample['workflow']==str(flow)
        assert sample['candidate_manifest_sha256']==sha(package/'pbz-release.json')
        path=(ROOT/sample['participant_file']).resolve();assert path.parent==work
        assert sha(path)==sample['participant_sha256']and practice.read(path)['rows']==sample['participants']
        paths.append(path)if path not in paths else None
    raw_path=work/'UE4SS.log';raw=raw_path.read_text(encoding='utf-8',errors='replace')
    result=analyze(samples,raw)
    result.update(session=session,candidate=str(package),candidate_manifest_sha256=sha(package/'pbz-release.json'),
        sources={p.relative_to(ROOT).as_posix():sha(p)for p in [*paths,raw_path,state_path,work/'postcheck.json',ROOT/'tools/player_experience_focus.py']})
    target=work/'player-experience-focus-acceptance.json'
    if target.exists():assert practice.read(target)==result
    else:write_json(target,result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=(*TAGS,'collect'));p.add_argument('workflow',type=Path);p.add_argument('--session')
    a=p.parse_args();flow=a.workflow.resolve()
    if a.action=='collect':print(json.dumps(collect(a.session,flow),ensure_ascii=False))
    else:sample(flow,a.action)
