"""用途：只下载Valve公开清单作箱内网络对照；限时规则仅授予curl，PBZ始终封锁。"""
from pathlib import Path
import hashlib,json,socket,subprocess,sys,time,os
import official_validation as v
from prepare_manual_login import save
from test_wfp_isolation import change

ROOT=v.ROOT
LATEST=ROOT/'runtime/latest-manifest-probe.json'
URL='https://client-update.steamstatic.com/steam_client_win64'


def worker(mode,work,address):
    """用途：在箱内直接启动curl并记录其真实退出码，避免Start.exe转发返回码混淆。"""
    if mode=='all':
        for item in ['direct-resolved','direct-system-dns','existing-system-proxy']:worker(item,work,address)
        return
    c=v.c;c.isolation.select_box('PBZSteamLab');dll=c.isolation.api()
    if os.getpid() not in c.baseline.box_pids(dll):raise RuntimeError('Probe worker must be boxed')
    work=Path(work)
    if not work.is_relative_to(ROOT/'evidence/network-diagnostic'):raise RuntimeError('Output outside diagnostic folder')
    if mode not in ['direct-resolved','direct-system-dns','existing-system-proxy']:raise RuntimeError('Unknown probe mode')
    dest=work/(mode+'.bin');headers=work/(mode+'-headers.txt')
    args=[r'C:\Windows\System32\curl.exe','--silent','--show-error','--connect-timeout','5','--max-time','12',
          '--max-filesize','1048576','--output',str(dest),'--dump-header',str(headers)]
    if mode=='direct-resolved':args+=['--noproxy','*','--resolve',f'client-update.steamstatic.com:443:{address}']
    elif mode=='direct-system-dns':args+=['--noproxy','*']
    else:args+=['--proxy','http://127.0.0.1:7890','--noproxy','']
    args+=[URL];started=time.monotonic();r=subprocess.run(args,capture_output=True,timeout=16)
    data=dest.read_bytes() if dest.exists() else b''
    status=[line for line in headers.read_text(encoding='utf-8',errors='replace').splitlines() if line.startswith('HTTP/')] if headers.exists() else []
    save(work/(mode+'-worker.json'),{'mode':mode,'curl_exit':r.returncode,'seconds':round(time.monotonic()-started,2),
         'status':status,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest() if data else None,
         'looks_like_valve_manifest':b'win64' in data[:100] and b'"version"' in data,'stderr':r.stderr.decode(errors='replace')[:500]})


def restore(path):
    s=json.loads(path.read_text(encoding='utf-8'))
    if s.get('restored'):return s
    c=v.c;c.isolation.select_box('PBZSteamLab');dll=c.isolation.api()
    change('set','PBZSteamLab','AllowNetworkAccess','n')
    remaining=c.cleanup(dll)
    for rule in s['rules']:
        if rule in c.isolation.values(dll,'NetworkAccess'):change('delete','PBZSteamLab','NetworkAccess',rule)
    if not remaining:change('set','PBZSteamLab','AllowNetworkAccess',s['prior_allow_network'])
    c.isolation.check_policy(dll)
    s.update({'restored':True,'restored_at':v.utc8(),'remaining_box_pids':remaining})
    save(path,s);return s


def watchdog(path):
    c=v.c;c.isolation.select_box('PBZSteamLab');dll=c.isolation.api()
    while True:
        s=json.loads(path.read_text(encoding='utf-8'))
        if s.get('restored'):return
        try:stop=time.time()>=s['deadline_unix'] or path.with_suffix('.stop').exists() or bool(c.host_steam_pids(dll)) or bool(c.preflight.games_running())
        except Exception:stop=True
        if stop:restore(path);return
        time.sleep(1)


def main():
    c=v.c;c.isolation.select_box('PBZSteamLab');dll=c.isolation.api();policy=c.isolation.check_policy(dll)
    if c.baseline.box_pids(dll) or c.host_steam_pids(dll) or c.preflight.games_running():raise RuntimeError('Preserve current sessions')
    for suffix in (r'\steamlibrary\*',r'\steamapps\common\pbz\*'):
        if not any(p.casefold().endswith(suffix) for p in policy['ClosedFilePath']):raise RuntimeError('Game block missing')
    address=socket.gethostbyname('client-update.steamstatic.com')
    work=ROOT/'evidence/network-diagnostic'/time.strftime('%Y%m%d-%H%M%S-sandbox');work.mkdir(parents=True)
    path=work/'lease.json'
    rules=[f'curl.exe,Allow;Address={address};Port=443;Protocol=TCP',
           'curl.exe,Allow;Address=127.0.0.1;Port=7890;Protocol=TCP']
    s={'started_at':v.utc8(),'restored':False,'deadline_unix':time.time()+100,'prior_allow_network':policy['AllowNetworkAccess'][0],'rules':rules,'formal_before':c.baseline.formal_files()}
    save(path,s);save(LATEST,{'state_file':str(path)})
    subprocess.Popen([sys.executable,__file__,'--watchdog',str(path)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP)
    container=c.isolation.get_root(dll);results=[]
    try:
        for rule in rules:change('append','PBZSteamLab','NetworkAccess',rule)
        if sorted(c.isolation.values(dll,'NetworkAccess'))!=sorted(policy['NetworkAccess']+rules):raise RuntimeError('Probe network rules mismatch')
        # 用途：同一箱内父进程保持存活，避免连续Start.exe命令遇到箱内服务退出的竞争。
        args=[str(c.isolation.SBIE/'Start.exe'),'/box:PBZSteamLab','/silent','/hide_window','/wait',
              sys.executable,__file__,'--worker','all',str(work),address]
        r=subprocess.run(args,capture_output=True,timeout=55)
        for mode in ['direct-resolved','direct-system-dns','existing-system-proxy']:
            record=c.isolation.virtual_file(container,work/(mode+'-worker.json'))
            row=json.loads(record.read_text(encoding='utf-8')) if record.exists() else {'mode':mode,'worker_report_missing':True}
            row['sandbox_launcher_exit']=r.returncode
            results.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
    finally:
        path.with_suffix('.stop').touch()
        for _ in range(30):
            if json.loads(path.read_text(encoding='utf-8')).get('restored'):break
            time.sleep(.5)
        else:restore(path)
        after=c.baseline.formal_files()
        report={'finished_at':v.utc8(),'official_public_url':URL,'resolved_address':address,'no_account_data_sent':True,
                'no_game_started':True,'results':results,'restored':json.loads(path.read_text(encoding='utf-8'))['restored'],
                'formal_files_changed':[p for p in set(after)|set(s['formal_before']) if after.get(p)!=s['formal_before'].get(p)]}
        save(work/'result.json',report);save(ROOT/'evidence/latest-sandbox-manifest-probe.json',report)
        print(json.dumps({k:value for k,value in report.items() if k!='results'},ensure_ascii=False),flush=True)


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv)==3 and sys.argv[1]=='--watchdog':watchdog(Path(sys.argv[2]))
    elif len(sys.argv)==5 and sys.argv[1]=='--worker':worker(sys.argv[2],sys.argv[3],sys.argv[4])
    else:main()
