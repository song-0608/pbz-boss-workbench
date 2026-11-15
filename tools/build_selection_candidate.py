"""Add terrain preflight before workbench unlock; preserve published and frozen sources."""
import hashlib
import json
from mod_installation import ROOT, MANIFEST, assert_closed, validate_package, digest

BASE='ahua-boss-workbench-v2-dev-8d16f4d84200822e'
SOURCES=('tools/build_selection_candidate.py','tools/boss_selection_preflight.lua',
         'tests/test_boss_selection_preflight.lua','tests/test_workbench_selection_preflight.lua',
         'tools/selection_skill_reuse.py','tests/test_selection_candidate.py')


def patch_workbench(source):
    anchor="    assert(self.adapter.unlock()==true,'workbench input restoration failed')\n    self.opened=false;self.busy=true;self:changed('正在安全切换角色…')"
    if anchor not in source:anchor=anchor.replace('\n','\r\n')
    assert source.count(anchor)==1
    return source.replace(anchor,"""    if self.adapter.check_selection then
        local ok,ready,reason=pcall(self.adapter.check_selection,entry.id)
        if not ok or ready~=true then
            self:changed(ok and (reason or '当前位置无法切换，请返回后重试') or '角色检查未完成，请返回后重试')
            return false,self.message
        end
    end
"""+anchor)


def patch_arena(source):
    anchor="                            select=function(id)\n                                guard();assert(session.state=='OFF'and not session.receipt,'restore before Boss switching')"
    if anchor not in source:anchor=anchor.replace('\n','\r\n')
    assert source.count(anchor)==1
    return source.replace(anchor,"""                            check_selection=function(id)
                                local grant=guard()
                                assert(session.state=='OFF'and not session.receipt,'restore before selection check')
                                local ready,reason=require('boss_selection_preflight').verify(
                                    _G,options.arena_binding,pc,player,id,valid,grant.exe_sha256)
                                if not ready then log('WORKBENCH_SELECTION_REJECTED',id..'|insufficient verified clearance')end
                                return ready,reason
                            end,
"""+anchor)


def build(root=ROOT):
    assert_closed(root)
    base=root/'runtime/release-candidates'/BASE
    manifest=validate_package(base)
    contents={n:(base/n).read_bytes()for n in manifest['files']}
    for name,patch in (('owned_arena.lua',patch_arena),('boss_workbench.lua',patch_workbench)):
        n='PBZBossControl/Scripts/'+name
        contents[n]=patch(contents[n].decode('utf-8')).encode('utf-8')
    contents['PBZBossControl/Scripts/boss_selection_preflight.lua']=(root/'tools/boss_selection_preflight.lua').read_bytes()
    contents['PBZBossControl/README.md']+='\n烟千岁工作台确认前先检查净空；空间不足保留当前装配和工作台，按Esc返回后可移动重选。生成时仍独立复查，不缓存地面通过结果。\n'.encode('utf-8')
    files={n:hashlib.sha256(v).hexdigest()for n,v in sorted(contents.items())}
    sources={n:digest(root/n)for n in SOURCES}
    fingerprint=hashlib.sha256(json.dumps({'files':files,'sources':sources},sort_keys=True).encode()).hexdigest()[:16]
    release_id='ahua-boss-workbench-v2-dev-'+fingerprint
    target=root/'runtime/release-candidates'/release_id
    if target.exists():
        existing=validate_package(target)
        assert existing['files']==files and existing['selection_fix_sources']==sources
        return target
    target.mkdir(parents=True)
    for name,data in contents.items():
        path=target/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    manifest.update(release_id=release_id,files=files,selection_preflight=True,
        selection_preflight_preserves_current_assembly=True,
        previous_selection_candidate=BASE,previous_selection_manifest_sha256=digest(base/MANIFEST),
        selection_fix_sources=sources)
    (target/MANIFEST).write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    validate_package(target)
    return target


if __name__=='__main__':
    print(json.dumps({'candidate':str(build()),'complete_mod':False,'installed':False},ensure_ascii=False))
