"""Versioned player launcher; preserve all frozen research and isolation code."""
import hashlib
import json
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
WINDOW_SHA = '0f2d123cbbf02a9c2b4168d7e28c9ef081e00ba3e59d84faeedbac7f10158d59'
STARTUP_BOSSES = {'ahua_guitoudao': '新娘阿花', '057_wanjun': '巨锤客：万钧'}


def startup_settings(data):
    if not isinstance(data, dict) or set(data) != {'boss_id'}:
        raise ValueError('启动角色设置格式错误')
    if data['boss_id'] in STARTUP_BOSSES:
        return dict(data), False
    if data['boss_id'] in ('073_yanqiansui', '056_youlong'):
        return {'boss_id': 'ahua_guitoudao'}, True
    raise ValueError('未登记的启动角色')


def render():
    data = (ROOT / 'tools/ahua_practice_window.py').read_bytes()
    assert hashlib.sha256(data).hexdigest() == WINDOW_SHA, 'Frozen launcher source changed'
    source = data.decode('utf-8')
    replacements = {
        "window.title('Boss 工作台 · 离线操控')": "window.title('Boss 工作台 v2 · 三角色离线操控')",
        "text='Boss 工作台：角色选择、操控与技能'": "text='Boss 工作台 v2：阿花 · 万钧 · 游龙'",
        "text='隔离副本独立运行 · 当前核定PBZ构建 · 使用已启用且通过校验的Mod版本'":
            "text='隔离副本独立运行；阿花/万钧可在此启动，游龙请进入游戏按 Insert 选择。烟千岁仍锁定预览。'",
        "text='选择Boss：'": "text='启动角色：'",
        "ROOT / '64-双Boss工作台操作说明.md'": "ROOT / '67-三Boss工作台v2交付说明.md'",
    }
    for before, after in replacements.items():
        assert source.count(before) == 1, before
        source = source.replace(before, after)
    return source


def main(smoke=False):
    import player_settings
    data = json.loads((ROOT / '玩家设置.json').read_text(encoding='utf-8-sig'))
    normalized, changed = startup_settings(data)
    if changed and not smoke:
        player_settings.save(ROOT / '玩家设置.json', normalized)
        print('启动角色已切回阿花；游龙在游戏内工作台选择，烟千岁暂未开放。', flush=True)
    # Only this GUI process limits the startup choices. The frozen arm subprocess
    # continues to validate the same two existing ordinary-entry configurations.
    original_bosses, original_read = player_settings.BOSSES, player_settings.read
    player_settings.BOSSES = dict(STARTUP_BOSSES)
    if smoke:
        player_settings.read = lambda: dict(normalized)
    try:
        module = types.ModuleType('boss_workbench_v2_gui')
        module.__file__ = str(ROOT / 'tools/ahua_practice_window.py')
        exec(compile(render(), module.__file__, 'exec'), module.__dict__)
        module.main(smoke=smoke)
    finally:
        player_settings.BOSSES, player_settings.read = original_bosses, original_read


if __name__ == '__main__':
    main('--smoke' in sys.argv)
