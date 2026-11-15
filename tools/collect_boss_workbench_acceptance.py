"""Freeze closed-session workbench results, including exactly-once timer behavior."""
import argparse
import json
from pathlib import Path
import re
from boss_adaptation_workflow import ROOT,sha,write_json
from control_action_evidence import restoration_result


def proof(segment,preview_steps=1):
    assert type(preview_steps)is int and 1<=preview_steps<=128
    labels=re.findall(r'\[PBZBossControl\] (\w+) success=(true|false) state=(\w+)',segment)
    def count(name,success='true'):return labels.count((name,success,'OFF'))
    expected={'workbench_toggle':5,'workbench_down':preview_steps,'workbench_up':preview_steps,
              'workbench_confirm':1,'workbench_close':1,'exit':2,'auto_exit':1}
    counts={name:count(name) for name in expected}
    entries=labels.count(('enter','true','ACTIVE'))
    first_enter=segment.find('[PBZBossControl] enter success=true state=ACTIVE')
    final_enter=segment.rfind('[PBZBossControl] enter success=true state=ACTIVE')
    locks=segment.count('WORKBENCH_INPUT_LOCKED=')
    unlocks=segment.count('WORKBENCH_INPUT_RESTORED=true')
    result={'action_counts':counts,'expected_counts':expected,'successful_entries':entries,
            'locks':locks,'unlocks':unlocks,'preview_confirm_rejections':count('workbench_confirm','false'),
            'open_restoration':restoration_result(segment[first_enter:final_enter],'auto_exit'),
            'final_restoration':restoration_result(segment[final_enter:],'exit')}
    result['passed']=bool(counts==expected and entries==2 and locks==unlocks==4
        and result['preview_confirm_rejections']==1
        and result['open_restoration']['passed'] and result['final_restoration']['passed']
        and 'KEY_SKILL_BEGIN=' not in segment and 'WORKBENCH_BOSS_SELECTED=' not in segment
        and not any(token in segment for token in ('state=FAULTED','PBZ_CONTROL_LIFECYCLE:ISSUE_',
            'pause menu opened','HUD_UNAVAILABLE=')))
    return result


def collect(session):
    assert re.fullmatch(r'\d{8}-\d{6}',session)
    state_path=ROOT/'runtime'/('official-validation-'+session)/'state.json'
    state=json.loads(state_path.read_text(encoding='utf-8'));work=Path(state['work'])
    assert state.get('restored') and work.name==session
    post_path=work/'postcheck.json';post=json.loads(post_path.read_text(encoding='utf-8'))
    assert post['validation_state']==str(state_path)
    assert post['research_box_empty'] and post['research_loader_removed'] and post['host_registry_unchanged']
    assert not post['formal_files_changed'] and not post['host_config_files_changed']
    actions_path=work/'boss-workbench-runtime-actions.json'
    actions=json.loads(actions_path.read_text(encoding='utf-8'));assert actions['passed']
    raw_path=work/'UE4SS.log';raw=raw_path.read_text(encoding='utf-8',errors='replace')
    start,end=actions['log_offset'],actions['log_end'];assert 0<=start<end<=len(raw)
    segment=raw[start:end];assert all(line in segment for line in actions['lines'])
    deployments=[json.loads(p.read_text(encoding='utf-8')) for p in work.glob('control-lifecycle-deployment-*.json')]
    # The first assembly is the ordinary player workbench; a later independent Boss trial is separate.
    deployment=min((d for d in deployments if d.get('player_entry')),key=lambda d:d['at'])
    assert deployment['workbench'] and deployment['boss_id']=='ahua_guitoudao'
    result=proof(segment,actions.get('preview_steps',1))
    result.update(session=session,module_source_sha256=deployment['module_source_sha256'],
        checks=actions['checks'],multi_boss_switching_verified=False,
        scope='Workbench interaction, input isolation and cleanup; no second Boss promotion',
        sources={str(p.relative_to(ROOT)):sha(p) for p in (state_path,post_path,actions_path,raw_path)})
    target=work/'boss-workbench-acceptance.json';write_json(target,result)
    print(json.dumps({'report':str(target),'passed':result['passed']},ensure_ascii=False))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('session')
    raise SystemExit(0 if collect(parser.parse_args().session)['passed'] else 1)
