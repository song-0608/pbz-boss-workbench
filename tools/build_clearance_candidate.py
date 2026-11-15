"""Apply initialization-only YanQianSui terrain clearance to a separate immutable candidate."""
import hashlib
import json
from pathlib import Path

from mod_installation import ROOT, MANIFEST, assert_closed, digest, validate_package

BASE = 'ahua-boss-workbench-v2-dev-fc170a5ecd820768'
SOURCES = ('tools/build_clearance_candidate.py','tools/yanqiansui_arena_clearance.lua',
           'tests/test_yanqiansui_clearance.lua')


def patched(original):
    anchor="            layout,reason=require('arena_layout').choose(projected,location,forward,"
    assert original.count(anchor)==1
    result=original.replace(anchor,"            local layout_module=assembly_profile.id=='073_yanqiansui' and 'yanqiansui_arena_clearance' or 'arena_layout'\n"
        "            layout,reason=require(layout_module).choose(projected,location,forward,")
    anchor='            current_layout_key=layout.key'
    assert result.count(anchor)==1
    return result.replace(anchor,"            if assembly_profile.id=='073_yanqiansui' then\n"
        "                assert(layout.clearance_cm==900 and layout.clearance_samples==24 and layout.queries_used<=192,'verified movement clearance required')\n"
        "                log('NAVIGATION_CLEARANCE_VERIFIED','radius=900|samples=24|queries='..layout.queries_used)\n"
        "            end\n"+anchor)


def build(root=ROOT):
    assert_closed(root)
    base=root/'runtime/release-candidates'/BASE
    manifest=validate_package(base)
    contents={name:(base/name).read_bytes() for name in manifest['files']}
    arena='PBZBossControl/Scripts/owned_arena.lua'
    contents[arena]=patched(contents[arena].decode('utf-8')).encode('utf-8')
    name='PBZBossControl/Scripts/yanqiansui_arena_clearance.lua'
    contents[name]=(root/'tools/yanqiansui_arena_clearance.lua').read_bytes()
    contents['PBZBossControl/README.md']+=('\n烟千岁装配前增加900厘米同层导航净空采样；仅初始化时执行，最多192次查询，空间不足拒绝生成。'
        '此检查不能保证任意技能轨迹安全，仍须实机验收，不修改地形、原生位移或碰撞。\n').encode('utf-8')
    files={n:hashlib.sha256(v).hexdigest() for n,v in sorted(contents.items())}
    fingerprint=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
    release_id='ahua-boss-workbench-v2-dev-'+fingerprint[:16]
    target=root/'runtime/release-candidates'/release_id
    if target.exists():
        assert validate_package(target)['files']==files
        return target
    target.mkdir(parents=True)
    for n,v in contents.items():
        path=target/n;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(v)
    manifest.update(release_id=release_id,files=files,terrain_clearance_cm=900,
        terrain_clearance_queries_max=192,terrain_clearance_initialization_only=True,
        previous_integration_candidate=BASE,previous_manifest_sha256=digest(base/MANIFEST),
        terrain_fix_sources={n:digest(root/n) for n in SOURCES})
    (target/MANIFEST).write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    validate_package(target)
    return target


if __name__=='__main__':
    print(json.dumps({'candidate':str(build()),'complete_mod':False,'installed':False},ensure_ascii=False))
