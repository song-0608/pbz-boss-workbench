"""Generate a protected, input-free staging workflow for the inventoried moves."""

import argparse
import ast
import hashlib
import json
from pathlib import Path

from boss_adaptation_workflow import ROOT, sha, write_json
from build_player_experience_candidate import replace
import boss_inventory_bundle as bundle
from mod_installation import unlinked_path
import native_grant_ui_stage as previous


def render(root=ROOT):
    files = previous.render(root)
    runner = files['stage_candidate.py'].decode()
    runner = replace(runner, 'import native_grant_ui_stage as controller', 'import inventory_ui_controller as controller')
    runner = replace(runner, repr(('071_xianzhe', '067_motian')), repr(bundle.candidate_ids(root)))
    gate = files['boss_candidate_gate.py'].decode().replace('native_grant_developer_bundle', 'boss_inventory_bundle')
    gate = replace(gate, 'import REVIEWS,validate as verify', 'import candidate_ids,validate as verify')
    gate = replace(gate, 'identifier not in REVIEWS', 'identifier not in candidate_ids(root)')
    controller = (root / 'tools/native_grant_ui_stage.py').read_text(encoding='utf-8')
    controller = replace(controller, 'import native_grant_developer_bundle as bundle', 'import boss_inventory_bundle as bundle')
    controller = replace(controller, 'import native_grant_developer_workflow as previous',
                         'import prepare_boss_inventory_workflow as previous')
    controller = replace(controller, "LABEL = 'native-grant-ui-stage'", "LABEL = 'inventory-skill-ui-stage'")
    controller = replace(controller, "kind='native_grant_ui_stage'", "kind='inventory_skill_ui_stage'")
    controller = replace(controller, "'native-grant-ui-' + parent['id']", "'inventory-skill-ui-' + parent['id']")
    controller = replace(controller, 'files = render(root)\n    manifest', 'files = previous.render(root)\n    manifest')
    controller = replace(controller,
        "    expected_modules = {p.removeprefix('Scripts/'): h for p, h in recorded['base_mod_files'].items()\n"
        "                        if p.startswith('Scripts/') and p != 'Scripts/main.lua'}\n"
        "    expected_modules['boss_candidate.lua'] = recorded['overrides']['Scripts/boss_candidate.lua']",
        "    expected_modules = previous.expected_modules(recorded)")
    controller = replace(controller, "    result = dict(id=manifest['id'], state_file=state['state_file'],\n",
        "    from prepare_boss_variant_candidates import captured_grants\n"
        "    definition = bundle.read(Path(manifest['bundle']) / 'manifest.json')['definition']\n"
        "    native_grants = captured_grants(tail, definition, rows)\n"
        "    result = dict(id=manifest['id'], state_file=state['state_file'],\n")
    controller = replace(controller,
        "        missing_native_grants=[p for p in allowed if p not in {r['class_path'] for r in rows}],",
        "        **native_grants,")
    validator = (root / 'tools/native_grant_skill_gate.py').read_text(encoding='utf-8')
    validator = replace(validator, 'import native_grant_ui_stage as flow', 'import inventory_ui_controller as flow')
    add_tools = 'import sys\nsys.dont_write_bytecode = True\nsys.path.append(' + repr(str(root / 'tools')) + ')\nimport argparse'
    controller = replace(controller, 'import argparse', add_tools)
    validator = replace(validator, 'import argparse', add_tools)
    result = dict(stage_candidate=runner, boss_candidate_gate=gate, inventory_ui_controller=controller,
                  inventory_skill_gate=validator)
    for name, source in result.items():
        ast.parse(source, filename=name + '.py')
    return {name + '.py': source.encode('utf-8') for name, source in result.items()}


def expected_modules(record, root=ROOT):
    release = root / 'releases/ahua-boss-workbench-v5-3f29975fe3b8826f' / 'pbz-release.json'
    files = bundle.read(release)['files']
    prefix = 'PBZBossControl/Scripts/'
    modules = {name.removeprefix(prefix): digest for name, digest in files.items()
               if name.startswith(prefix) and name.endswith('.lua') and name != prefix + 'main.lua'}
    modules['boss_candidate.lua'] = record['module_sha256']
    return modules


def expected(path, root=ROOT):
    identifier = bundle.read(path / 'manifest.json')['definition']['id']
    grant = bundle.validate(identifier, path, root=root)
    return dict(id=identifier, candidate_grant=grant, generator_sha256=sha(root / 'tools/prepare_boss_inventory_workflow.py'),
                validator_sha256=sha(root / 'tools/boss_inventory_bundle.py')), None, None


def build(path, root=ROOT):
    path = unlinked_path(path)
    parent, _, _ = expected(path, root)
    files = render(root)
    sources = {name: sha(root / name) for name in previous.SOURCES}
    record = dict(schema=1, kind='inventory_skill_ui_stage', id=parent['id'], bundle=str(path),
                  bundle_manifest_sha256=sha(path / 'manifest.json'), parent_workflow_manifest=parent,
                  source_files=sources, files={name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()},
                  developer_only=True, playable=False, game_started=False, ui_input_sent=False)
    fingerprint = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()[:16]
    target = root / 'runtime/developer-workflows' / ('inventory-skill-ui-' + parent['id'] + '-' + fingerprint)
    if not target.exists():
        target.mkdir(parents=True)
        for name, raw in files.items():
            (target / name).write_bytes(raw)
        write_json(target / 'manifest.json', record)
    assert bundle.read(target / 'manifest.json') == record
    assert all((target / name).read_bytes() == raw for name, raw in files.items())
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pool', type=Path)
    args = parser.parse_args()
    print(build(args.pool))
