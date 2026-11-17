"""Freeze ordinary player tools for a reviewed expansion without relaxing runtime gates."""
import argparse
import ast
import hashlib
import json
from pathlib import Path

from boss_adaptation_workflow import ROOT, sha, write_json
import player_experience_workflow as experience
import build_expanded_boss_candidate as candidate
from mod_installation import MANIFEST, unlinked_path

SOURCES = ('tools/expanded_boss_integration_workflow.py', 'tests/test_expanded_boss_integration.py',
           'tools/player_experience_trial.py', 'tools/test_player_experience_inputs.py')


def candidate_mod_root(directory):
    directory = unlinked_path(directory)
    candidate.verify(directory)
    return directory / 'PBZBossControl'


def render(directory, root=ROOT, additions=()):
    base = root / 'runtime/release-candidates' / candidate.BASE
    files = experience.render(base, root)
    name = 'run_control_lifecycle_probe.py'
    source = files[name].decode('utf-8')
    source = experience.candidate.replace(source,
        "from player_experience_workflow import candidate_mod_root\ndef active_mod_root():\n    return candidate_mod_root(Path(" + repr(str(base)) + '))',
        "from expanded_boss_integration_workflow import candidate_mod_root\ndef active_mod_root():\n    return candidate_mod_root(Path(" + repr(str(directory)) + '))')
    files[name] = source.encode('utf-8')
    source = files['player_settings.py'].decode('utf-8')
    labels = {row['id']: row['skill_labels'] for row in additions}
    names = {row['id']: row['display_name'] for row in additions}
    source = experience.candidate.replace(source,
        '    import player_keymap\n    return {slot:LABELS[slot]for slot in player_keymap.read()[\'skills\']}',
        '    extra_labels=' + repr(labels) + '\n'
        '    if boss_id in extra_labels:return dict(extra_labels[boss_id])\n'
        '    import player_keymap\n    return {slot:LABELS[slot]for slot in player_keymap.read()[\'skills\']}')
    source += '\n# Exact independently accepted profiles in this candidate only.\nBOSSES.update(' + repr(names) + ')\n'
    files['player_settings.py'] = source.encode('utf-8')
    header = 'import sys\nsys.dont_write_bytecode=True\nsys.path.append(' + repr(str(root / 'tools')) + ')\n'
    source = (root / 'tools/player_experience_trial.py').read_text(encoding='utf-8')
    source = experience.candidate.replace(source, 'import player_experience_workflow as workflow',
                                         'import expanded_boss_integration_workflow as workflow')
    source = experience.candidate.replace(source, 'import build_player_experience_candidate as candidate',
                                         'import build_expanded_boss_candidate as candidate')
    files['player_experience_trial.py'] = (header + source).encode('utf-8')
    files['test_player_experience_inputs.py'] = (header + (root / 'tools/test_player_experience_inputs.py').read_text(encoding='utf-8')).encode('utf-8')
    for name, data in files.items(): ast.parse(data.decode('utf-8'), filename=name)
    return files


def expected(directory, root=ROOT):
    package = candidate.verify(directory, root)
    files = render(directory, root, package['expansion_profiles'])
    manifest = dict(schema=1, candidate=str(directory), candidate_manifest_sha256=sha(directory / MANIFEST),
        sources={name: sha(root / name) for name in SOURCES},
        files={name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
        developer_only=True, installed=False, game_started=False, runtime_verified=False)
    key = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()[:16]
    return manifest, files, 'expanded-player-' + key


def verify(target, root=ROOT):
    target = unlinked_path(target)
    assert target.parent == (root / 'runtime/integration-workflows').resolve()
    recorded = json.loads((target / 'manifest.json').read_bytes())
    manifest, files, name = expected(Path(recorded['candidate']), root)
    assert target.name == name and recorded == manifest
    assert {p.name for p in target.iterdir()} == set(files) | {'manifest.json'}
    assert all((target / name).read_bytes() == data for name, data in files.items())
    return manifest


def build(directory, root=ROOT):
    manifest, files, name = expected(directory, root)
    target = root / 'runtime/integration-workflows' / name
    if not target.exists():
        target.mkdir(parents=True)
        for name, data in files.items(): (target / name).write_bytes(data)
        write_json(target / 'manifest.json', manifest)
    verify(target, root)
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('candidate', type=Path)
    args = parser.parse_args()
    print(json.dumps(dict(workflow=str(build(args.candidate.resolve())), installed=False, game_started=False), ensure_ascii=False))
