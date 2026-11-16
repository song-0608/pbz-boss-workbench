"""Collect closed terrain observations; a refused selection never counts as acceptance."""
import argparse
import json
from pathlib import Path
import re
from mod_installation import ROOT,MANIFEST,digest
from four_boss_integration_workflow import modules
from build_yanqiansui_terrain_candidate import expected,verify


def collect(session):
    assert re.fullmatch(r'\d{8}-\d{6}',session)
    state_path=ROOT/'runtime'/('official-validation-'+session)/'state.json'
    state=json.loads(state_path.read_text(encoding='utf-8'))
    work=ROOT/'evidence/official-validation'/session
    assert state['restored'] and Path(state['work']).resolve()==work.resolve()
    post=json.loads((work/'postcheck.json').read_text(encoding='utf-8'))
    assert post['validation_state']==str(state_path)
    assert all(post[k]for k in ('research_box_empty','research_loader_removed','host_registry_unchanged'))
    assert not any(post[k]for k in ('formal_files_changed','host_config_files_changed','remaining_games'))
    candidate=ROOT/'runtime/release-candidates'/expected()[-1]
    manifest=verify(candidate)
    deployments=list(work.glob('control-lifecycle-deployment-*.json'));assert len(deployments)==1
    deployment=json.loads(deployments[0].read_text(encoding='utf-8'))
    assert deployment['module_source_sha256']==modules(manifest) and deployment['player_entry']
    raw_path=work/'UE4SS.log';raw=raw_path.read_text(encoding='utf-8',errors='replace')
    traces=list(re.finditer(r'PBZ_TERRAIN_TRACE:BEGIN=[\s\S]+?PBZ_TERRAIN_TRACE:END=queries:(\d+)\|accepted:(true|false)',raw))
    assert traces and re.findall(r'PLAYER_ENTRY_READY=([^\r\n]+)',raw)==['ahua_guitoudao']
    result=[]
    for index,trace in enumerate(traces):
        end=traces[index+1].start()if index+1<len(traces)else len(raw)
        tail=raw[trace.end():end]
        queries=re.findall(r'PBZ_TERRAIN_TRACE:QUERY=(\d+)\|wanted=([^|\r\n]+)\|actual=([^\r\n]+)',trace[0])
        assert 0<len(queries)==int(trace[1])<=192 and trace[2]=='false'
        assert [int(r[0])for r in queries]==list(range(1,len(queries)+1))
        assert tail.count('WORKBENCH_SELECTION_REJECTED=073_yanqiansui|')==1
        assert 'WORKBENCH_INPUT_RESTORED=true'in tail
        assert not any(t in tail for t in ('SPAWN_ATTEMPT=','OWNED_DESTROY_VERIFIED=','WORKBENCH_BOSS_SELECTED=','enter success=true'))
        unavailable=sum(r[2]=='unavailable'for r in queries)
        result.append({'log_offset':trace.start(),'log_end':trace.end(),'queries':len(queries),
                       'unavailable_projections':unavailable,'selection_refused':True,
                       'current_assembly_preserved':True,'workbench_input_restored':True})
    paths=[state_path,raw_path,work/'postcheck.json',*deployments,candidate/MANIFEST,ROOT/'tools/collect_yanqiansui_terrain.py']
    report={'schema':1,'session':session,'observations_verified':True,'ordinary_integration_accepted':False,
            'candidate':candidate.name,'module_source_sha256':deployment['module_source_sha256'],
            'terrain_checks':result,'formal_postcheck_passed':True,
            'sources':{p.relative_to(ROOT).as_posix():digest(p)for p in paths}}
    output=ROOT/'research/boss-adaptation/developer-attempt-receipts'/('yanqiansui-terrain-'+session+'.json')
    assert not output.exists(),'Preserve historical observations'
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {'observations_verified':True,'selection_attempts':len(result),'ordinary_integration_accepted':False,'receipt':str(output)}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('session');args=parser.parse_args()
    print(json.dumps(collect(args.session),ensure_ascii=False))
