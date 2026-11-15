"""集中验证玩家工作台双向切换；仅使用现有受保护输入入口，不启动游戏。"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import ahua_practice as practice
import research_game_menu as menu
from control_action_evidence import restoration_result
from test_player_skill_batch import wait_for
from collect_multi_boss_switching import movement_camera_proof


def main():
    parser=argparse.ArgumentParser();resume=parser.add_mutually_exclusive_group()
    resume.add_argument('--resume-camera',action='store_true')
    resume.add_argument('--resume-entry',action='store_true')
    resume.add_argument('--complete-ahua',action='store_true')
    args=parser.parse_args()
    owner,state=practice.owned_session()
    assert owner['phase']=='armed' and owner.get('player_entry') and owner.get('workbench')
    work=Path(state['work']);path=practice.log_path(state)
    assert practice.read(work/'control-lifecycle-deployment.json')['boss_id']=='ahua_guitoudao'
    assert state['deadline_unix']-time.time()>300
    start=len(path.read_text(encoding='utf-8',errors='replace'))
    target=work/'multi-boss-switching-actions.json'
    if args.complete_ahua:
        previous=json.loads(target.read_text(encoding='utf-8'))
        assert previous['passed'] is False and previous['error']=='skill_01: Entry not verified\n'
        assert previous['checks']==['open_active_workbench_restores_ahua','ahua_to_wanjun_owned_cleanup',
            'wanjun_ordinary_bindings_natural_cancel_restored','wanjun_to_ahua_owned_cleanup']
        assert not previous.get('completion_resumed_from') and previous['state_file']==state['state_file']
        raw=path.read_text(encoding='utf-8',errors='replace')
        assert previous['lines']==raw[previous['log_offset']:previous['log_end']].splitlines()
        pending=raw[previous['log_offset']:].rsplit('PLAYER_ENTRY_READY=ahua_guitoudao',1)
        assert len(pending)==2 and 'stop moving before entering boss control; velocity=' in pending[1]
        assert not any(k in pending[1] for k in ('KEY_SKILL_BEGIN=','enter success=true','PLAYER_ENTRY_READY=',
            'WORKBENCH_BOSS_SELECTED=','state=FAULTED','PBZ_CONTROL_RESTORE:FAILED='))
        failed=work/'multi-boss-switching-ahua-settling-attempt.json';assert not failed.exists()
        failed.write_bytes(target.read_bytes())
        report=dict(previous,completion_resumed_from=failed.name,
            completion_resumed_from_sha256=hashlib.sha256(failed.read_bytes()).hexdigest(),completion_resume_log_offset=start)
        report.pop('error',None);start=report['log_offset']
    elif args.resume_camera or args.resume_entry:
        previous=json.loads(target.read_text(encoding='utf-8'))
        expected_error=('ordinary WanJun actual movement/camera change not verified' if args.resume_camera
                        else 'skill_01: Entry not verified\n')
        expected_checks=['open_active_workbench_restores_ahua','ahua_to_wanjun_owned_cleanup']
        if args.resume_camera:expected_checks.append('wanjun_ordinary_bindings_natural_cancel_restored')
        assert previous.get('passed') is False and previous.get('error')==expected_error
        assert previous['checks']==expected_checks and not previous.get('resumed_from')
        assert previous['state_file']==state['state_file']
        raw=path.read_text(encoding='utf-8',errors='replace')
        assert previous['lines']==raw[previous['log_offset']:previous['log_end']].splitlines()
        assert 'PLAYER_ENTRY_READY=057_wanjun' in raw[previous['log_offset']:]
        assert 'PLAYER_ENTRY_READY=ahua_guitoudao' not in raw[previous['log_offset']:]
        assert not any(k in raw[previous['log_offset']:] for k in ('state=FAULTED','PBZ_CONTROL_RESTORE:FAILED='))
        if args.resume_entry:
            pending=raw[previous['log_offset']:].rsplit('PLAYER_ENTRY_READY=057_wanjun',1)[-1]
            assert 'stop moving before entering boss control; velocity=' in pending
            assert 'KEY_SKILL_BEGIN=' not in pending and 'enter success=true' not in pending
        failed=work/('multi-boss-switching-camera-first-attempt.json' if args.resume_camera
                     else 'multi-boss-switching-entry-first-attempt.json');assert not failed.exists()
        failed.write_bytes(target.read_bytes())
        report=dict(previous,passed=False,resumed_from=failed.name,
            resumed_from_sha256=hashlib.sha256(failed.read_bytes()).hexdigest(),resume_log_offset=start)
        report.pop('error',None);start=report['log_offset']
    else:
        assert not target.exists(),'preserve the existing integration attempt'
        report={'state_file':state['state_file'],'log_offset':start,'checks':[],'passed':False}
    def save():
        raw=path.read_text(encoding='utf-8',errors='replace')
        report.update(log_end=len(raw),lines=raw[start:].splitlines())
        target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def send(action,token):
        offset=len(path.read_text(encoding='utf-8',errors='replace'))
        menu.click(0,0,2560,1600,action)
        tail=wait_for(path,offset,lambda t:token in t,85 if action=='control_workbench_confirm' else 10,True)
        assert token in tail,'Missing '+token
        return offset,tail
    def skills(*names,interrupt=False):
        result=subprocess.run([sys.executable,str(practice.ROOT/'tools/test_player_skill_batch.py'),
            *names,*(['--interrupt']if interrupt else [])],cwd=practice.ROOT,timeout=250,
            capture_output=True,text=True,encoding='utf-8',errors='replace',creationflags=subprocess.CREATE_NO_WINDOW)
        print(result.stdout,flush=True)
        assert result.returncode==0,result.stderr or result.stdout
    try:
        save()
        if args.complete_ahua:
            skills('skill_01')
            skills('skill_08',interrupt=True)
            report['checks'].append('ahua_controls_restored_after_roundtrip')
            raw=path.read_text(encoding='utf-8',errors='replace')[start:]
            assert not any(x in raw for x in ('state=FAULTED','PBZ_CONTROL_LIFECYCLE:ISSUE_',
                'HUD_UNAVAILABLE=','PBZ_CONTROL_RESTORE:FAILED='))
            report['passed']=True
            return 0
        expected=('boss','boss_controller','target','target_controller','extra_target','extra_target_controller')
        if args.resume_camera:
            send('control_workbench_toggle','WORKBENCH_INPUT_RESTORED=true')
        elif not args.resume_entry:
            send('control_enter','[PBZBossControl] enter success=true state=ACTIVE')
            offset,tail=send('control_workbench_toggle','WORKBENCH_INPUT_LOCKED=')
            tail=wait_for(path,offset,lambda t:restoration_result(t,'auto_exit')['passed'],10)
            assert restoration_result(tail,'auto_exit')['passed']
            report['checks'].append('open_active_workbench_restores_ahua');save()
            send('control_workbench_down','workbench_down success=true')
            offset,tail=send('control_workbench_confirm','PLAYER_ENTRY_READY=057_wanjun')
            assert 'WORKBENCH_BOSS_SELECTED=057_wanjun'in tail
            assert all('OWNED_DESTROY_VERIFIED='+name+'|engine_unusable=true'in tail for name in expected)
            report['checks'].append('ahua_to_wanjun_owned_cleanup');save()
        if not args.resume_camera:
            time.sleep(2)  # 切换装配后先等待站位收敛；保留F6真实静止检查。
            skills('skill_01','heavy_01','skill_02','dash')
            skills('skill_01','heavy_01','skill_02','dash',interrupt=True)
            report['checks'].append('wanjun_ordinary_bindings_natural_cancel_restored');save()
        movement_start,_=send('control_enter','[PBZBossControl] enter success=true state=ACTIVE')
        baseline=wait_for(path,movement_start,lambda t:'CAMERA_ARM_YAW='in t,5)
        assert 'CAMERA_ARM_YAW='in baseline,'initial ordinary WanJun camera readback required'
        menu.click(0,0,2560,1600,'control_forward')
        menu.click(0,0,2560,1600,'control_look')
        after_input=len(path.read_text(encoding='utf-8',errors='replace'))
        turned=wait_for(path,after_input,lambda t:'CAMERA_ARM_YAW='in t,9)
        assert 'CAMERA_ARM_YAW='in turned,'new camera sample after completed mouse input required'
        report['camera_after_input_offset']=after_input
        offset,tail=send('control_workbench_toggle','WORKBENCH_INPUT_LOCKED=')
        tail=wait_for(path,offset,lambda t:restoration_result(t,'auto_exit')['passed'],10)
        assert restoration_result(tail,'auto_exit')['passed']
        movement=movement_camera_proof(path.read_text(encoding='utf-8',errors='replace')[movement_start:])
        assert movement['passed'],'ordinary WanJun actual movement/camera change not verified'
        report['wanjun_movement_camera']=movement;save()
        send('control_workbench_up','workbench_up success=true')
        offset,tail=send('control_workbench_confirm','PLAYER_ENTRY_READY=ahua_guitoudao')
        assert 'WORKBENCH_BOSS_SELECTED=ahua_guitoudao'in tail
        assert all('OWNED_DESTROY_VERIFIED='+name+'|engine_unusable=true'in tail for name in expected)
        report['checks'].append('wanjun_to_ahua_owned_cleanup');save()
        time.sleep(2)  # 等待装配后的站位收敛；F6仍须通过真实静止检查。
        skills('skill_01')
        skills('skill_08',interrupt=True)
        report['checks'].append('ahua_controls_restored_after_roundtrip')
        raw=path.read_text(encoding='utf-8',errors='replace')[start:]
        assert not any(x in raw for x in ('state=FAULTED','PBZ_CONTROL_LIFECYCLE:ISSUE_',
            'HUD_UNAVAILABLE=','PBZ_CONTROL_RESTORE:FAILED='))
        report['passed']=True
    except Exception as error:
        report['error']=str(error)
    finally:
        save();print(json.dumps({k:v for k,v in report.items()if k!='lines'},ensure_ascii=False),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
