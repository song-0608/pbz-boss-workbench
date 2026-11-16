"""Keep 9m clearance; use the projected Boss floor for additional targets."""
import hashlib
import json
from mod_installation import ROOT, MANIFEST, assert_closed, validate_package, digest
from build_yanqiansui_dense_candidate import expected as base_expected, verify as base_verify
from build_yanqiansui_terrain_candidate import CORE

SOURCES = ('tools/build_yanqiansui_centered_candidate.py', 'tools/yanqiansui_centered_acceptance.py',
           'tests/test_yanqiansui_clearance_centered.lua', 'tests/test_yanqiansui_centered_candidate.py')
PATCHES = (
    ('local rows,accepted={},true', 'local rows,accepted={},true\n                local projected_floor'),
    ('Y=origin.Y+y*offset[1]+x*offset[2],Z=floor}',
     'Y=origin.Y+y*offset[1]+x*offset[2],Z=index==1 and floor or projected_floor}'),
    ('math.abs(p.Z-floor)>30 then accepted=false;break end\n                    rows[index]',
     'math.abs(p.Z-(index==1 and floor or projected_floor))>(index==1 and 100 or 30) then accepted=false;break end\n'
     '                    if index==1 then projected_floor=p.Z end\n                    rows[index]'),
)


def patched(data):
    source = data.decode('utf-8')
    for before, after in PATCHES:
        assert source.count(before) == 1, before
        source = source.replace(before, after)
    return source.encode('utf-8')


def expected(root=ROOT):
    base = root / 'runtime/release-candidates' / base_expected(root)[-1]
    manifest = base_verify(base, root)
    contents = {n: (base / n).read_bytes() for n in manifest['files']}
    contents[CORE] = patched(contents[CORE])
    hashes = {n: hashlib.sha256(v).hexdigest() for n, v in contents.items()}
    assert {n for n in hashes if hashes[n] != manifest['files'][n]} == {CORE}
    sources = {n: digest(root / n) for n in SOURCES}
    key = hashlib.sha256(json.dumps({'files': hashes, 'sources': sources}, sort_keys=True).encode()).hexdigest()[:16]
    return manifest, contents, hashes, sources, 'ahua-boss-workbench-centered-' + key


def verify(target, root=ROOT):
    base, _, hashes, sources, identifier = expected(root)
    manifest = validate_package(target)
    assert target.name == identifier and manifest['files'] == hashes
    assert manifest['centered_search_sources'] == sources and manifest['centered_search_base'] == base['release_id']
    assert manifest['terrain_clearance_cm'] == 900 and manifest['terrain_clearance_queries_max'] == 192
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
        manifest.update(release_id=identifier, files=hashes, centered_search_sources=sources,
                        centered_search_base=manifest['release_id'], center_floor_offset_limit_cm=100,
                        target_and_footprint_floor_tolerance_cm=30, status='acceptance-candidate',
                        complete_mod=False, runtime_acceptance_current=False)
        (target / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    verify(target, root)
    return target


if __name__ == '__main__':
    print(json.dumps({'candidate': str(build()), 'game_started': False, 'complete_mod': False}, ensure_ascii=False))
