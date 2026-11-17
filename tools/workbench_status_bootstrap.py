"""Add UI-only state guards around the exact installed v5 launcher and backend."""
import argparse
import importlib.util
import json
from pathlib import Path

from boss_adaptation_workflow import ROOT, sha
from mod_installation import MANIFEST, installed_package, unlinked_path


def verified_entry(entry):
    entry = unlinked_path(entry)
    assert entry == ROOT / 'tools/boss_workbench_v5_window.py'
    receipt, manifest, directory = installed_package()
    assert receipt['enabled'] and manifest['status'] == 'release'
    assert manifest['release_id'].startswith('ahua-boss-workbench-v5-')
    assert manifest['runtime_acceptance_current'] and manifest['complete_mod']
    assert sha(directory / MANIFEST) == receipt['manifest_sha256']
    proof_path = ROOT / manifest['acceptance_report']
    assert sha(proof_path) == manifest['acceptance_report_sha256']
    proof = json.loads(proof_path.read_bytes())
    assert proof['passed'] and proof['release_id'] == manifest['release_id']
    offline_path = ROOT / proof['offline']
    assert sha(offline_path) == proof['offline_sha256']
    offline = json.loads(offline_path.read_bytes())
    assert offline['passed']
    assert sha(entry) == offline['source_files']['tools/boss_workbench_v5_window.py']
    return entry


def render(source):
    source = source.replace('\r\n', '\n')
    def change(before, after):
        nonlocal source
        assert source.count(before) == 1, before
        source = source.replace(before, after)
    change('import player_settings\n',
        'import player_settings\nfrom workbench_session_status import snapshot, ActionLease, action_available\n')
    change("value='先点第1步，等待准备完成。普通Steam或其他游戏正在运行时，入口会停止并保留它们。'",
        "value='当前阶段与可用按钮会自动更新；每个步骤只需点一次。执行进度显示在下方。'")
    change('    buttons = []\n', '    buttons = []\n    action_buttons = {}\n'
        '    session_status = tk.StringVar()\n'
        "    ttk.Label(frame,textvariable=session_status,wraplength=810).pack(anchor='w',pady=(0,8))\n")
    change("        busy['value'] = True\n", """        view = snapshot(ROOT)
        if action not in view.allowed:
            status.set(view.message)
            add_line(view.message)
            return
        lease = ActionLease(ROOT)
        if action != 'status':
            try:
                acquired = lease.acquire()
            except OSError as error:
                status.set('无法取得步骤锁：' + str(error))
                return
            if not acquired:
                status.set('另一个工作台窗口正在执行步骤，请等待完成。')
                return
            # Re-read after acquiring: another window may just have finished.
            view = snapshot(ROOT)
            if action not in view.allowed:
                lease.release()
                status.set(view.message)
                return
        busy['value'] = True
""")
    change('                messages.put((\'done\', (1, False)))\n',
        "                messages.put(('done', (1, False)))\n            finally:\n                lease.release()\n")
    change('        buttons.append(button)\n', '        buttons.append(button)\n        action_buttons[action] = button\n')
    change('    def pump():\n', """    def refresh_session():
        view = snapshot(ROOT)
        session_status.set(view.message)
        if not busy['value']:
            available = action_available(ROOT)
            for action, button in action_buttons.items():
                enabled = action in view.allowed and (action == 'status' or available)
                button.configure(state='normal' if enabled else 'disabled')
            if view.bindings:
                binding_text.set(view.bindings)
        window.after(1000, refresh_session)

    def pump():
""")
    change("        job('stop', close_after=True)\n", """        if 'stop' not in snapshot(ROOT).allowed:
            window.destroy()
            return
        job('stop', close_after=True)
""")
    change('    pump()\n', '    refresh_session()\n    pump()\n')
    return source


def main(entry, smoke=False):
    path = verified_entry(entry)
    spec = importlib.util.spec_from_file_location('verified_workbench_v5', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    original = module.render
    module.render = lambda flow, count: render(original(flow, count))
    module.main(smoke=smoke)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('verified_entry', type=Path)
    parser.add_argument('--smoke', action='store_true')
    args = parser.parse_args()
    main(args.verified_entry, args.smoke)
