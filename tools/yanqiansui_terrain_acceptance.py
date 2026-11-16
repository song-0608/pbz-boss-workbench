"""Use the frozen integration gates with a decision-identical terrain trace."""
import argparse
import json
from pathlib import Path
from mod_installation import ROOT, MANIFEST, digest, validate_package
from four_boss_integration_workflow import modules, verify as verify_workflow
from build_yanqiansui_terrain_candidate import expected, verify as verify_candidate, WRAPPER, CORE
from yanqiansui_search_acceptance import verify_current as verify_search


def verify_current(current, root=ROOT):
    _, _, _, _, identifier = expected(root)
    candidate = root / 'runtime/release-candidates' / identifier
    manifest = verify_candidate(candidate, root)
    assert current == modules(manifest), 'Exact terrain trace deployment required'
    base_path = root / 'runtime/release-candidates' / manifest['terrain_trace_base']
    base = modules(validate_package(base_path))
    wrapper, core = (n.removeprefix('PBZBossControl/Scripts/') for n in (WRAPPER, CORE))
    assert {n for n in base if current.get(n) != base[n]} == {wrapper}
    assert set(current) - set(base) == {core} and current[core] == base[wrapper]
    previous, sources = verify_search(base, root)
    sources.update(manifest['terrain_trace_sources'])
    sources[(candidate / MANIFEST).relative_to(root).as_posix()] = digest(candidate / MANIFEST)
    return previous, sources


def run(workflow, finish=False):
    import test_four_boss_integration as frozen
    verify_workflow(workflow)
    frozen.verify_current = verify_current
    return frozen.main(workflow, '073_yanqiansui', finish_world=finish)


def collect(session, workflow):
    import collect_four_boss_integration as frozen
    verify_workflow(workflow)
    frozen.verify_current = verify_current
    return frozen.collect(session, workflow, '073_yanqiansui')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=('verify', 'run', 'finish-world', 'collect'))
    p.add_argument('--workflow', type=Path, required=True)
    p.add_argument('--session')
    a = p.parse_args()
    workflow = a.workflow.resolve()
    if a.action == 'verify':
        verify_workflow(workflow)
        target = ROOT / 'runtime/release-candidates' / expected()[-1]
        actions, _ = verify_current(modules(verify_candidate(target)))
        print(json.dumps({'passed': True, 'candidate': str(target), 'ordinary_actions_reparsed': len(actions),
                          'search_decisions_unchanged': True, 'game_started': False}))
    elif a.action == 'collect':
        assert a.session
        print(json.dumps(collect(a.session, workflow), ensure_ascii=False))
    else:
        raise SystemExit(run(workflow, a.action == 'finish-world'))
