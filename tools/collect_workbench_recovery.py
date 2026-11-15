"""从已关闭会话核对死亡目标残留清理与完整恢复，不发送输入。"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re
from control_action_evidence import restoration_result
from mod_installation import ROOT,digest


def proof(text):
    starts=list(re.finditer(r'\[PBZBossControl\] enter success=true state=ACTIVE',text))
    accepted=[]
    for index,start in enumerate(starts):
        end=starts[index+1].start() if index+1<len(starts) else len(text)
        interval=text[start.start():end]
        clears=list(re.finditer(r'PBZ_COMBAT_TARGET:CLEAR_VERIFIED=true\|fallback=(true|false)(?:\r?\n|$)',interval))
        clear=next((row for row in reversed(clears)
            if restoration_result(interval[row.end():],'exit')['passed']),None)
        if not clear:continue
        cleared=clear.start()
        statuses=[];cursor=0
        for line in interval[:cleared].splitlines(keepends=True):
            line_start=cursor;cursor+=len(line)
            if 'PBZ_PLAYER_UI:STATUS='not in line:continue
            try:statuses.append((json.loads(line.split('PBZ_PLAYER_UI:STATUS=',1)[1])['text'],line_start))
            except (ValueError,KeyError,TypeError):continue
        dead_rows=[i for i,(text,_)in enumerate(statuses)if ' | ACTIVE\n'in text and re.search(
            r'目标：[^\n]+ \| 生命 0(?:\.0+)?(?:\n|$)',text)]
        dead=False;lost_lock=False
        if dead_rows:
            last=dead_rows[-1];after=interval[statuses[last][1]:cleared]
            lost_lock=bool(last<len(statuses)-1
                and all(' | ACTIVE\n'in text and '目标：无有效锁定\n'in text for text,_ in statuses[last+1:])
                and '[PBZBossControl] target_request success=false state=ACTIVE reason=no visible living hostile target within radius'in after
                and 'KEY_SKILL_BEGIN='not in after)
            dead=last==len(statuses)-1 or lost_lock
        restoration=restoration_result(interval[cleared:],'exit')
        if dead and restoration['passed'] and not any(token in interval for token in (
                'state=FAULTED','PBZ_CONTROL_RESTORE:FAILED=','HUD_UNAVAILABLE=')):
            accepted.append({'log_offset':start.start(),'log_end':end,'restoration':restoration,
                'fallback_used':clear[1]=='true',
                'dead_status_followed_by_rejected_target_cycle':lost_lock})
    return {'passed':bool(accepted),'dead_target_clear_restorations':accepted,
            'requires_real_dead_target_status':True,'requires_native_clear_readback_and_full_restoration':True}


def collect(session):
    assert re.fullmatch(r'\d{8}-\d{6}',session)
    state_path=ROOT/'runtime'/('official-validation-'+session)/'state.json'
    state=json.loads(state_path.read_text(encoding='utf-8'));work=Path(state['work'])
    assert state.get('restored') and work.name==session
    post_path=work/'postcheck.json';post=json.loads(post_path.read_text(encoding='utf-8'))
    assert post['validation_state']==str(state_path) and post['research_box_empty'] and post['research_loader_removed']
    assert post['host_registry_unchanged'] and not post['formal_files_changed'] and not post['host_config_files_changed']
    deployments=list(work.glob('control-lifecycle-deployment-*.json'));assert len(deployments)==1
    deployment_path=deployments[0];deployment=json.loads(deployment_path.read_text(encoding='utf-8'))
    assert deployment['player_entry']
    log_path=work/'UE4SS.log';result=proof(log_path.read_text(encoding='utf-8',errors='replace'))
    result.update(at=datetime.now().astimezone().isoformat(),session=session,
        module_source_sha256=deployment['module_source_sha256'],
        sources={p.relative_to(ROOT).as_posix():digest(p) for p in (state_path,post_path,deployment_path,log_path)},
        scope='dead training target lock cleanup; original player, camera, input and faction strictly restored')
    target=work/'workbench-recovery-acceptance.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'report':str(target),'passed':result['passed']},ensure_ascii=False))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('session')
    raise SystemExit(0 if collect(parser.parse_args().session)['passed'] else 1)
