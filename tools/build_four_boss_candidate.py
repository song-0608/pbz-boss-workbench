"""Build a separate four-Boss integration package only after independent YouLong control passes."""
import argparse
import hashlib
import json
from boss_adaptation_workflow import ROOT,sha
from mod_installation import MANIFEST,assert_closed,validate_package
from build_selection_candidate import build as selection_candidate
from build_youlong_profile import build as stage_profile


def build(session,root=ROOT):
    assert_closed(root);base=selection_candidate(root);manifest=validate_package(base)
    staged=stage_profile(session,root)
    staged_manifest=json.loads((staged/'profile-candidate.json').read_text(encoding='utf-8'))
    assert staged_manifest['base_control_accepted']and staged_manifest['playable']is False
    assert not staged_manifest['ordinary_switching_accepted']and not staged_manifest['player_registry_modified']
    for name,digest in staged_manifest['files'].items():assert sha(staged/name)==digest
    contents={n:(base/n).read_bytes()for n in manifest['files']}
    name='PBZBossControl/Scripts/boss_catalog.lua';source=contents[name].decode('utf-8')
    anchor="    {id='073_yanqiansui',name='琴女烟千岁',profile='profiles.yanqiansui',bindings='profiles.yanqiansui_bindings',abilities=4,bindings_count=4},"
    assert source.count(anchor)==1 and "id='056_youlong'"not in source
    contents[name]=source.replace(anchor,anchor+"\n    {id='056_youlong',name='发狂的水行帮主：游龙',profile='profiles.youlong',bindings='profiles.youlong_bindings',abilities=4,bindings_count=4},").encode('utf-8')
    for name in ('youlong.lua','youlong_bindings.lua'):
        contents['PBZBossControl/Scripts/profiles/'+name]=(staged/name).read_bytes()
    contents['PBZBossControl/README.md']+='\n四Boss开发集成候选：游龙四项独立原生动作完成基础验收；本包工作台切换、原生菜单跨World和净空拒绝体验仍待集中验收。此目录不是发布版。\n'.encode('utf-8')
    files={n:hashlib.sha256(v).hexdigest()for n,v in sorted(contents.items())}
    sources={n:sha(root/n)for n in ('tools/build_four_boss_candidate.py','tests/test_four_boss_candidate.lua')}
    fingerprint=hashlib.sha256(json.dumps({'files':files,'sources':sources},sort_keys=True).encode()).hexdigest()[:16]
    release_id='ahua-boss-workbench-v2-dev-'+fingerprint
    target=root/'runtime/release-candidates'/release_id
    if target.exists():
        existing=validate_package(target)
        assert existing['files']==files and existing['four_boss_sources']==sources
        return target
    target.mkdir(parents=True)
    for name,data in contents.items():
        path=target/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    manifest.update(release_id=release_id,status='acceptance-candidate',complete_mod=False,
        runtime_acceptance_current=False,files=files,ability_count=40,skill_binding_count=41,
        bosses=[*manifest['bosses'],{'id':'056_youlong','name':'发狂的水行帮主：游龙','abilities':4,'bindings':4}],
        youlong_profile_evidence=staged_manifest['evidence'],youlong_profile_evidence_sha256=staged_manifest['evidence_sha256'],
        youlong_attempt_receipt=staged_manifest['attempt_receipt'],youlong_attempt_receipt_sha256=staged_manifest['attempt_receipt_sha256'],
        previous_four_boss_candidate=base.name,previous_four_boss_manifest_sha256=sha(base/MANIFEST),four_boss_sources=sources,
        pending=['ordinary new-profile workbench switching','new-profile world lifecycle','live terrain preflight refusal and current-assembly recovery'])
    (target/MANIFEST).write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    validate_package(target)
    return target


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('session');args=parser.parse_args()
    print(json.dumps({'candidate':str(build(args.session)),'complete_mod':False,'installed':False},ensure_ascii=False))
