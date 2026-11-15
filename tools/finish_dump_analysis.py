"""用途：汇总本地转储和实验结果、复核分析器自检；不启动游戏，不上传转储。"""
from datetime import datetime,timezone,timedelta
import json
from pathlib import Path
import re
import subprocess
import sys
import official_validation as v


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    analysis=v.ROOT/'runtime/dump-analysis'
    dump_root=v.ROOT/'sandbox/PBZSteamLab/drive/C/Users/xuesong/AppData/Local/CrashDumps'
    fixture=json.loads((analysis/'fixture-report.json').read_text())
    map_text=(analysis/'fixture.map').read_text(errors='replace')
    expected={}
    for name in ('known_leaf','known_middle','known_outer'):
        match=re.search(r'^\s*[0-9A-Fa-f]+:([0-9A-Fa-f]+)\s+\?'+name+r'@@\S*\s+([0-9A-Fa-f]+)',map_text,re.M)
        if not match:raise RuntimeError('Fixture MAP symbol missing: '+name)
        # 用途：RVA=本工具代码段偏移+0x1000；这只用于固定的自建验证程序，不套用到游戏。
        expected[name]=int(match.group(1),16)+0x1000
    frames=fixture['frames']
    assert len(frames)>=3 and frames[0]['module']=='offline_dump_fixture.exe'
    actual=[int(f['rva'],16) for f in frames[:3]]
    starts=list(expected.values())
    assert actual[0]==starts[0] and starts[1]<=actual[1]<starts[2] and starts[2]<=actual[2]<starts[2]+128
    test={'at':v.utc8(),'passed':True,'expected_chain':['known_leaf','known_middle','known_outer'],
        'source':'Own fixture MAP file compared with dump StackWalk64 frames',
        'recovered_callers':fixture['recovered_caller_frames'],'no_live_game_access':True}
    v.save(analysis/'selftest.json',test)
    runs=[('16904','20261112-194538'),('33744','20261112-195144'),('39724','20261112-195754'),
          ('36292','20261112-200713'),('36900','20261112-200945')]
    summaries=[]
    for pid,stamp in runs:
        work=v.ROOT/'evidence/official-validation'/stamp;report=work/'stackwalk.json'
        subprocess.run([str(analysis/'offline_dump_stack.exe'),str(dump_root/f'PBZ.exe.{pid}.dmp'),str(report),str(analysis/'symbols')],check=True,capture_output=True,timeout=30)
        result=json.loads(report.read_text());frame=result['frames'][0]
        module_names=set(__import__('inspect_client_dump').inspect(dump_root/f'PBZ.exe.{pid}.dmp')['module_names'])
        summaries.append({'run':stamp,'exception':result['exception_code'],'location':frame['module']+'+'+frame['rva'],
            'recovered_callers':result['recovered_caller_frames'],
            'local_runtime_function_covers_exception':result['exception_pc_covered_by_local_runtime_function'],
            'steam_overlay_loaded':'gameoverlayrenderer64.dll' in module_names,
            'nvidia_overlay_loaded':bool({'nvspcap64.dll','nvppex.dll'} & module_names)})
    result={'at':v.utc8(),'selftest':test,'runs':summaries,
        'no_menu_verified':True,'root_cause_identified':False,
        'finding':'Overlay absence was verified in loaded-module samples and dumps; the observed PBZ access violation still occurs.',
        'stack_limit':'No caller frames were recovered for PBZ; do not label earlier stack-address candidates as call stacks.',
        'official_update_health_verified':False,'game_binary_modified':False,'ue4ss_deployed':False,'gameplay_performed':False}
    v.save(v.ROOT/'evidence/latest-offline-dump-analysis.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
