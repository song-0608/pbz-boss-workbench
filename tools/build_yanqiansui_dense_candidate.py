"""Replace only the unaccepted terrain search in an immutable candidate."""
import hashlib
import json
from mod_installation import ROOT, MANIFEST, assert_closed, validate_package, digest
from build_yanqiansui_terrain_candidate import expected as base_expected, verify as base_verify, CORE

SOURCES=('tools/build_yanqiansui_dense_candidate.py','tools/yanqiansui_clearance_dense.lua',
         'tools/yanqiansui_dense_acceptance.py','tests/test_yanqiansui_clearance_dense.lua',
         'tests/test_yanqiansui_dense_candidate.py')


def expected(root=ROOT):
    base=root/'runtime/release-candidates'/base_expected(root)[-1]
    manifest=base_verify(base,root)
    contents={n:(base/n).read_bytes()for n in manifest['files']}
    contents[CORE]=(root/'tools/yanqiansui_clearance_dense.lua').read_bytes()
    hashes={n:hashlib.sha256(v).hexdigest()for n,v in contents.items()}
    assert {n for n in hashes if hashes[n]!=manifest['files'][n]}=={CORE}
    sources={n:digest(root/n)for n in SOURCES}
    key=hashlib.sha256(json.dumps({'files':hashes,'sources':sources},sort_keys=True).encode()).hexdigest()[:16]
    return manifest,contents,hashes,sources,'ahua-boss-workbench-dense-'+key


def verify(target,root=ROOT):
    base,_,hashes,sources,identifier=expected(root)
    manifest=validate_package(target)
    assert target.name==identifier and manifest['files']==hashes
    assert manifest['dense_search_sources']==sources and manifest['dense_search_base']==base['release_id']
    return manifest


def build(root=ROOT):
    assert_closed(root)
    manifest,contents,hashes,sources,identifier=expected(root)
    target=root/'runtime/release-candidates'/identifier
    if not target.exists():
        target.mkdir(parents=True)
        for n,data in contents.items():
            path=target/n;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        manifest.update(release_id=identifier,files=hashes,dense_search_sources=sources,
            dense_search_base=manifest['release_id'],search_radius_max_cm=2400,
            terrain_search_decisions_unchanged=False,status='acceptance-candidate',complete_mod=False,
            runtime_acceptance_current=False)
        (target/MANIFEST).write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    verify(target,root)
    return target


if __name__=='__main__':
    print(json.dumps({'candidate':str(build()),'game_started':False,'complete_mod':False},ensure_ascii=False))
