"""One bounded four-role experience roundtrip on an already armed candidate."""
import argparse
from pathlib import Path
import re
import time

import ahua_practice as practice
import official_validation as v
import player_experience_workflow as workflow
from test_player_experience_inputs import main as dispatch
from control_action_evidence import restoration_result
from test_player_skill_batch import wait_for
from boss_adaptation_workflow import sha

IDS=('ahua_guitoudao','057_wanjun','073_yanqiansui','056_youlong')


def run(flow,resume=False):
    workflow.verify(flow);owner,state=practice.owned_session()
    assert min(state['deadline_unix'],state['control_probe_expires_at'])-time.time()>200
    path=practice.log_path(state);previous=Path(state['work'])/'experience-role-roundtrip.json'
    target=Path(state['work'])/('experience-role-continuation.json'if resume else'experience-role-roundtrip.json')
    assert not target.exists(), 'Preserve every roundtrip attempt'
    def raw():return path.read_text(encoding='utf-8',errors='replace')
    current=re.findall(r'PLAYER_ENTRY_READY=([^\r\n]+)',raw())[-1]
    assert current==IDS[1], 'First manual switch to WanJun required'
    report=dict(state_file=state['state_file'],workflow=str(flow),log_offset=len(raw()),
        roles=[],passed=False,runtime_acceptance_current=False)
    if resume:
        old=practice.read(previous);text=raw()
        assert old['error']=='AssertionError: Complete native restoration required'
        assert old['lines']==text[old['log_offset']:old['log_end']].splitlines()
        assert len(old['roles'])==1 and old['roles'][0]['boss']==IDS[1]
        assert restoration_result(text[old['log_offset']:],'exit')['passed']
        assert re.search(r'KEY_SKILL_END=skill_01\|[^\r\n]+\|natural=true\|',text[old['log_offset']:])
        report.update(previous_attempt_sha256=sha(previous),previous_attempt=str(previous),
            continuation_reason='The first runner inspected restoration before its delayed readback; reanalyzed raw proof, no repeated WanJun cast.')
    def save():
        text=raw();report.update(log_end=len(text),lines=text[report['log_offset']:].splitlines());v.save(target,report)
    def send(action):
        offset=len(raw());dispatch(flow,action);return offset
    def wait(offset,tokens,timeout=15):return practice.wait_tokens(path,tokens,timeout=timeout,offset=offset)
    try:
        save()
        for identifier in IDS[1:]:
            row=dict(boss=identifier,log_offset=len(raw()),passed=False);report['roles'].append(row);save()
            assert re.findall(r'PLAYER_ENTRY_READY=([^\r\n]+)',raw())[-1]==identifier
            if resume and identifier==IDS[1]:
                row['inherited_trial_offset']=old['log_offset']
                row['restoration']=restoration_result(raw()[old['log_offset']:],'exit')
            else:
                offset=send('enter');wait(offset,['enter success=true state=ACTIVE','TARGET_CAMERA_LOCK=true|initial'])
                offset=send('shift_cast')
                tail=wait(offset,['KEY_SKILL_BEGIN=skill_01|','KEY_SKILL_END=skill_01|'],timeout=45)
                assert '[PBZBossControl] slot1 success=true state=ACTIVE' in tail
                assert re.search(r'KEY_SKILL_BEGIN=skill_01\|[^\r\n]+\|active=[1-9]\d*',tail)
                assert re.search(r'KEY_SKILL_END=skill_01\|[^\r\n]+\|natural=true\|',tail)
                offset=send('exit')
                restored=wait_for(path,offset,lambda t:restoration_result(t,'exit')['passed'],8)
                assert restoration_result(restored,'exit')['passed'], 'Complete native restoration required'
            row.update(log_end=len(raw()),passed=True);save()
            offset=send('workbench');wait(offset,['WORKBENCH_INPUT_LOCKED='])
            wanted=IDS[(IDS.index(identifier)+1)%len(IDS)]
            action='up'if wanted==IDS[0]else'down'
            for _ in range(3 if wanted==IDS[0]else 1):
                offset=send(action);wait(offset,['workbench_'+action+' success=true'])
            offset=send('confirm');wait(offset,['WORKBENCH_BOSS_SELECTED='+wanted,
                'PLAYER_ENTRY_READY='+wanted,'WORKBENCH_INPUT_RESTORED=true'],timeout=60)
        report['returned_to_ahua']=True;report['passed']=True
    except Exception as error:
        report['error']=type(error).__name__+': '+str(error)
        text=raw()[report['log_offset']:]
        last=text.rfind('[PBZBossControl] enter success=true state=ACTIVE')
        if last>=0 and not restoration_result(text[last:])['passed']:
            try:send('exit')
            except Exception as cleanup:report['cleanup_error']=str(cleanup)
        raise
    finally:save();print('roundtrip_record='+str(target),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('workflow',type=Path)
    parser.add_argument('--resume',action='store_true')
    args=parser.parse_args();run(args.workflow.resolve(),args.resume)
