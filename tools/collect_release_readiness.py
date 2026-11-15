"""离线汇总同一固定候选的发布门槛；缺证据就报告缺口，不改变发布或可玩标记。"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path

from build_ahua_acceptance_matrix import build as build_matrix
from collect_auto_world_reassembly import proof as world_proof
from collect_practice_stability import proof as stability_proof
from mod_installation import ROOT, MANIFEST, digest, read, validate_package


def evaluate(skills, stability, reloads, bindings, expected_bindings, installation, checks):
    natural={r['skill'] for r in skills if r.get('natural_completion') and r.get('restoration',{}).get('passed')}
    cancelled={r['skill'] for r in skills if r.get('active_cancel_and_restoration')}
    expected={r['skill'] for r in expected_bindings}
    covered={(r['slot'],r['skill'],r['key']) for r in bindings}
    gates={
        'local_checks_current':bool(checks),
        'installed_candidate_used_and_closed':bool(installation),
        'all_28_natural_and_restored':expected <= natural and len(expected)==28,
        'all_28_active_cancel_and_restored':expected <= cancelled and len(expected)==28,
        'all_29_actual_bindings':len(expected_bindings)==29 and all(
            (r['slot'],r['skill'],r['key']) in covered for r in expected_bindings),
        'full_600_seconds_and_continuous_active':bool(stability),
        'ordinary_native_menu_world_cycle':bool(reloads),
    }
    return {'gates':gates,'ready_for_release':all(gates.values()),
            'missing_natural':sorted(expected-natural),'missing_cancel':sorted(expected-cancelled),
            'missing_bindings':[r for r in expected_bindings if (r['slot'],r['skill'],r['key']) not in covered]}


def collect(package):
    package=Path(package).resolve();manifest=validate_package(package)
    payload=package/'PBZBossControl';scripts=payload/'Scripts'
    modules={p.relative_to(scripts).as_posix():digest(p) for p in scripts.rglob('*.lua') if p.name!='main.lua'}
    assembly=digest(payload/'Experiments/spawn_lifecycle.lua')
    matrix=build_matrix()
    if matrix['module_source_sha256']!=modules:
        raise RuntimeError('Acceptance matrix source does not match the immutable candidate')
    from build_ahua_acceptance_matrix import capabilities
    bindings=capabilities()
    # 使用玩家实际配置，而不是默认键位冒充当轮输入。
    import player_keymap
    keymap=player_keymap.read()
    expected=[{'slot':r['slot'],'skill':r['skill'],'key':keymap['skills'][r['slot']]} for r in bindings]
    checks=read(ROOT/'evidence/adaptation/ahua-delivery-local-checks.json')
    checks_current=checks.get('passed') and all(digest(ROOT/n)==sha for n,sha in checks['source_sha256'].items())
    accepted=[];proof_bindings=[];stability=[];reloads=[];sessions=[];installed=[]
    for work in sorted((ROOT/'evidence/official-validation').iterdir()):
        if not work.is_dir() or not (work/'postcheck.json').exists():continue
        state_file=ROOT/'runtime'/('official-validation-'+work.name)/'state.json'
        if not state_file.exists():continue
        state,post=read(state_file),read(work/'postcheck.json')
        closed=(state.get('restored') and post.get('validation_state')==state.get('state_file')
                and not post.get('formal_files_changed') and not post.get('host_config_files_changed')
                and post.get('host_registry_unchanged') and post.get('research_box_empty') and post.get('research_loader_removed'))
        if not closed or not (work/'UE4SS.log').exists():continue
        deployments=[read(p) for p in work.glob('control-lifecycle-deployment-*.json')]
        matching=[d for d in deployments if d.get('player_entry') and d.get('module_source_sha256')==modules
                  and d.get('assembly_source_sha256')==assembly]
        if not matching:continue
        raw=(work/'UE4SS.log').read_bytes();sha=hashlib.sha256(raw).hexdigest();text=raw.decode('utf-8',errors='replace')
        sessions.append(work.name)
        if any(Path(d.get('mod_source_directory','')).parent.name==manifest['release_id'] for d in matching):
            installed.append(work.name)
        if (work/'player-skill-acceptance-evidence.json').exists():
            evidence=read(work/'player-skill-acceptance-evidence.json')
            if evidence['log_sha256']!=sha:raise RuntimeError('Skill evidence raw log changed: '+work.name)
            actions=read(work/'player-extra-skill-actions.json')
            for row in evidence['actions']:
                if row.get('boss_id','ahua_guitoudao')!='ahua_guitoudao':continue
                if row.get('module_source_sha256')!=modules:continue
                accepted.append(row)
                if row.get('natural_completion') and row.get('restoration',{}).get('passed') or row.get('active_cancel_and_restoration'):
                    matches=[a for a in actions if a['log_offset']==row['log_offset'] and a.get('log_end')==row['log_end']]
                    if len(matches)!=1:raise RuntimeError('Exact action binding witness required')
                    proof_bindings.append(matches[0]['binding'])
        if len(deployments)==1:
            result=stability_proof(text,work.name)
            if result['passed']:stability.append({'session':work.name,'proof':result,'log_sha256':sha})
        if (work/'auto-world-reassembly-evidence.json').exists():
            evidence=read(work/'auto-world-reassembly-evidence.json')
            if evidence['log_sha256']!=sha:raise RuntimeError('World evidence raw log changed: '+work.name)
            begin,end=evidence.get('proof_log_offset',0),evidence.get('proof_log_end',len(text))
            if not(type(begin)is int and type(end)is int and 0<=begin<end<=len(text)):
                raise RuntimeError('Invalid world-cycle proof interval: '+work.name)
            if begin:
                assert text[begin:].startswith('PBZ_CONTROL_LIFECYCLE:PLAYER_ENTRY_READY=ahua_guitoudao')
                assert 'WORKBENCH_BOSS_SELECTED='not in text[begin:end]
            if (evidence.get('passed') and evidence.get('ordinary_player_entry')
                    and evidence.get('module_source_sha256')==modules and world_proof(text[begin:end])['passed']):
                reloads.append({'session':work.name,'evidence':str((work/'auto-world-reassembly-evidence.json').relative_to(ROOT))})
    result=evaluate(accepted,stability,reloads,proof_bindings,expected,installed,checks_current)
    result.update(at=datetime.now().astimezone().isoformat(),release_id=manifest['release_id'],
                  candidate_manifest_sha256=digest(package/MANIFEST),module_source_sha256=modules,
                  exact_source_closed_sessions=sessions,installed_closed_sessions=installed,expected_bindings=expected,
                  stability=stability,native_menu_reloads=reloads,complete_mod=False,
                  game_started=False,scope='current fixed build, local protected offline launcher')
    target=ROOT/'evidence/adaptation/ahua-release-readiness.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('release_id','gates','ready_for_release','missing_natural','missing_cancel')},ensure_ascii=False,indent=2))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('package');args=parser.parse_args()
    collect(args.package)
