"""Build a separate three-Boss integration candidate from the immutable v1 package."""
import hashlib
import json
from pathlib import Path

from build_yanqiansui_profile import build as build_profile
from mod_installation import ROOT, MANIFEST, digest, validate_package, installed_package, assert_closed

SESSION = '20261116-055334'


def payloads(base, staged):
    manifest = validate_package(base)
    assert manifest['status'] == 'release' and manifest['complete_mod'] is True
    assert manifest['release_id'] == 'ahua-boss-workbench-v1-f0bcf1323e641e03'
    result = {name: (base / name).read_bytes() for name in manifest['files']}
    catalog = 'PBZBossControl/Scripts/boss_catalog.lua'
    original = result[catalog].decode('utf-8')
    anchor = "    {id='057_wanjun',name='巨锤客：万钧',profile='profiles.wanjun',bindings='profiles.wanjun_bindings',abilities=4,bindings_count=4},"
    assert original.count(anchor) == 1 and "id='073_yanqiansui'" not in original
    result[catalog] = original.replace(anchor, anchor + "\n    {id='073_yanqiansui',name='琴女烟千岁',profile='profiles.yanqiansui',bindings='profiles.yanqiansui_bindings',abilities=4,bindings_count=4},").encode('utf-8')
    preview = 'PBZBossControl/Scripts/workbench_catalog.lua'
    original = result[preview].decode('utf-8')
    original = original.replace("name='056_YouLong'", "name='发狂的水行帮主：游龙'")
    old = "reason=entry.id=='056_youlong'and'类默认配置与候选配置不一致，保持锁定'or'身份已核实，独立操控和技能验收尚未通过'"
    assert original.count(old) == 1
    result[preview] = original.replace(old, "reason='身份已核实，独立操控和技能验收尚未通过'").encode('utf-8')
    for name in ('yanqiansui.lua', 'yanqiansui_bindings.lua'):
        result['PBZBossControl/Scripts/profiles/' + name] = (staged / name).read_bytes()
    result['PBZBossControl/README.md'] += ('\n\n三Boss开发集成候选：烟千岁四技能基础操控通过，工作台切换与World生命周期待本候选实测。'
        '游龙仅身份已核实，仍不可选。Insert打开工作台，方向键选择，Enter确认，F6接管，F10恢复。\n').encode('utf-8')
    changed = {name for name, content in result.items() if name not in manifest['files'] or digest(base / name) != hashlib.sha256(content).hexdigest()}
    assert changed == {catalog, preview, 'PBZBossControl/README.md',
        'PBZBossControl/Scripts/profiles/yanqiansui.lua', 'PBZBossControl/Scripts/profiles/yanqiansui_bindings.lua'}
    return manifest, result


def build(root=ROOT):
    assert_closed(root)
    _, base_manifest, base = installed_package(root)
    staged = build_profile(SESSION, root)
    accepted = json.loads((staged / 'profile-candidate.json').read_text(encoding='utf-8'))
    assert accepted['base_control_accepted'] is True and accepted['ordinary_switching_accepted'] is False
    assert accepted['playable'] is False and accepted['player_registry_modified'] is False
    for name, expected in accepted['files'].items():
        assert digest(staged / name) == expected
    manifest, contents = payloads(base, staged)
    files = {name: hashlib.sha256(content).hexdigest() for name, content in sorted(contents.items())}
    fingerprint = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    release_id = 'ahua-boss-workbench-v2-dev-' + fingerprint[:16]
    target = root / 'runtime/release-candidates' / release_id
    if target.exists():
        assert validate_package(target)['files'] == files
        return target
    target.mkdir(parents=True)
    for name, content in contents.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    result = dict(manifest, release_id=release_id, status='acceptance-candidate', complete_mod=False,
        runtime_acceptance_current=False, files=files, ability_count=36, skill_binding_count=37,
        inherited_release=base_manifest['release_id'], inherited_manifest_sha256=digest(base / MANIFEST),
        new_profile_evidence=accepted['evidence'], new_profile_evidence_sha256=accepted['evidence_sha256'],
        bosses=[*manifest['bosses'], {'id':'073_yanqiansui','name':'琴女烟千岁','abilities':4,'bindings':4}],
        pending=['ordinary new-profile workbench switching', 'new-profile world lifecycle'],
        integration_only=True)
    # A v1 report describes v1 only; never label this candidate with that acceptance report.
    for key in ('acceptance_report', 'acceptance_report_sha256', 'accepted_candidate'):
        result.pop(key, None)
    (target / MANIFEST).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    validate_package(target)
    return target


if __name__ == '__main__':
    print(json.dumps({'candidate': str(build()), 'complete_mod': False, 'installed': False}, ensure_ascii=False))
