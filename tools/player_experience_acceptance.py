"""Combine replayed feature, World and focus evidence for one exact payload."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from boss_adaptation_workflow import ROOT,sha,write_json
from collect_player_experience import collect as features
from player_experience_world import collect as world
from player_experience_focus import collect as focus
import player_experience_workflow as workflow

SOURCES=('tools/player_experience_acceptance.py','tools/collect_player_experience.py',
    'tools/player_experience_world.py','tools/player_experience_focus.py',
    'tests/test_collect_player_experience.py','tests/test_player_experience_lifecycle.py')


def collect(feature_session,world_session,flow,offline):
    frozen=workflow.verify(flow);package=Path(frozen['candidate'])
    path,feature=features(feature_session,flow);world_result=world(world_session,flow);focus_result=focus(world_session,flow)
    assert feature['feature_trial_passed']and world_result['passed']and focus_result['passed']
    assert {r['candidate_manifest_sha256']for r in (feature,world_result,focus_result)}=={sha(package/'pbz-release.json')}
    check=json.loads(offline.read_bytes());assert check['passed']and all(row['passed']for row in check['checks'])
    assert check['candidate_manifest_sha256']==sha(package/'pbz-release.json')and check['workflow']==str(flow)
    assert all(sha(ROOT/name)==digest for name,digest in check['source_files'].items())
    performance=[]
    raw=ROOT/'evidence/official-validation'/world_session/'UE4SS.log'
    for match in re.finditer(r'PBZ_PERF:WINDOW=state=ACTIVE\|wall=([\d.]+)\|frames=(\d+)\|callback_ms=([\d.]+)\|max_ms=([\d.]+)',
                           raw.read_text(encoding='utf-8',errors='replace')):
        performance.append(dict(wall_seconds=float(match[1]),frames=int(match[2]),callback_ms=float(match[3]),max_ms=float(match[4])))
    assert performance
    frames=sum(r['frames']for r in performance)
    receipts=[path,ROOT/'evidence/official-validation'/world_session/'player-experience-world-acceptance.json',
        ROOT/'evidence/official-validation'/world_session/'player-experience-focus-acceptance.json',offline]
    report=dict(schema=1,passed=True,experience_runtime_verified=True,candidate=str(package),
        candidate_manifest_sha256=sha(package/'pbz-release.json'),workflow=str(flow),
        feature_session=feature_session,world_session=world_session,feature_checks=feature['feature_checks'],
        world_reload_verified=True,focus_idle_roundtrip_verified=True,held_key_focus_release_verified=False,
        loop_measurements=dict(active_windows=len(performance),frames=frames,
            weighted_mean_callback_ms=sum(r['callback_ms']*r['frames']for r in performance)/frames,
            max_callback_ms=max(r['max_ms']for r in performance),is_gpu_fps=False),
        receipts={p.relative_to(ROOT).as_posix():sha(p)for p in receipts},
        sources={name:sha(ROOT/name)for name in SOURCES},
        new_playable_bosses=0,installed=False,complete_mod=False,
        remaining_scope='Additional Boss native grants, effects, cancellation and ordinary selection acceptance')
    key=hashlib.sha256(json.dumps(report,sort_keys=True).encode()).hexdigest()[:16]
    target=ROOT/'evidence/releases'/('player-experience-accepted-'+key+'.json')
    if target.exists():assert json.loads(target.read_bytes())==report
    else:write_json(target,report)
    return target,report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('feature_session');p.add_argument('world_session')
    p.add_argument('workflow',type=Path);p.add_argument('offline',type=Path);a=p.parse_args()
    target,report=collect(a.feature_session,a.world_session,a.workflow.resolve(),a.offline.resolve())
    print(json.dumps(dict(report=str(target),passed=report['passed'],loop=report['loop_measurements'],complete_mod=False),ensure_ascii=False))
