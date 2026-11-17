"""Independently collect each Boss in one closed single-player research session."""
import argparse
from pathlib import Path
import re
import boss_skill_expansion as expansion
import boss_skill_workflow as workflow
from boss_skill_session import evaluate
from boss_adaptation_workflow import ROOT,BUILD,sha,write_json
from mod_installation import active_mod_root


def collect(session,root=ROOT):
    assert re.fullmatch(r'\d{8}-\d{6}',session)
    state_path=root/'runtime'/('official-validation-'+session)/'state.json'
    state=expansion.read(state_path);work=root/'evidence/official-validation'/session
    assert Path(state['work']).resolve()==work.resolve() and state['restored'] is True
    post_path=work/'postcheck.json';post=expansion.read(post_path)
    assert post['validation_state']==str(state_path)
    assert all(post[k] is True for k in ('validation_restored','research_box_empty',
        'research_loader_removed','host_registry_unchanged'))
    assert post['formal_files_changed']==[] and post['host_config_files_changed']==[]
    raw_path=work/'UE4SS.log';raw=raw_path.read_text(encoding='utf-8',errors='replace')
    actions_path=work/'player-extra-skill-actions.json';actions=expansion.read(actions_path)
    assert all(row['state_file']==str(state_path) for row in actions)
    sources={p.relative_to(root).as_posix():sha(p) for p in (state_path,post_path,raw_path,actions_path)}
    results=[];intervals=[]
    for item in expansion.read(root/expansion.QUEUE)['bosses']:
        identifier=item['id'];milestone_path=work/('boss-skill-milestone-'+identifier+'.json')
        if not milestone_path.exists():continue
        milestone=expansion.read(milestone_path)
        assert milestone['candidate']==identifier and milestone['state_file']==str(state_path)
        assert not milestone.get('natural_session'),'Expansion actions must be independently tested'
        deployments=[p for p in work.glob('control-lifecycle-deployment-*.json')
                     if expansion.read(p).get('boss_candidate')==identifier]
        assert len(deployments)==1,'One exact expansion assembly per Boss required'
        deployment_path=deployments[0];deployment=expansion.read(deployment_path)
        bundle=Path(deployment['developer_bundle']);grant=expansion.validate(identifier,bundle,root=root)
        assert deployment['candidate_identity_grant']==grant
        assert deployment['grant']['exe_sha256']==BUILD and deployment['player_entry'] is False
        manifest=expansion.read(bundle/'manifest.json')
        base={n.removeprefix('Scripts/'):d for n,d in manifest['base_mod_files'].items()
              if n.startswith('Scripts/') and n!='Scripts/main.lua'}
        base['boss_candidate.lua']=manifest['overrides']['Scripts/boss_candidate.lua']
        assert deployment['module_source_sha256']==base
        flows=[p for p in (root/'runtime/developer-workflows').glob('skills-'+identifier+'-*')
               if expansion.read(p/'manifest.json').get('bundle_manifest_sha256')==sha(bundle/'manifest.json')]
        verified=[p for p in flows if workflow.verify(p,root=root)]
        assert len(verified)==1,'Exact current workflow revision required'
        source=active_mod_root(root)/'Experiments/spawn_lifecycle.lua'
        assert deployment['assembly_source_sha256']==sha(source)
        expected={row['test_id']:row['class_path'] for row in manifest['skill_expansion']['actions']}
        result=evaluate(raw,milestone['log_offset'],milestone['log_end'],identifier,
            session,expected,actions,manifest['definition']['display_name'])
        result['milestone_passed']=milestone['passed'] is True
        result['all_four_accepted']=result['all_four_accepted'] and result['milestone_passed']
        result.update(bundle=str(bundle),bundle_manifest_sha256=sha(bundle/'manifest.json'),
            module_source_sha256=deployment['module_source_sha256'])
        results.append(result);intervals.append((result['log_offset'],result['log_end']))
        for p in (milestone_path,deployment_path,bundle/'manifest.json',bundle/'boss_candidate.lua',
                  verified[0]/'manifest.json',source):
            sources[p.relative_to(root).as_posix()]=sha(p)
    assert results,'No completed expansion attempts found'
    assert len(set(intervals))==len(intervals)
    ordered=sorted(intervals);assert all(a[1]<=b[0] for a,b in zip(ordered,ordered[1:]))
    return dict(schema=1,session=session,target_build_sha256=BUILD,bosses=results,sources=sources,
        all_twelve_accepted=len(results)==3 and all(row['all_four_accepted'] for row in results),
        formal_postcheck_passed=True,playable=False,game_started_by_collector=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('session')
    parser.add_argument('--verify',action='store_true');args=parser.parse_args()
    result=collect(args.session);output=ROOT/'evidence/official-validation'/args.session/'boss-skill-session.json'
    if args.verify:assert expansion.read(output)==result,'Collected skill receipt changed'
    else:
        assert not output.exists(),'Preserve collected attempt';write_json(output,result)
    print(__import__('json').dumps(dict(report=str(output),all_twelve_accepted=result['all_twelve_accepted'],
        bosses=[dict(id=row['id'],accepted=list(row['accepted_skills']),all_four_accepted=row['all_four_accepted'])
                for row in result['bosses']],playable=False),ensure_ascii=False))
