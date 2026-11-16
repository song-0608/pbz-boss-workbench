"""Extend only initialization terrain search in a separate immutable candidate."""
import hashlib
import json
from mod_installation import ROOT, MANIFEST, assert_closed, validate_package, digest

BASE='ahua-boss-workbench-v2-dev-c5149d9c33223138'
BASE_SHA='7c581fe517e7c73dd7d4132ab5e32884b997e385bc7cca77fa7cc39d49314a52'
MODULE='PBZBossControl/Scripts/yanqiansui_arena_clearance.lua'
SOURCES=('tools/build_yanqiansui_search_candidate.py','tools/yanqiansui_clearance_search.lua',
         'tests/test_yanqiansui_clearance_search.lua')


def expected(root=ROOT):
    base=root/'runtime/release-candidates'/BASE
    manifest=validate_package(base)
    assert digest(base/MANIFEST)==BASE_SHA
    files={n:(base/n).read_bytes()for n in manifest['files']}
    files[MODULE]=(root/'tools/yanqiansui_clearance_search.lua').read_bytes()
    hashes={n:hashlib.sha256(b).hexdigest()for n,b in files.items()}
    assert {n for n,d in hashes.items()if manifest['files'][n]!=d}=={MODULE}
    sources={n:digest(root/n)for n in SOURCES}
    fingerprint=hashlib.sha256(json.dumps({'files':hashes,'sources':sources},sort_keys=True).encode()).hexdigest()[:16]
    return manifest,files,hashes,sources,'ahua-boss-workbench-v2-search-'+fingerprint


def verify(target,root=ROOT):
    old,files,hashes,sources,identifier=expected(root)
    manifest=validate_package(target)
    assert target.name==identifier and manifest['files']==hashes
    assert manifest['search_sources']==sources and manifest['search_base_candidate']==BASE
    assert manifest['search_base_manifest_sha256']==BASE_SHA
    return manifest


def build(root=ROOT):
    assert_closed(root)
    manifest,files,hashes,sources,identifier=expected(root)
    target=root/'runtime/release-candidates'/identifier
    if not target.exists():
        target.mkdir(parents=True)
        for n,b in files.items():
            p=target/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
        manifest.update(release_id=identifier,files=hashes,search_sources=sources,
            search_base_candidate=BASE,search_base_manifest_sha256=BASE_SHA,
            search_radius_max_cm=1800,terrain_clearance_queries_max=192,
            pending=['YanQianSui ordinary movement/camera, roundtrip and native-menu World cycle'])
        (target/MANIFEST).write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    verify(target,root)
    return target


if __name__=='__main__':
    print(json.dumps({'candidate':str(build()),'game_started':False,'complete_mod':False},ensure_ascii=False))
