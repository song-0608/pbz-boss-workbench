"""Freeze a separate, exact developer workflow for the travel repair candidate."""
import ast
import hashlib
import json
from pathlib import Path

from boss_adaptation_workflow import ROOT, sha, write_json
from build_player_experience_candidate import replace
import build_player_travel_candidate as candidate
import published_boss_workflow as published
from mod_installation import MANIFEST, unlinked_path


def candidate_mod_root(directory):
    directory = unlinked_path(directory)
    candidate.verify(directory)
    return directory / 'PBZBossControl'


def expected(directory):
    manifest = candidate.verify(directory)
    files = published.render(directory, manifest)
    name = 'run_control_lifecycle_probe.py'
    files[name] = replace(files[name].decode('utf-8'),
        'from published_boss_workflow import installed_mod_root as candidate_mod_root',
        'from player_travel_workflow import candidate_mod_root').encode('utf-8')
    source = files[name].decode('utf-8')
    source = replace(source, 'import research_game_menu as menu\n', '')
    source = replace(source,
        "    menu.click(0,0,2560,1600,'control_reload')\n"
        "    print('Bounded lifecycle experiment hot reload requested in existing isolated game; no restart.')",
        "    print('Player candidate staged; use the separate fresh window reload gate.')")
    assert 'menu.click' not in source and 'research_game_menu' not in source
    source = replace(source, "        remote_binding={'binding_verified':True}",
        "        remote_binding={'binding_verified':True}\n"
        "        if args.player_entry:\n"
        "            from player_3c_contract import collect as collect_3c\n"
        "            remote_binding.update(collect_3c(work,contract['pid']))")
    source = replace(source, "    if remote_binding:prefix+='local experiment_remote_binding={binding_verified=true}\\n'",
        "    if remote_binding:prefix+='local experiment_remote_binding={binding_verified=true,locomotion_verified=' + ('true' if remote_binding.get('locomotion_verified') else 'false') + '}\\n'")
    files[name] = source.encode('utf-8')
    for name, data in files.items():
        ast.parse(data.decode('utf-8'), filename=name)
    record = dict(schema=1, candidate=str(directory), candidate_manifest_sha256=sha(directory / MANIFEST),
        files={name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
        sources={name: sha(ROOT / name) for name in ('tools/player_travel_workflow.py', 'tools/player_3c_contract.py')},
        developer_only=True, installed=False, runtime_verified=False)
    key = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()[:16]
    return record, files, 'travel-repair-' + key


def verify(directory):
    directory = unlinked_path(directory)
    recorded = json.loads((directory / 'manifest.json').read_bytes())
    expected_record, files, name = expected(Path(recorded['candidate']))
    assert directory.parent == (ROOT / 'runtime/integration-workflows').resolve()
    assert directory.name == name and recorded == expected_record
    assert {p.name for p in directory.iterdir()} == set(files) | {'manifest.json'}
    assert all((directory / name).read_bytes() == data for name, data in files.items())
    return recorded


def build(package):
    record, files, name = expected(package)
    directory = ROOT / 'runtime/integration-workflows' / name
    if not directory.exists():
        directory.mkdir(parents=True)
        for name, data in files.items():
            (directory / name).write_bytes(data)
        write_json(directory / 'manifest.json', record)
    verify(directory)
    return directory


if __name__ == '__main__':
    print(json.dumps(dict(workflow=str(build(candidate.build())), installed=False), ensure_ascii=False))
