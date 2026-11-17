"""Installed roster must survive the inherited two-role startup restrictions."""
from pathlib import Path
import os
import sys
import types
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import workbench_status_bootstrap as bootstrap


class WorkbenchRosterTests(unittest.TestCase):
    def test_all_installed_roles_are_selectable_without_resetting_saved_choice(self):
        ids = ('ahua_guitoudao', '057_wanjun', '073_yanqiansui', '056_youlong', '071_xianzhe', '058_maddoctor')
        manifest = dict(bosses=[dict(id=name, name=name, abilities=2, bindings=2) for name in ids])
        roles = bootstrap.installed_roles(manifest)
        self.assertEqual(tuple(roles), ids)
        for name in ids:
            value = dict(boss_id=name)
            self.assertEqual(bootstrap.startup_selection(value, roles), (value, False))
        with self.assertRaises(ValueError):
            bootstrap.startup_selection(dict(boss_id='067_motian'), roles)
        for invalid in (None, {}, {'boss_id': []}, {'boss_id': {}}, {'boss_id': 1}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                bootstrap.startup_selection(invalid, roles)

    def test_preview_and_duplicate_names_cannot_enter_startup_roster(self):
        row = dict(id='role', name='Role', abilities=1, bindings=1)
        with self.assertRaises(AssertionError):
            bootstrap.installed_roles(dict(bosses=[row, dict(row, id='other')]))
        with self.assertRaises(AssertionError):
            bootstrap.installed_roles(dict(bosses=[dict(row, abilities=0)]))

    @unittest.skipUnless(os.name == 'nt', 'Windows Tk integration')
    def test_actual_combobox_lists_and_saves_every_installed_role(self):
        import tkinter as tk
        from tkinter import ttk
        import boss_workbench_v5_window as window_source
        from mod_installation import installed_package
        root = Path(__file__).resolve().parents[1]
        _, manifest, _ = installed_package()
        roles = bootstrap.installed_roles(manifest)
        source = bootstrap.render(window_source.render(root / 'runtime/player-workflows/test', len(roles)))
        scope = dict(__name__='roster_test', __file__=str(root / 'tools/ahua_practice_window.py'))
        exec(compile(source, '<roster-test>', 'exec'), scope)
        save = Mock()
        scope['player_settings'] = types.SimpleNamespace(BOSSES=roles, read=lambda:dict(boss_id=next(iter(roles))),
            save=save, validate=lambda data:bootstrap.startup_selection(data, roles)[0])
        create = tk.Tk; errors=[]; observed=[]
        def factory():
            window = create()
            def inspect():
                try:
                    pending = list(window.winfo_children()); widgets=[]
                    while pending:
                        widget=pending.pop();widgets.append(widget);pending.extend(widget.winfo_children())
                    box=next(w for w in widgets if isinstance(w,ttk.Combobox))
                    self.assertEqual(tuple(box.cget('values')), tuple(roles.values()))
                    for identifier, name in roles.items():
                        box.set(name); box.event_generate('<<ComboboxSelected>>');window.update_idletasks()
                        self.assertEqual(save.call_args.args[1], {'boss_id':identifier})
                    observed.append(True)
                except Exception as error:
                    errors.append(error)
                finally:
                    window.destroy()
            window.after(50,inspect)
            return window
        with patch.object(tk,'Tk',side_effect=factory), patch('subprocess.Popen',side_effect=AssertionError('No game dispatch')):
            scope['main'](smoke=True)
        if errors:raise errors[0]
        self.assertEqual(observed,[True])


if __name__ == '__main__':
    unittest.main()
