"""Compose accepted native Boss profiles with the exact verified experience payload."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from boss_adaptation_workflow import ROOT, sha, write_json
from build_boss_profile_candidate import lua
import build_expanded_boss_profile as profiles
import build_player_experience_candidate as experience
from mod_installation import MANIFEST, assert_closed, unlinked_path, validate_package

BASE = 'ahua-player-experience-dev-e552ef2f8fdf70c0'
EXPERIENCE = 'evidence/releases/player-experience-accepted-4f55cc32aafa3051.json'
SOURCES = ('tools/build_expanded_boss_candidate.py', 'tests/test_expanded_boss_integration.py',
           *profiles.SOURCES)
PREFIX = 'PBZBossControl/Scripts/'


def overlay(files, additions):
    files = dict(files)
    catalog = files[PREFIX + 'boss_catalog.lua'].decode('utf-8').replace('\r\n', '\n')
    anchor = '}\nlocal bindings = {'
    assert catalog.count(anchor) == 1 and additions
    seen = set(re.findall(r"id='([^']+)'", catalog[:catalog.index(anchor)]))
    entries = []
    for manifest, payload in additions:
        identifier = manifest['id']
        assert identifier in profiles.NAMES and identifier not in seen
        assert manifest['base_control_accepted'] is True and manifest['playable'] is False
        assert manifest['ordinary_switching_accepted'] is False
        assert manifest['player_registry_modified'] is False
        seen.add(identifier)
        count = len(manifest['accepted_skills'])
        assert 1 <= count <= 4 and 'skill_01' in manifest['accepted_skills']
        entries.append('    ' + lua(dict(id=identifier, name=manifest['display_name'],
            profile=manifest['profile_module'], bindings=manifest['bindings_module'],
            abilities=count, bindings_count=count)) + ',\n')
        for name, text in payload.items():
            assert name in (profiles.NAMES[identifier] + '.lua', profiles.NAMES[identifier] + '_bindings.lua')
            path = PREFIX + 'profiles/' + name
            assert path not in files, 'Never overwrite an existing native profile'
            files[path] = text.encode('utf-8')
    files[PREFIX + 'boss_catalog.lua'] = catalog.replace(anchor, ''.join(entries) + anchor).encode('utf-8')
    return files


def expected(sessions, root=ROOT):
    assert sessions and len(sessions) <= 3
    assert len({row[1] for row in sessions}) == len(sessions)
    base = root / 'runtime/release-candidates' / BASE
    old = experience.verify(base, root)
    proof = json.loads((root / EXPERIENCE).read_bytes())
    assert proof['passed'] is True and proof['experience_runtime_verified'] is True
    assert proof['candidate_manifest_sha256'] == sha(base / MANIFEST)
    assert proof['world_reload_verified'] and proof['focus_idle_roundtrip_verified']
    for group in ('receipts', 'sources'):
        for name, digest in proof[group].items():
            profiles.checked(root, name, digest)
    additions = []; lineage = []
    for session, identifier in sessions:
        assert re.fullmatch(r'\d{8}-\d{6}', session)
        manifest, payload, _ = profiles.expected(session, identifier, root)
        additions.append((manifest, payload))
        lineage.append(dict(session=session, id=identifier, evidence=manifest['evidence'],
            evidence_sha256=manifest['evidence_sha256'], skills=manifest['accepted_skills'],
            display_name=manifest['display_name'], skill_labels=manifest['skill_labels'],
            profile_files=manifest['files']))
    files = overlay({name: (base / name).read_bytes() for name in old['files']}, additions)
    files['PBZBossControl/README.md'] += ('\n扩展开发候选：新增角色已完成独立原生技能验证；'
        '普通工作台切换、组合输入和跨World仍需该包集中验证。尚未安装。\n').encode('utf-8')
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}
    sources = {name: sha(root / name) for name in SOURCES}
    fingerprint = hashlib.sha256(json.dumps(dict(files=hashes, sources=sources, profiles=lineage),
                                           sort_keys=True).encode()).hexdigest()[:16]
    count = sum(len(row['skills']) for row in lineage)
    manifest = dict(old, release_id='ahua-expanded-boss-dev-' + fingerprint,
        status='acceptance-candidate', complete_mod=False, runtime_acceptance_current=False,
        integration_only=True, files=hashes, ability_count=old['ability_count'] + count,
        skill_binding_count=old['skill_binding_count'] + count,
        bosses=[*old['bosses'], *(dict(id=m['id'], name=m['display_name'],
            abilities=len(m['accepted_skills']), bindings=len(m['accepted_skills'])) for m, _ in additions)],
        expansion_base=BASE, expansion_base_manifest_sha256=sha(base / MANIFEST),
        experience_acceptance=EXPERIENCE, experience_acceptance_sha256=sha(root / EXPERIENCE),
        expansion_profiles=lineage, expansion_sources=sources,
        pending=['ordinary selection, shifted movement casting and cancellation for every added profile',
                 'new-profile native World lifecycle and input restoration'])
    return manifest, files


def verify(directory, root=ROOT):
    directory = unlinked_path(directory)
    assert directory.parent == (root / 'runtime/release-candidates').resolve()
    recorded = validate_package(directory)
    sessions = [(row['session'], row['id']) for row in recorded['expansion_profiles']]
    manifest, files = expected(sessions, root)
    assert directory.name == manifest['release_id'] and recorded == manifest
    assert all((directory / name).read_bytes() == data for name, data in files.items())
    return manifest


def build(sessions, root=ROOT):
    assert_closed(root)
    manifest, files = expected(sessions, root)
    target = root / 'runtime/release-candidates' / manifest['release_id']
    if not target.exists():
        target.mkdir(parents=True)
        for name, data in files.items():
            path = target / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        write_json(target / MANIFEST, manifest)
    verify(target, root)
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--boss', action='append', required=True, metavar='SESSION:ID')
    args = parser.parse_args()
    print(json.dumps(dict(candidate=str(build([tuple(row.split(':')) for row in args.boss])),
                         installed=False, runtime_acceptance_current=False), ensure_ascii=False))
