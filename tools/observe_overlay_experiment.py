"""用途：只读采样研究箱游戏模块，验证叠加层是否真实缺席；并记录窗口与退出码。"""
import json
import subprocess
import sys
import threading
import time
from pathlib import Path
import official_validation as v
import observe_official_startup as observer


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    c=v.c;c.isolation.select_box('PBZSteamLab');dll=c.isolation.api()
    state=json.loads(v.state_path().read_text(encoding='utf-8'));work=Path(state['work'])
    offline=bool(state.get('offline_validation'))
    c.isolation.check_policy(dll,allow_official_validation=not offline,allow_offline_validation=offline)
    if not state.get('steam_overlay_block_added'):raise RuntimeError('No active overlay experiment')
    stop=threading.Event();samples=[]
    def sample():
        # 用途：仅列举目标 PID 的模块名；不读取内存字符串、不导出命令行和账号。
        while not stop.is_set():
            current=json.loads(v.state_path().read_text(encoding='utf-8'))
            if current.get('restored') or time.time()>=current['deadline_unix']:return
            try:
                pids=[p['ProcessId'] for p in c.box_processes(dll) if p['Name'].lower()=='pbz.exe']
                if pids:
                    code='@('+','.join(map(str,pids))+') | ForEach-Object { $p = Get-Process -Id $_ -ErrorAction SilentlyContinue; if ($p) { try { [pscustomobject]@{ pid=$p.Id; names=@($p.Modules | Select-Object -ExpandProperty ModuleName); inspected=$true } } catch { [pscustomobject]@{ pid=$p.Id; names=@(); inspected=$false } } } } | ConvertTo-Json -Compress -Depth 4'
                    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',code],capture_output=True,timeout=10)
                    if not result.returncode and result.stdout.strip():
                        raw=json.loads(result.stdout);raw=raw if isinstance(raw,list) else [raw]
                        for item in raw:
                            names={n.lower() for n in item.get('names',[])}
                            samples.append({'at':v.utc8(),'pid':item['pid'],'inspected':item['inspected'],
                                'module_count':len(names),'d3d12_loaded':'d3d12.dll' in names,
                                'steam_overlay_loaded':'gameoverlayrenderer64.dll' in names,
                                'nvidia_capture_loaded':'nvspcap64.dll' in names,
                                'nvidia_present_loaded':'nvppex.dll' in names,
                                'nvidia_overlay_loaded':bool(names & {'nvspcap64.dll','nvppex.dll'})})
                        v.save(work/'overlay-module-samples.json',samples)
            except Exception as error:
                samples.append({'at':v.utc8(),'error_type':type(error).__name__})
                v.save(work/'overlay-module-samples.json',samples)
            stop.wait(3)
    thread=threading.Thread(target=sample,daemon=True);thread.start()
    try:observer.observe(120,stop_on_render=False)
    finally:
        stop.set();thread.join(12);v.save(work/'overlay-module-samples.json',samples)
    late=[s for s in samples if s.get('inspected') and s.get('d3d12_loaded')]
    outcome={'at':v.utc8(),'late_module_samples':len(late),
        'steam_overlay_absent_in_all_late_samples':bool(late) and all(not s['steam_overlay_loaded'] for s in late),
        'nvidia_overlay_absent_in_all_late_samples':bool(late) and all(not s['nvidia_overlay_loaded'] for s in late),
        'sampled_pids':sorted({s['pid'] for s in samples if 'pid' in s}),
        'menu_verified':False,'sample_count':len(samples)}
    v.save(work/'overlay-experiment-outcome.json',outcome)
    print(json.dumps(outcome,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
