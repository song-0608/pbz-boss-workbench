"""普通玩家入口逐项核对实际键位、自然结束或活动取消；不授予、不绕过冷却。"""
import argparse
import json
from pathlib import Path
import re
import sys
import time
import ahua_practice as practice
import research_game_menu as menu
from control_action_evidence import restoration_result
from collect_skill_acceptance import analyze,subtree_evidence,registered_subtree_class
from player_target_readiness import ensure_visible_target,deployed_boss_name
from player_keymap import ability_for_slot


def resolve_binding(bindings,requested):
    rows=[row for row in bindings if row.get('skill')==requested or row.get('slot')==requested]
    if requested=='skill_01':rows=[row for row in rows if row['slot']=='slot1']
    if len(rows)!=1 or rows[0]['skill']!=ability_for_slot(rows[0]['slot']):
        raise RuntimeError('Exact registered player skill binding required: '+requested)
    return rows[0]


def action_proof(text,skill):
    return subtree_evidence(text,skill,analyze(text,skill),registered_subtree_class(skill))


def wait_for(path,offset,predicate,seconds,stop_on_action_failure=False):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        tail=path.read_text(encoding='utf-8',errors='replace')[offset:]
        if predicate(tail):return tail
        if 'state=FAULTED'in tail:return tail
        if stop_on_action_failure and re.search(r'\[PBZBossControl\] \w+ success=false',tail):return tail
        time.sleep(.1)
    return path.read_text(encoding='utf-8',errors='replace')[offset:]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('skills',nargs='+');parser.add_argument('--interrupt',action='store_true')
    parser.add_argument('--cycle-target',action='store_true',help='诊断专用：强制一次F7；默认仅当前HUD证明遮挡时切换')
    args=parser.parse_args();owner,state=practice.owned_session()
    assert owner['phase']=='armed'and not owner.get('skill_lab')and not owner.get('expanded')
    assert len(set(args.skills))==len(args.skills)<=29
    bindings={requested:resolve_binding(owner['actual_bindings'],requested) for requested in args.skills}
    path=practice.log_path(state)
    if owner.get('boss_candidate'):
        from boss_candidate_gate import validate
        identifier=owner['boss_candidate'];validate(identifier)
        dossier=practice.read(practice.ROOT/'research/boss-adaptation/dossiers'/(identifier+'.json'))
        boss_name=dossier['metadata_identity']['display_name']
    else:
        from player_settings import BOSSES
        deployment=practice.read(Path(state['work'])/'control-lifecycle-deployment.json')
        boss_name=deployed_boss_name(owner,deployment,
            path.read_text(encoding='utf-8',errors='replace')[owner['log_offset']:],BOSSES)
    target=Path(state['work'])/'player-extra-skill-actions.json'
    history=json.loads(target.read_text(encoding='utf-8')) if target.exists() else []
    passed=True
    for requested in args.skills:
        binding=bindings[requested];skill=binding['skill']
        assert min(state['deadline_unix'],state['control_probe_expires_at']-20)-time.time()>80
        offset=len(path.read_text(encoding='utf-8',errors='replace'))
        row={'at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'state_file':state['state_file'],
             'skill':skill,'binding':binding,'interrupt':args.interrupt,
             'target_cycle_requested':args.cycle_target,'log_offset':offset,'passed':False,
             'cast_dispatched':False,'stage':'entry'}
        try:
            menu.click(0,0,2560,1600,'control_enter')
            tail=wait_for(path,offset,lambda t:'[PBZBossControl] enter success=true state=ACTIVE'in t,6,True)
            assert '[PBZBossControl] enter success=true state=ACTIVE'in tail,'Entry not verified'
            row['stage']='target_precondition'
            row['target_readiness']=ensure_visible_target(path,offset,
                'official-validation-'+Path(state['work']).name,wait_for,menu.click,time.time,args.cycle_target,
                boss_name=boss_name)
            row['stage']='dispatch'
            menu.click(0,0,2560,1600,('control_cancel_registered_skill_'if args.interrupt else'control_registered_skill_')+binding['slot'])
            row['cast_dispatched']=True;row['stage']='skill_lifecycle'
            if args.interrupt:
                tail=wait_for(path,offset,lambda t:bool(re.search(r'KEY_SKILL_BEGIN='+re.escape(skill)+r'\|[^\r\n]*\|active=[1-9]\d*',t)),5,True)
                assert re.search(r'KEY_SKILL_BEGIN='+re.escape(skill)+r'\|[^\r\n]*\|active=[1-9]\d*',tail),'No active skill proof'
            else:
                tail=wait_for(path,offset,lambda t:bool(action_proof(t,skill)['natural_completion']),
                    55 if registered_subtree_class(skill)else 40,True)
                assert action_proof(tail,skill)['natural_completion'],'No natural completion proof'
            if not args.interrupt:menu.click(0,0,2560,1600,'control_exit')
            row['stage']='restoration'
            tail=wait_for(path,offset,lambda t:restoration_result(t,'exit')['passed'],8)
            proof=action_proof(tail,skill);row['proof']=proof
            assert restoration_result(tail,'exit')['passed'],'Restoration incomplete'
            assert not args.interrupt or proof['active_cancel_and_restoration'],'Cancellation incomplete'
            row['passed']=True;row['stage']='complete'
        except Exception as error:
            row.update(passed=False,error=str(error),failure_kind=(
                'target_precondition_not_met'if row['stage']=='target_precondition'else row['stage']+'_failed'))
            passed=False
        finally:
            current=path.read_text(encoding='utf-8',errors='replace')[offset:]
            if not row.get('passed') and '[PBZBossControl] enter success=true state=ACTIVE'in current and not restoration_result(current,'exit')['passed']:
                try:
                    menu.click(0,0,2560,1600,'control_exit')
                    current=wait_for(path,offset,lambda t:restoration_result(t,'exit')['passed'],8)
                    row['cleanup_restoration']=restoration_result(current,'exit')
                except RuntimeError as error:
                    row['cleanup_error']=str(error)
            text=path.read_text(encoding='utf-8',errors='replace');row['log_end']=len(text)
            row['lines']=text[offset:].splitlines();history.append(row)
            target.write_text(json.dumps(history,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print(skill+': '+('PASS'if row['passed']else row['error']),flush=True)
        if not passed:break
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
