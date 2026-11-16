"""Four-role player window; refuse unaccepted installed candidates."""
import hashlib
import json
import sys
import types
from pathlib import Path
import boss_workbench_v2_window as previous
from mod_installation import installed_package

ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_SHA = '82be68f0a625ed3a6e32c4f708547cd5f055b5b62445843bd88f39b2b2d99690'
IDS = ['ahua_guitoudao', '057_wanjun', '073_yanqiansui', '056_youlong']


def check_installed():
    receipt, manifest, _ = installed_package()
    assert receipt['enabled'] and manifest['status'] == 'release'
    assert manifest['complete_mod'] and manifest['runtime_acceptance_current']
    assert manifest['release_id'].startswith('ahua-boss-workbench-v3-')
    assert [r['id'] for r in manifest['bosses']] == IDS and manifest['locked_previews'] == []
    return manifest


def render():
    assert hashlib.sha256((ROOT / 'tools/boss_workbench_v2_window.py').read_bytes()).hexdigest() == PREVIOUS_SHA
    source = previous.render()
    changes = (
        ('Boss 工作台 v2 · 三角色离线操控', 'Boss 工作台 v3 · 四角色离线操控'),
        ('Boss 工作台 v2：阿花 · 万钧 · 游龙', 'Boss 工作台 v3：阿花 · 万钧 · 烟千岁 · 游龙'),
        ('隔离副本独立运行；阿花/万钧可在此启动，游龙请进入游戏按 Insert 选择。烟千岁仍锁定预览。',
         '隔离副本独立运行；阿花/万钧可在此启动，烟千岁/游龙请进入游戏按 Insert 选择。'),
        ('67-三Boss工作台v2交付说明.md', '70-四Boss工作台v3操作说明.md'),
    )
    for before, after in changes:
        assert source.count(before) == 1
        source = source.replace(before, after)
    return source


def main(smoke=False):
    if not smoke:
        check_installed()
    import player_settings
    data = json.loads((ROOT / '玩家设置.json').read_text(encoding='utf-8-sig'))
    normalized, changed = previous.startup_settings(data)
    if changed and not smoke:
        player_settings.save(ROOT / '玩家设置.json', normalized)
        print('启动角色已切回阿花；烟千岁和游龙请在游戏画面按 Insert 选择。', flush=True)
    old_bosses, old_read = player_settings.BOSSES, player_settings.read
    player_settings.BOSSES = dict(previous.STARTUP_BOSSES)
    if smoke:
        player_settings.read = lambda: dict(normalized)
    try:
        module = types.ModuleType('boss_workbench_v3_gui')
        module.__file__ = str(ROOT / 'tools/ahua_practice_window.py')
        exec(compile(render(), module.__file__, 'exec'), module.__dict__)
        module.main(smoke=smoke)
    finally:
        player_settings.BOSSES, player_settings.read = old_bosses, old_read


if __name__ == '__main__':
    main('--smoke' in sys.argv)
