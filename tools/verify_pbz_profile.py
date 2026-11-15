"""用途：反复核对本项目自写 AOB 的唯一命中、RIP 语义、配置键和每份文件哈希。"""
import hashlib
import json
from pathlib import Path
import re
import sys
from datetime import datetime
from pbz_static_analysis import Analysis,ROOT
from aob_lab import parse_aob,find_matches,resolve_rip


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    x=Analysis();profile=ROOT/'adaptation/pbz-26367565';source=profile/'UE4SS_Signatures/GUObjectArray.lua'
    pattern=re.search(r'return "([0-9A-F? ]+)"',source.read_text(encoding='utf-8'))[1];hits=[]
    for s in x.pe.sections:
        if not s['executable']:continue
        for p in find_matches(x.data,parse_aob(pattern),s['raw_offset'],s['raw_offset']+s['raw_size']):
            targets=[resolve_rip(x.pe,p,o,2,6)['target_rva'] for o in (0,6,12)]
            hits.append({'rva':hex(x.pe.file_to_rva(p)),'targets':list(map(hex,targets)),
                         'layout_matches':targets[0]-targets[2]==0x20 and targets[1]-targets[2]==0x68})
    # 用途：验证键真实受当前 UE4SS 解析器支持，避免写入看似有效、实际被忽略的偏移。
    setter=(ROOT.parent/'upstream/RE-UE4SS/UE4SS/generated_include/MacroSetter.hpp').read_text(encoding='utf-8')
    supported=set(re.findall(r'parser\.get_\w+\(STR\("([^"]+)"\), STR\("([^"]+)"\)',setter))
    section=None;unknown=[];members=[]
    for line in (profile/'MemberVariableLayout.ini').read_text(encoding='utf-8').splitlines():
        text=line.split(';',1)[0].strip()
        if text.startswith('['):section=text[1:-1]
        elif '=' in text:
            key,val=map(str.strip,text.split('=',1));members.append({'section':section,'member':key,'offset':val})
            if (section,key) not in supported:unknown.append([section,key])
    report={'at':datetime.now().astimezone().isoformat(),'exe_sha256':x.sha256,
        'passed':len(hits)==1 and hits[0]['layout_matches'] and not unknown,'hits':hits,'unknown_keys':unknown,
        'members':members,'files':{str(p.relative_to(profile)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [source,profile/'MemberVariableLayout.ini']},'pbz_ue4ss_initialization_verified':False,
        'scope':'Static verification and manifest only; does not prove all inferred member offsets functionally correct'}
    target=ROOT/'evidence/adaptation/profile-verification.json'
    if target.exists():
        prior=json.loads(target.read_text(encoding='utf-8'))
        history=target.parent/('profile-verification-'+datetime.fromisoformat(prior['at']).strftime('%Y%m%d-%H%M%S')+'.json')
        if not history.exists():history.write_text(json.dumps(prior,indent=2),encoding='utf-8')
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'matches':len(hits),'offsets':len(members),'unknown_keys':unknown,'report':str(target)},ensure_ascii=False))
    if not report['passed']:raise RuntimeError('Profile static verification failed')


if __name__=='__main__':main()
