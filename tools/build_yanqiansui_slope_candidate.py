"""Version the initialization search with a bounded gentle-plane verifier."""
import hashlib
import json
from mod_installation import ROOT, MANIFEST, assert_closed, validate_package, digest
from build_yanqiansui_centered_candidate import expected as base_expected, verify as base_verify
from build_yanqiansui_terrain_candidate import CORE

SOURCES = ('tools/build_yanqiansui_slope_candidate.py', 'tools/yanqiansui_clearance_slope.lua',
           'tools/yanqiansui_slope_acceptance.py', 'tests/test_yanqiansui_clearance_slope.lua',
           'tests/test_yanqiansui_slope_candidate.py')


def patched(data, plane):
    source = data.decode('utf-8')
    start = source.index('    local function clearance(plan)\n')
    end = source.index('    local initial=Base.choose(', start)
    replacement = ('    local Terrain=(function()\n' + plane.decode('utf-8') + '\nend)()\n'
                   '    local function clearance(plan)\n'
                   '        if not Terrain.verify(bounded,plan,boss_half,target_half,radius)then return nil end\n'
                   '        plan.clearance_cm=radius;plan.clearance_samples=24\n'
                   '        plan.queries_used=used;plan.queries_bound=limit\n'
                   '        return plan\n    end\n')
    return (source[:start] + replacement + source[end:]).encode('utf-8')


def expected(root=ROOT):
    base = root / 'runtime/release-candidates' / base_expected(root)[-1]
    manifest = base_verify(base, root)
    contents = {n: (base / n).read_bytes() for n in manifest['files']}
    contents[CORE] = patched(contents[CORE], (root / 'tools/yanqiansui_clearance_slope.lua').read_bytes())
    hashes = {n: hashlib.sha256(v).hexdigest() for n, v in contents.items()}
    assert {n for n in hashes if hashes[n] != manifest['files'][n]} == {CORE}
    sources = {n: digest(root / n) for n in SOURCES}
    key = hashlib.sha256(json.dumps({'files': hashes, 'sources': sources}, sort_keys=True).encode()).hexdigest()[:16]
    return manifest, contents, hashes, sources, 'ahua-boss-workbench-slope-' + key


def verify(target, root=ROOT):
    base, _, hashes, sources, identifier = expected(root)
    manifest = validate_package(target)
    assert target.name == identifier and manifest['files'] == hashes
    assert manifest['slope_search_sources'] == sources and manifest['slope_search_base'] == base['release_id']
    assert manifest['terrain_clearance_cm'] == 900 and manifest['terrain_clearance_queries_max'] == 192
    assert manifest['terrain_slope_limit_degrees'] == 5 and manifest['terrain_residual_limit_cm'] == 30
    return manifest


def build(root=ROOT):
    assert_closed(root)
    manifest, contents, hashes, sources, identifier = expected(root)
    target = root / 'runtime/release-candidates' / identifier
    if not target.exists():
        target.mkdir(parents=True)
        for n, data in contents.items():
            path = target / n;path.parent.mkdir(parents=True, exist_ok=True);path.write_bytes(data)
        manifest.update(release_id=identifier, files=hashes, slope_search_sources=sources,
                        slope_search_base=manifest['release_id'], terrain_slope_limit_degrees=5,
                        terrain_residual_limit_cm=30, terrain_footprint_height_limit_cm=100,
                        status='acceptance-candidate', complete_mod=False, runtime_acceptance_current=False)
        (target / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    verify(target, root)
    return target


if __name__ == '__main__':
    print(json.dumps({'candidate': str(build()), 'game_started': False, 'complete_mod': False}, ensure_ascii=False))
