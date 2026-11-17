"""Archive native observations without turning partial trials into release acceptance."""
import argparse
import json
from pathlib import Path
import re

from boss_adaptation_workflow import ROOT, sha
from mod_installation import MANIFEST, validate_package


def observe(text):
    role = None
    active = False
    primary = None
    pending = {}
    attacks, roles, routes, events = [], [], [], []
    for number, line in enumerate(text.splitlines(), 1):
        if 'PBZ_CONTROL_LIFECYCLE:SPAWN_ATTEMPT=' in line:
            role, active, primary, pending = None, False, None, {}
        match = re.search(r'PBZ_CONTROL_LIFECYCLE:PLAYER_ENTRY_READY=([^\r\n]+)', line)
        if match:
            role = match[1]; roles.append(dict(role=role, ready_line=number))
        if '[PBZBossControl] enter success=true state=ACTIVE' in line:
            active = True
            events.append(dict(event='takeover', role=role, line=number))
        if re.search(r'\[PBZBossControl\] \w+ success=true state=OFF', line):
            active = False
        if '[PBZBossControl] primary_attack success=true state=ACTIVE' in line:
            primary = dict(role=role, dispatch_line=number, active=active)
        match = re.search(r'PBZ_CONTROL_LIFECYCLE:KEY_SKILL_BEGIN=([^|]+)\|', line)
        if match:
            pending[match[1]] = primary
            primary = None
        match = re.search(r'PBZ_CONTROL_LIFECYCLE:KEY_SKILL_END=([^|]+)\|.*?natural=(true|false)\|'
                          r'health_before=([\d.]+)\|health_after=([\d.]+)', line)
        if match:
            attempt = pending.pop(match[1], None)
            if attempt:
                before, after = float(match[3]), float(match[4])
                attacks.append(dict(attempt, skill=match[1], end_line=number,
                    natural=match[2] == 'true', health_before=before, health_after=after,
                    observed_damage=before-after))
        match = re.search(r'PBZ_CONTROL_LIFECYCLE:CROSS_MAP_TRIAL_ROUTE=([^|]+)\|([^\r\n]+)', line)
        if match:
            routes.append(dict(source=match[1], destination=match[2], line=number))
        for event in ('MAP_TRAVEL_PRE_ACTIVE', 'MAP_TRAVEL_RESTORED_BEFORE_LOAD', 'MAP_TRAVEL_IDLE_CLEANED',
                      'IDLE_WORLD_CHANGED', 'WORLD_REASSEMBLY_WAIT'):
            if 'PBZ_CONTROL_LIFECYCLE:' + event + '=' in line:
                events.append(dict(event=event, role=role, line=number))
    return dict(ready_roles=roles, primary_observations=attacks, cross_map_requests=routes, lifecycle=events,
        runtime_fault_lines=[i for i,line in enumerate(text.splitlines(),1)
            if 'state=FAULTED' in line or 'PBZ_CONTROL_LIFECYCLE:ISSUE_' in line])


def report(session):
    directory = ROOT / 'evidence/official-validation' / session
    paths = [directory / name for name in ('UE4SS.log', 'control-lifecycle-deployment.json', 'postcheck.json')]
    assert all(p.is_file() for p in paths), 'Only a closed trial with original evidence can be archived'
    deployment = json.loads(paths[1].read_bytes())
    postcheck = json.loads(paths[2].read_bytes())
    # This is a historical observation, so validate its frozen package rather
    # than comparing it to the possibly newer developer source tree.
    workflows = []
    for item in (ROOT / 'runtime/integration-workflows').glob('travel-repair-*/manifest.json'):
        frozen = json.loads(item.read_bytes())
        package = Path(frozen['candidate'])
        manifest = validate_package(package)
        actual = deployment['module_source_sha256']
        # Deployment keys are module names, with their source-relative path stored in the manifest.
        from four_boss_integration_workflow import modules
        if modules(manifest) == actual:
            workflows.append(dict(manifest=str(item), sha256=sha(item), candidate=str(package),
                candidate_manifest_sha256=sha(package / MANIFEST)))
    assert workflows, 'No exact frozen workflow matches the deployment'
    observed = observe(paths[0].read_text(encoding='utf-8', errors='replace'))
    record = dict(schema=1, session=session, status='partial-development-observations',
        complete_mod=False, release_accepted=False, travel_repair_runtime_verified=False,
        sources={str(p.relative_to(ROOT)): sha(p) for p in paths}, matching_workflows=workflows,
        observed=observed, closed_cleanly=bool(postcheck.get('validation_restored')
            and postcheck.get('research_box_empty') and postcheck.get('research_loader_removed')
            and postcheck.get('formal_files_changed') == [] and postcheck.get('host_config_files_changed') == []
            and postcheck.get('host_registry_unchanged')),
        limits=['A left-button skill shortcut is not a complete native normal-attack combo.',
                'Recorded health deltas are observations, not full per-role release acceptance.',
                'Cross-map requests alone do not prove loading, reassembly or playable performance.'])
    output = directory / 'player-travel-progress.json'
    with output.open('x', encoding='utf-8') as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2); stream.write('\n')
    return output, record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session'); args = parser.parse_args()
    assert re.fullmatch(r'\d{8}-\d{6}', args.session), 'Exact research session id required'
    output, record = report(args.session)
    print(json.dumps(dict(report=str(output), closed_cleanly=record['closed_cleanly'],
        primary_observations=record['observed']['primary_observations']), ensure_ascii=False))
