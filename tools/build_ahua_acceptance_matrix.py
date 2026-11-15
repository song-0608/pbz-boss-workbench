"""离线生成28能力的版本化验收清单；逐项区分历史与当前源码，不修改可玩标记。"""
from datetime import datetime
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from mod_installation import ROOT,digest


def capabilities():
    lua=ROOT.parent/'build/lua-harness/Release/lua-lab.exe'
    run=subprocess.run([str(lua),str(ROOT/'tools/export_ahua_capabilities.lua'),str(ROOT)],
        capture_output=True,text=True,encoding='utf-8',check=True,timeout=20,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    rows=[]
    for line in run.stdout.splitlines():
        if not line.startswith('CAP\t'):continue
        _,slot,skill,key,name,cls,damage,movement,natural,cancel=line.split('\t')
        rows.append({'slot':slot,'skill':skill,'key':key,'name':name,'class_path':cls,
            'damage_verified':damage=='true','movement_verified':movement=='true',
            'natural_declared':natural=='true','cancel_declared':cancel=='true'})
    if len(rows)!=29 or len({r['skill']for r in rows})!=28:
        raise RuntimeError('Unexpected real player catalog shape; update the milestone before acceptance')
    return rows


def collected_actions():
    actions=[]
    for path in sorted((ROOT/'evidence/official-validation').glob('*/player-skill-acceptance-evidence.json')):
        report=json.loads(path.read_text(encoding='utf-8'));work=path.parent
        state_path=ROOT/'runtime'/('official-validation-'+work.name)/'state.json'
        if not state_path.exists():continue
        state=json.loads(state_path.read_text(encoding='utf-8'))
        post=json.loads((work/'postcheck.json').read_text(encoding='utf-8'))
        if not(state.get('restored')and post['validation_state']==state['state_file']
            and not post['formal_files_changed']and not post['host_config_files_changed']
            and post['host_registry_unchanged']and post['research_box_empty']and post['research_loader_removed']):continue
        if digest(work/'UE4SS.log')!=report['log_sha256']:
            raise RuntimeError('Historical acceptance raw log changed: '+str(path))
        for row in report['actions']:
            if row.get('boss_id','ahua_guitoudao')!='ahua_guitoudao':continue
            actions.append(dict(row,session=work.name,evidence_file=str(path.relative_to(ROOT)),evidence_sha256=digest(path)))
    return actions


def build():
    bindings=capabilities();actions=collected_actions()
    current={p.relative_to(ROOT/'mod/PBZBossControl/Scripts').as_posix():digest(p)
        for p in(ROOT/'mod/PBZBossControl/Scripts').rglob('*.lua')if p.name!='main.lua'}
    skills=[]
    for skill in sorted({r['skill']for r in bindings}):
        source=next(r for r in bindings if r['skill']==skill)
        rows=[r for r in actions if r['skill']==skill]
        row={'skill':skill,'name':source['name'],'class_path':source['class_path'],
            'bindings':[{'slot':r['slot'],'key':r['key']}for r in bindings if r['skill']==skill],
            'damage_verified':source['damage_verified'],'movement_verified':source['movement_verified'],
            'natural_declared':source['natural_declared'],'cancel_declared':source['cancel_declared'],
            'ordinary_natural_evidence':[r for r in rows if r['natural_completion']and r['restoration']['passed']],
            'ordinary_cancel_evidence':[r for r in rows if r['active_cancel_and_restoration']]}
        row['current_source_ordinary_natural']=any(r['module_source_sha256']==current for r in row['ordinary_natural_evidence'])
        row['current_source_ordinary_cancel']=any(r['module_source_sha256']==current for r in row['ordinary_cancel_evidence'])
        skills.append(row)
    result={'at':datetime.now().astimezone().isoformat(),'ability_count':len(skills),'skill_binding_count':len(bindings),
        'scope':'报告中的历史通过仅对应各自部署SHA；没有本收集器旧记录的能力不推断为失败或已通过',
        'complete_mod':False,'module_source_sha256':current,'skills':skills,
        'current_source_all_ordinary_natural':all(r['current_source_ordinary_natural']for r in skills),
        'current_source_all_ordinary_cancel':all(r['current_source_ordinary_cancel']for r in skills)}
    target=ROOT/'evidence/adaptation/ahua-28-acceptance-matrix.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    csv_path=ROOT/'55-28能力验收清单.csv'
    with csv_path.open('w',encoding='utf-8-sig',newline='')as stream:
        writer=csv.writer(stream);writer.writerow(('能力ID','名称','默认键','已观察伤害','已观察位移','历史普通自然证据会话','历史普通取消证据会话','当前源码普通自然','当前源码普通取消'))
        for row in skills:
            writer.writerow((row['skill'],row['name'],' / '.join(r['key']for r in row['bindings']),row['damage_verified'],
                row['movement_verified'],' / '.join(sorted({r['session']for r in row['ordinary_natural_evidence']})),
                ' / '.join(sorted({r['session']for r in row['ordinary_cancel_evidence']})),
                row['current_source_ordinary_natural'],row['current_source_ordinary_cancel']))
    print(json.dumps({'report':str(target),'csv':str(csv_path),'ability_count':len(skills),
        'historical_collected_natural':sum(bool(r['ordinary_natural_evidence'])for r in skills),
        'historical_collected_cancel':sum(bool(r['ordinary_cancel_evidence'])for r in skills),'complete_mod':False},ensure_ascii=False))
    return result


if __name__=='__main__':build()
