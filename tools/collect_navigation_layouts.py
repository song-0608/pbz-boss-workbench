"""只收集同版导航模块、完整收尾且真实出招恢复成功的不同落点。"""
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
from control_action_evidence import restoration_result

ROOT=Path(__file__).resolve().parents[1]
NAV_RE=re.compile(r'NAVIGATION_LAYOUT_VERIFIED=boss=([\d.-]+),([\d.-]+),([\d.-]+)\|targets=2')


def layout_proof(segment):
    match=NAV_RE.search(segment)
    natural=None;restored={'passed':False}
    cycles=list(re.finditer(r'\[PBZBossControl\] enter success=true state=ACTIVE',segment))
    for index,enter in enumerate(cycles):
        cycle=segment[enter.start():cycles[index+1].start()if index+1<len(cycles)else len(segment)]
        match_end=re.search(r'KEY_SKILL_END=([^|\r\n]+)\|peak=[1-9]\d*\|active=0\|natural=true'
            r'\|health_before=([\d.-]+)\|health_after=([\d.-]+)\|distance=([\d.eE+-]+)',cycle)
        exit_at=cycle.find('[PBZBossControl] exit success=true state=OFF')
        if match_end and match_end.end()<exit_at:
            before,after,distance=map(float,match_end.group(2,3,4))
            if all(math.isfinite(v)and v>=0 for v in(before,after,distance))and(before>after or distance>0):
                check=restoration_result(cycle,'exit')
                if check['passed']:natural,restored=match_end,check;break
    result={'coordinates':[float(match[i])for i in (1,2,3)]if match else None,
        'spawned_target_visibility':'NAVIGATION_TARGET_VISIBILITY_VERIFIED=2'in segment,
        'interactive_ready':'INTERACTIVE_READY='in segment,
        'entered':'[PBZBossControl] enter success=true state=ACTIVE'in segment,
        'natural_skill':natural[1]if natural else None,'restoration':restored,
        'failures_absent':not any(t in segment for t in('state=FAULTED','PBZ_CONTROL_LIFECYCLE:ISSUE_',
            'PREREQUISITE_NOT_READY=','NAVIGATION_LAYOUT_REJECTED=','PBZ_CONTROL_RESTORE:FAILED='))}
    result['passed']=bool(match and all(math.isfinite(v)for v in result['coordinates'])and natural and restored['passed']and all(result[k]for k in
        ('spawned_target_visibility','interactive_ready','entered','failures_absent')))
    return result


def collect():
    expected={name:hashlib.sha256((ROOT/'mod/PBZBossControl/Scripts'/name).read_bytes()).hexdigest()
              for name in('arena_layout.lua','ue_arena_layout.lua')}
    accepted=[]
    for work in sorted((ROOT/'evidence/official-validation').iterdir()):
        try:
            state=json.loads((ROOT/'runtime'/('official-validation-'+work.name)/'state.json').read_text(encoding='utf-8'))
            post=json.loads((work/'postcheck.json').read_text(encoding='utf-8'))
            if not(state.get('restored')and post['validation_state']==state['state_file']
                and not post['formal_files_changed']and not post['host_config_files_changed']
                and post['host_registry_unchanged']and post['research_box_empty']and post['research_loader_removed']):continue
            raw=(work/'UE4SS.log').read_bytes();text=raw.decode('utf-8',errors='replace')
            deployments=[(p,json.loads(p.read_text(encoding='utf-8')))for p in work.glob('control-lifecycle-deployment-*.json')]
            deployments.sort(key=lambda r:r[1]['at'])
            for index,(path,deployment)in enumerate(deployments):
                if not deployment.get('arena_navigation_trial')or any(deployment['module_source_sha256'].get(k)!=v for k,v in expected.items()):continue
                start=datetime.fromisoformat(deployment['at']).replace(tzinfo=None)
                end=datetime.fromisoformat(deployments[index+1][1]['at']).replace(tzinfo=None)if index+1<len(deployments)else datetime.max
                lines=[]
                for line in text.splitlines():
                    stamp=re.match(r'^\[([^]]+)\]',line)
                    if stamp and start<=datetime.fromisoformat(stamp[1])<end:lines.append(line)
                block='\n'.join(lines);anchors=list(NAV_RE.finditer(block))
                for n,anchor in enumerate(anchors):
                    segment=block[anchor.start():anchors[n+1].start()if n+1<len(anchors)else len(block)]
                    result=layout_proof(segment)
                    if result['passed']:
                        accepted.append(dict(result,session=work.name,deployment_file=path.name,
                            log_sha256=hashlib.sha256(raw).hexdigest(),module_source_sha256=deployment['module_source_sha256']))
        except (OSError,ValueError,KeyError,TypeError):continue
    unique=sorted({tuple(round(v,1)for v in row['coordinates'])for row in accepted})
    result={'at':datetime.now().astimezone().isoformat(),'passed':len(unique)>=3,
        'scope':'仅已验证地图的局部不平整导航地面和不同装配落点；不推广任意关卡、陡坡或水面',
        'navigation_module_sha256':expected,'successful_assemblies':accepted,'unique_locations':unique,
        'unique_location_count':len(unique),'complete_mod':False}
    target=ROOT/'evidence/adaptation/navigation-layout-acceptance.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'report':str(target),'passed':result['passed'],'unique_locations':unique},ensure_ascii=False))
    return 0 if result['passed']else 1


if __name__=='__main__':raise SystemExit(collect())
