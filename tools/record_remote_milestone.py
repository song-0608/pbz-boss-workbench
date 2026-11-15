"""用途：按每次独立实验和每招的配对日志登记证据，禁止把失败招式的掉血算为成功。"""
import json
import re
from pathlib import Path
import official_validation as v


def parse(log):
    runs=[]
    for part in log.split('PBZ_CONTROL_LIFECYCLE:DEFERRED_ACTOR=')[1:]:
        events=re.findall(r'PBZ_CONTROL_LIFECYCLE:([A-Z_]+)=([^\r\n]*)',part)
        run={'skills':[],'restored':False,'ended':False,'target_verified':False}
        skill=None
        for key,value in events:
            if key=='BATCH_SKILL':
                skill={'id':value,'activated':False,'natural_finish':False};run['skills'].append(skill)
            elif key=='TARGET_AFTER_SETTLE_VERIFIED':run['target_verified']=value=='true'
            elif key=='MOVEMENT_DELTA_XY':run['movement_delta_xy']=float(value)
            elif key=='RESTORE':run['restored']=value=='true|nil'
            elif key=='END':run['ended']=True
            elif key=='HEALTH_BEFORE' and skill:skill['health_before']=float(value)
            elif key=='HEALTH_AFTER' and skill:skill['health_after']=float(value)
            elif key=='SKILL_START' and skill:skill['activated']=value.startswith('true|')
            elif key=='SKILL_FINISHED_NATURALLY' and skill:skill['natural_finish']=value=='true'
        for skill in run['skills']:
            paired='health_before'in skill and'health_after'in skill
            skill['health_delta']=skill['health_before']-skill['health_after']if paired else None
            skill['damage_observed_during_successful_activation']=bool(paired and skill['activated']and skill['natural_finish']and skill['health_delta']>0)
        runs.append(run)
    return runs


def main():
    s=json.loads(v.state_path().read_text(encoding='utf-8'));work=Path(s['work'])
    if not s.get('restored'):raise RuntimeError('Finish research session before recording')
    post=json.loads((v.ROOT/'evidence/latest-native-diagnostic-postcheck.json').read_text(encoding='utf-8'))
    if post['validation_state']!=s['state_file']:raise RuntimeError('Fresh matching postcheck required')
    runs=parse((work/'UE4SS.log').read_text(encoding='utf-8',errors='replace'))
    result={'at':v.utc8(),'session':s['state_file'],'runs':runs,'completed_mod':False,
        'formal_files_changed':len(post['formal_files_changed']),'research_box_empty':post['research_box_empty'],
        'research_loader_removed':post['research_loader_removed'],
        'scope':'Temporary owned Ahua and owned enemy only; successful health deltas are observations, not a claim of every hit or damage attribution after rejection'}
    v.save(work/'remote-control-milestone.json',result)
    v.save(v.ROOT/'evidence/adaptation/ahua-remote-control-milestone.json',result)
    status_path=v.ROOT/'项目状态.json';status=json.loads(status_path.read_text(encoding='utf-8'))
    target=any(r['target_verified']and r['restored']and r['ended']for r in runs)
    damage=any(r['target_verified']and r['restored']and r['ended']and any(k['damage_observed_during_successful_activation']for k in r['skills'])for r in runs)
    status.update({'updated_at':v.utc8(),'boss_target_runtime_verified':target,'boss_damage_runtime_verified':damage,
        'latest_remote_evidence':str(work/'remote-control-milestone.json'),'boss_control_verified':False,
        'status_summary':'阿花遥控、原生AI焦点目标与真实掉血已有证据，玩家入口及完整生命周期仍在开发。',
        'blocked_reason':'玩家输入隔离、交互目标切换与死亡切图清理尚未完成验收',
        'next_action':'集中完成交互控制和输入屏障后进行整体验收',
        'not_done':['原主角攻击输入隔离','完整交互技能键位和目标切换','死亡切图及失败恢复','玩家版入口与使用清单']})
    v.save(status_path,status)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
