"""Add bounded terrain observations without changing search or control decisions."""
import hashlib
import json
from mod_installation import ROOT, MANIFEST, assert_closed, validate_package, digest
from build_yanqiansui_search_candidate import expected as search_expected, verify as search_verify

WRAPPER = 'PBZBossControl/Scripts/yanqiansui_arena_clearance.lua'
CORE = 'PBZBossControl/Scripts/yanqiansui_clearance_core.lua'
SOURCES = ('tools/build_yanqiansui_terrain_candidate.py', 'tools/yanqiansui_terrain_trace.lua',
           'tools/yanqiansui_terrain_acceptance.py', 'tests/test_yanqiansui_terrain_trace.lua',
           'tests/test_yanqiansui_terrain_candidate.py')


def expected(root=ROOT):
    base = root / 'runtime/release-candidates' / search_expected(root)[-1]
    manifest = search_verify(base, root)
    contents = {n: (base / n).read_bytes() for n in manifest['files']}
    contents[CORE] = contents[WRAPPER]
    contents[WRAPPER] = (root / 'tools/yanqiansui_terrain_trace.lua').read_bytes()
    hashes = {n: hashlib.sha256(v).hexdigest() for n, v in contents.items()}
    assert {n for n in manifest['files'] if hashes[n] != manifest['files'][n]} == {WRAPPER}
    assert set(hashes) - set(manifest['files']) == {CORE}
    sources = {n: digest(root / n) for n in SOURCES}
    key = hashlib.sha256(json.dumps({'files': hashes, 'sources': sources}, sort_keys=True).encode()).hexdigest()[:16]
    return manifest, contents, hashes, sources, 'ahua-boss-workbench-terrain-' + key


def verify(target, root=ROOT):
    base, _, hashes, sources, identifier = expected(root)
    manifest = validate_package(target)
    assert target.name == identifier and manifest['files'] == hashes
    assert manifest['terrain_trace_sources'] == sources
    assert manifest['terrain_trace_base'] == base['release_id']
    return manifest


def build(root=ROOT):
    assert_closed(root)
    manifest, contents, hashes, sources, identifier = expected(root)
    target = root / 'runtime/release-candidates' / identifier
    if not target.exists():
        target.mkdir(parents=True)
        for n, data in contents.items():
            path = target / n
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        manifest.update(release_id=identifier, files=hashes, terrain_trace_sources=sources,
            terrain_trace_base=manifest['release_id'], terrain_search_decisions_unchanged=True,
            terrain_trace_queries_max=192, status='acceptance-candidate', complete_mod=False,
            runtime_acceptance_current=False)
        (target / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    verify(target, root)
    return target


if __name__ == '__main__':
    print(json.dumps({'candidate': str(build()), 'game_started': False, 'complete_mod': False}, ensure_ascii=False))
