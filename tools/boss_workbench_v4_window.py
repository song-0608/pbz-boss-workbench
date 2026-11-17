"""Player launcher for the independently accepted 52-ability workbench."""
import hashlib
import json
from pathlib import Path
import sys
import types
import boss_workbench_v3_window as previous
from mod_installation import installed_package

ROOT=Path(__file__).resolve().parents[1]
EXTRA={
    '057_wanjun':('万钧右侧攻击','万钧中段攻击01','万钧轻击01','万钧后撤攻击'),
    '073_yanqiansui':('烟千岁技能05','烟千岁技能06','烟千岁前闪攻击01','烟千岁后撤攻击01'),
    '056_youlong':('游龙中段攻击02','游龙重击02','游龙前闪','游龙后闪')}


def render():
    source=previous.render()
    changes=(('Boss 工作台 v3 · 四角色离线操控','Boss 工作台 v4 · 四角色技能扩展'),
        ('Boss 工作台 v3：阿花 · 万钧 · 烟千岁 · 游龙','Boss 工作台 v4：四角色 · 52项能力'),
        ('70-四Boss工作台v3操作说明.md','72-四Boss技能扩展v4操作说明.md'),
        ("if selected=='057_wanjun'and group=='skills'else player_settings.DESCRIPTIONS[action]",
         "if selected!='ahua_guitoudao'and group=='skills'else player_settings.DESCRIPTIONS[action]"),
        ('万钧开放四项独立能力。其余角色键位保留，保存仍检查整张按键表的冲突。',
         '万钧开放八项独立能力；烟千岁和游龙在游戏内选择。保存检查全部键位冲突。'))
    for before,after in changes:
        assert source.count(before)==1,before
        source=source.replace(before,after)
    return source


def check_installed():
    receipt,manifest,_=installed_package()
    assert receipt['enabled'] and manifest['status']=='release'
    assert manifest['complete_mod'] and manifest['runtime_acceptance_current']
    assert manifest['release_id'].startswith('ahua-boss-workbench-v4-')
    assert manifest['ability_count']==52 and manifest['skill_binding_count']==53
    assert [r['id'] for r in manifest['bosses']]==previous.IDS and manifest['locked_previews']==[]
    return manifest


def main(smoke=False):
    if not smoke:check_installed()
    import player_settings as settings
    original_bosses,original_read,original_labels=settings.BOSSES,settings.read,settings.editor_skill_labels
    data=json.loads((ROOT/'玩家设置.json').read_text(encoding='utf-8-sig'))
    normalized,changed=previous.previous.startup_settings(data)
    if changed and not smoke:settings.save(ROOT/'玩家设置.json',normalized)
    def labels(identifier):
        base=original_labels(identifier)
        if identifier in EXTRA:
            base.update(dict(zip(('skill_06','skill_08','skill_07','teleport_left'),EXTRA[identifier])))
        return base
    settings.BOSSES=dict(previous.previous.STARTUP_BOSSES);settings.editor_skill_labels=labels
    if smoke:settings.read=lambda:dict(normalized)
    try:
        module=types.ModuleType('boss_workbench_v4_gui');module.__file__=str(ROOT/'tools/ahua_practice_window.py')
        exec(compile(render(),module.__file__,'exec'),module.__dict__);module.main(smoke=smoke)
    finally:
        settings.BOSSES,settings.read,settings.editor_skill_labels=original_bosses,original_read,original_labels


if __name__=='__main__':main('--smoke' in sys.argv)
