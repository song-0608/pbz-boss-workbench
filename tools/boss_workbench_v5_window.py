"""Player window for the accepted v5 payload, using the existing three-step launcher."""
import importlib.util
import json
from pathlib import Path
import sys
import types

import boss_workbench_v4_window as previous
from boss_adaptation_workflow import ROOT
from mod_installation import installed_package
import published_boss_workflow as published


def render(flow, count):
    source = previous.render()
    replacements = (
        ('Boss 工作台 v4 · 四角色技能扩展', 'Boss 工作台 v5 · 锁敌与角色扩展'),
        ('Boss 工作台 v4：四角色 · 52项能力', 'Boss 工作台 v5：' + str(count) + '角色 · 镜头锁敌 · 移动施法'),
        ('72-四Boss技能扩展v4操作说明.md', '74-Boss工作台v5操作说明.md'),
        ('隔离副本独立运行；阿花/万钧可在此启动，烟千岁/游龙请进入游戏按 Insert 选择。',
         '隔离副本独立运行；进入游戏按 Insert 选择角色。中键锁敌，Shift+技能可用。'),
        ("str(ROOT / ('tools/research_scene_checkpoint.py' if action=='prepare' else 'tools/ahua_practice.py'))",
         "str((ROOT / 'tools/research_scene_checkpoint.py') if action=='prepare' else PLAYER_FLOW / 'ahua_practice.py')"),
        ('command = [sys.executable,', "command = [sys.executable, '-B', '-X', 'utf8',"),
        ('ROOT = Path(__file__).resolve().parents[1]', 'ROOT = Path(__file__).resolve().parents[1]\nPLAYER_FLOW=Path(' + repr(str(flow)) + ')'),
    )
    for before, after in replacements:
        assert source.count(before) == 1, before
        source = source.replace(before, after)
    return source


def main(smoke=False):
    _, manifest, _ = installed_package()
    release = ROOT / 'releases' / manifest['release_id']
    flow = published.build(release)
    saved = {name:sys.modules.get(name) for name in ('player_keymap', 'player_settings')}
    try:
        for name in saved:
            spec = importlib.util.spec_from_file_location(name, flow / (name + '.py'))
            module = importlib.util.module_from_spec(spec); sys.modules[name] = module; spec.loader.exec_module(module)
        settings = sys.modules['player_settings']
        data = json.loads((ROOT / '玩家设置.json').read_text(encoding='utf-8-sig'))
        normalized, changed = previous.previous.previous.startup_settings(data)
        if changed and not smoke: settings.save(ROOT / '玩家设置.json', normalized)
        original_labels = settings.editor_skill_labels
        def labels(identifier):
            result = original_labels(identifier)
            if identifier in previous.EXTRA:
                result.update(dict(zip(('skill_06', 'skill_08', 'skill_07', 'teleport_left'), previous.EXTRA[identifier])))
            return result
        settings.BOSSES = dict(previous.previous.previous.STARTUP_BOSSES)
        settings.editor_skill_labels = labels
        if smoke: settings.read = lambda: dict(normalized)
        gui = types.ModuleType('boss_workbench_v5_gui'); gui.__file__ = str(ROOT / 'tools/ahua_practice_window.py')
        exec(compile(render(flow, len(manifest['bosses'])), gui.__file__, 'exec'), gui.__dict__)
        gui.main(smoke=smoke)
    finally:
        for name,module in saved.items():
            if module is None: sys.modules.pop(name, None)
            else: sys.modules[name] = module


if __name__ == '__main__': main('--smoke' in sys.argv)
