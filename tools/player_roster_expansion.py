"""Prepare observed additional characters and combined metadata batches without starting the game."""
import argparse
import json
from pathlib import Path

from boss_adaptation_workflow import ROOT, BUILD, sha, write_json
import boss_metadata_jobs as metadata

CATALOG='research/boss-adaptation/catalog.json'
QUEUE='research/boss-adaptation/expansion-queue.json'


def plan(root=ROOT):
    catalog=json.loads((root/CATALOG).read_bytes());queue=json.loads((root/QUEUE).read_bytes())
    assert catalog['target_build_sha256']==queue['target_build_sha256']==BUILD
    assert len(queue['candidate_ids'])==len(set(queue['candidate_ids']))<=12
    for row in catalog['sources']:
        path=(root/row['path']).resolve()
        assert path.is_relative_to((root/'evidence').resolve()) and sha(path)==row['sha256']
    indexed={row['id']:row for row in catalog['candidates']};previews=[];candidates=[]
    for identifier in queue['candidate_ids']:
        candidate=indexed[identifier]
        assert not candidate.get('reference_only')
        jobs=metadata.jobs_for(candidate)
        characters=[row for row in jobs if row['role']=='character']
        assert characters
        configs=set(c for row in characters for c in row['config_candidates'])
        variants=len(characters)!=1 or len(configs)!=1
        previews.append(dict(id=identifier,name=candidate['resource_folder']+'（资源候选）',playable=False,
            reason='主身/阶段配置待核对' if variants else '等待合批身份与技能元数据核验',
            detail=str(len(characters))+'个角色类候选 / '+str(len(configs))+'个配置候选 / '
                   +str(sum(j['role']=='ability' for j in jobs))+'项能力元数据请求；尚不可接管',
            stage='variant_binding_required' if variants else 'metadata_ready'))
        candidates.append(candidate)
    batches=metadata.batches(candidates)
    assert len(previews)==6 and sum(len(batch) for batch in batches)==119
    return dict(schema=1,target_build_sha256=BUILD,previews=previews,jobs=batches,
        catalog_sha256=sha(root/CATALOG),queue_sha256=sha(root/QUEUE),
        new_playable_bosses=0,installed=False,game_started=False)


def build(root=ROOT):
    planned=plan(root);rows=[]
    for jobs in planned['jobs']:
        target=metadata.freeze(jobs,root/'runtime/player-experience-metadata',root)
        manifest=metadata.verify_batch(target,root)
        rows.append(dict(directory=target.relative_to(root).as_posix(),requests=len(jobs),
            candidate_ids=list(dict.fromkeys(j['id'] for j in jobs)),
            manifest_sha256=sha(target/'metadata-probe-manifest.json'),
            script_sha256=manifest['script_sha256']))
    report=dict(planned,metadata_batches=rows)
    report.pop('jobs')
    report['sources']={name:sha(root/name) for name in ('tools/player_roster_expansion.py',
        'tests/test_player_roster_expansion.py',*metadata.SOURCES)}
    output=root/'evidence/adaptation/player-experience-roster-offline.json'
    write_json(output,report);return output


if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    output=build();report=json.loads(output.read_bytes())
    print(json.dumps(dict(report=str(output),additional_candidates=len(report['previews']),
        batches=len(report['metadata_batches']),requests=sum(r['requests'] for r in report['metadata_batches']),
        new_playable_bosses=0,game_started=False),ensure_ascii=False))
