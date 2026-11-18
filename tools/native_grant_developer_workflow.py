"""Version the existing protected developer workflow for exact follow-up bundles."""
import argparse
import ast
import hashlib
import json
from pathlib import Path

from boss_adaptation_workflow import ROOT, sha, write_json
from build_player_experience_candidate import replace
from mod_installation import unlinked_path
import expanded_boss_developer_workflow as previous
import native_grant_developer_bundle as bundle

SOURCES = ('tools/native_grant_developer_workflow.py', 'tools/expanded_boss_developer_workflow.py',
           'tests/test_native_grant_developer.py')


def render(root=ROOT):
    files = previous.render(root)
    for name, data in list(files.items()):
        text = data.decode('utf-8')
        text = text.replace('expanded_boss_developer_bundle', 'native_grant_developer_bundle')
        if name in ('ahua_practice.py', 'run_control_lifecycle_probe.py'):
            text = replace(text,
                "choices=('071_xianzhe', '058_maddoctor', '067_motian')", 'choices=' + repr(tuple(bundle.REVIEWS)))
        ast.parse(text, filename=name)
        files[name] = text.encode('utf-8')
    return files


def expected(bundle_path, root=ROOT):
    identifier = bundle.read(bundle_path / 'manifest.json')['id']
    grant = bundle.validate(identifier, bundle_path, root=root)
    files = render(root)
    manifest = dict(schema=1, kind='native_grant_developer_workflow', id=identifier,
        bundle=str(bundle_path), bundle_manifest_sha256=sha(bundle_path / 'manifest.json'), candidate_grant=grant,
        source_files={n: sha(root / n) for n in SOURCES}, files={n: hashlib.sha256(v).hexdigest() for n, v in files.items()},
        developer_only=True, playable=False, game_started=False, runtime_acceptance_current=False)
    key = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()[:16]
    return manifest, files, 'native-grant-' + identifier + '-' + key


def build(bundle_path, root=ROOT):
    bundle_path = unlinked_path(bundle_path)
    manifest, files, name = expected(bundle_path, root)
    target = root / 'runtime/developer-workflows' / name
    if not target.exists():
        target.mkdir(parents=True)
        for name, data in files.items(): (target / name).write_bytes(data)
        write_json(target / 'manifest.json', manifest)
    verify(target, root)
    return target


def verify(target, root=ROOT):
    target = unlinked_path(target)
    assert target.parent == (root / 'runtime/developer-workflows').resolve()
    recorded = bundle.read(target / 'manifest.json')
    manifest, files, name = expected(Path(recorded['bundle']), root)
    assert target.name == name and recorded == manifest
    assert {p.name for p in target.iterdir()} == set(files) | {'manifest.json'}
    assert all(unlinked_path(target / n).read_bytes() == data for n, data in files.items())
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('bundle', type=Path)
    args = parser.parse_args()
    print(json.dumps(dict(workflow=str(build(args.bundle.resolve())), game_started=False, playable=False), ensure_ascii=False))
