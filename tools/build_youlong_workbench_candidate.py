"""Release only the three accepted profiles; keep YanQianSui as a locked preview."""
import hashlib
import json
from mod_installation import ROOT,MANIFEST,assert_closed,validate_package,digest

BASE='ahua-boss-workbench-v2-dev-c5149d9c33223138'
BASE_SHA='7c581fe517e7c73dd7d4132ab5e32884b997e385bc7cca77fa7cc39d49314a52'
SOURCES=('tools/build_youlong_workbench_candidate.py','tools/youlong_workbench_acceptance.py',
         'tools/test_youlong_workbench_world.py','tests/test_youlong_workbench_candidate.lua',
         'tests/test_youlong_workbench_acceptance.py')
REGISTRY='PBZBossControl/Scripts/boss_catalog.lua'
PREVIEW='PBZBossControl/Scripts/workbench_catalog.lua'
REMOVED="    {id='073_yanqiansui',name='琴女烟千岁',profile='profiles.yanqiansui',bindings='profiles.yanqiansui_bindings',abilities=4,bindings_count=4},\n"


def expected(root=ROOT):
    base=root/'runtime/release-candidates'/BASE;manifest=validate_package(base)
    assert digest(base/MANIFEST)==BASE_SHA
    contents={n:(base/n).read_bytes()for n in manifest['files']}
    original=contents[REGISTRY].decode('utf-8');assert original.count(REMOVED)==1
    contents[REGISTRY]=original.replace(REMOVED,'').encode('utf-8')
    old="reason='身份已核实，独立操控和技能验收尚未通过',"
    new="reason='烟千岁的地形、移动镜头及载图验收未完成，暂不开放',"
    original=contents[PREVIEW].decode('utf-8');assert original.count(old)==1
    contents[PREVIEW]=original.replace(old,new).encode('utf-8')
    contents['PBZBossControl/README.md']=('''# Boss 工作台 v2 候选

适用当前已核定构建的本机离线研究启动器。工作台开放新娘阿花（28能力/29绑定）、巨锤客万钧（4/4）和发狂的水行帮主游龙（4/4），合计36项独立能力、37个绑定。

Insert 打开工作台，↑↓选择，Enter确认，F6接管，F10恢复主角。游龙F1为中攻击01、F2为重攻击01、F3为左闪攻击、F4为右闪攻击。保留原生冷却和目标/地形限制；需等待装配及收招完成。

烟千岁仅锁定预览，普通目录不能装配。其独立基础与部分普通技能通过，但当前场地净空、移动镜头及载图集成尚未完成。

保留原生UObject缓存和增量状态读取。工作台为游戏画面上的Windows键盘浮层。仅写隔离研究副本，不写正式游戏或存档，不回档、不回写研究进度。

当前是否已正式发布须检查同目录pbz-release.json：status=release且runtime_acceptance_current=true时才是发布版；不能仅凭本说明认定验收完成。
''').encode('utf-8')
    hashes={n:hashlib.sha256(b).hexdigest()for n,b in sorted(contents.items())}
    assert {n for n,d in hashes.items()if d!=manifest['files'][n]}=={REGISTRY,PREVIEW,'PBZBossControl/README.md'}
    sources={n:digest(root/n)for n in SOURCES}
    identifier='ahua-boss-workbench-v2-three-'+hashlib.sha256(json.dumps({'files':hashes,'sources':sources},sort_keys=True).encode()).hexdigest()[:16]
    return manifest,contents,hashes,sources,identifier


def verify(target,root=ROOT):
    _,_,hashes,sources,identifier=expected(root);manifest=validate_package(target)
    assert target.name==identifier and manifest['files']==hashes and manifest['three_profile_sources']==sources
    assert manifest['three_profile_base']==BASE and manifest['three_profile_base_manifest_sha256']==BASE_SHA
    assert [b['id']for b in manifest['bosses']]==['ahua_guitoudao','057_wanjun','056_youlong']
    assert manifest['ability_count']==36 and manifest['skill_binding_count']==37
    return manifest


def build(root=ROOT):
    assert_closed(root);manifest,contents,hashes,sources,identifier=expected(root)
    target=root/'runtime/release-candidates'/identifier
    if not target.exists():
        target.mkdir(parents=True)
        for n,b in contents.items():
            p=target/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
        manifest.update(release_id=identifier,files=hashes,three_profile_sources=sources,
            three_profile_base=BASE,three_profile_base_manifest_sha256=BASE_SHA,
            bosses=[b for b in manifest['bosses']if b['id']!='073_yanqiansui'],ability_count=36,skill_binding_count=37,
            locked_previews=['073_yanqiansui'],pending=['exact three-profile menu and native World acceptance'])
        (target/MANIFEST).write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    verify(target,root);return target


if __name__=='__main__':
    print(json.dumps({'candidate':str(build()),'game_started':False,'complete_mod':False},ensure_ascii=False))
