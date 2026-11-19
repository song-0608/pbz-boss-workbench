"""Real Tk integration, with all editor/game dispatch forbidden."""
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import creative_workspace as cw
import creative_workbench_ui as ui
import boss_workbench_v5_window as base_window
import workbench_status_bootstrap as bootstrap


@unittest.skipUnless(os.name=='nt','Windows Tk integration')
class CreativeWorkbenchTests(unittest.TestCase):
    def test_one_window_contains_original_boss_and_both_creative_tabs(self):
        import tkinter as tk
        from tkinter import ttk
        source=bootstrap.render(base_window.render(ROOT/'runtime/player-workflows/test',6))
        scope=dict(__name__='creative_ui_test',__file__=str(ROOT/'tools/ahua_practice_window.py'))
        exec(compile(source,'<creative-workbench>','exec'),scope)
        scope['player_settings']=types.SimpleNamespace(BOSSES={'ahua':'阿花'},read=lambda:dict(boss_id='ahua'))
        create=tk.Tk;observed=[];errors=[]
        def factory():
            window=create()
            def inspect():
                try:
                    books=[w for w in window.winfo_children() if isinstance(w,ttk.Notebook)]
                    self.assertEqual(len(books),1)
                    self.assertEqual([books[0].tab(tab,'text') for tab in books[0].tabs()],
                        ['Boss 开发与研究','UE 创作与 3C','统一集成与冲突'])
                    self.assertIn('PBZ 统一工作台',window.title());observed.append(True)
                except Exception as error:errors.append(error)
                finally:window.destroy()
            window.after(50,inspect);return window
        with (patch.object(tk,'Tk',side_effect=factory),patch('subprocess.Popen',side_effect=AssertionError('No launch')),
                patch.object(cw,'initialize',side_effect=AssertionError('No automatic writes'))):
            scope['main'](smoke=True)
        if errors:raise errors[0]
        self.assertEqual(observed,[True])

    def test_parameter_save_captures_tk_values_before_worker_and_callback_errors_are_visible(self):
        import tkinter as tk
        from tkinter import ttk
        with tempfile.TemporaryDirectory() as directory:
            storage=Path(directory);cw.initialize(storage);p=cw.paths(storage)
            window=tk.Tk();window.withdraw();self.addCleanup(window.destroy)
            notebook=ttk.Notebook(window);notebook.pack()
            with patch.object(cw,'paths',return_value=p):tabs=ui.attach(window,notebook,ROOT,smoke=False)
            widgets=[];todo=[tabs['creative']]
            while todo:
                widget=todo.pop();widgets.append(widget);todo.extend(widget.winfo_children())
            buttons={w.cget('text'):w for w in widgets if isinstance(w,ttk.Button)}
            main_thread=threading.get_ident();calls=[]
            original=tk.StringVar.get
            def main_get(variable):
                self.assertEqual(threading.get_ident(),main_thread,'Tk values accessed by worker')
                return original(variable)
            def save(role,settings,expected):
                self.assertNotEqual(threading.get_ident(),main_thread)
                self.assertEqual(role,'*');self.assertEqual(settings,{},'unchanged defaults must stay inherited')
                calls.append(True);return 'new-sha'
            with (patch.object(tk.StringVar,'get',main_get),patch.object(cw,'save_profile',side_effect=save),
                    patch('subprocess.Popen',side_effect=AssertionError('No launch'))):
                buttons['保存 3C 草稿'].invoke()
                deadline=time.monotonic()+3
                while time.monotonic()<deadline and not tabs['status'].get().startswith('完成：'):
                    window.update();time.sleep(.01)
                self.assertEqual(calls,[True]);self.assertIn('完成：',tabs['status'].get())
            # No selected proposal should be a visible error, not a Tk traceback.
            actions=[];todo=[tabs['integration']]
            while todo:
                widget=todo.pop();actions.append(widget);todo.extend(widget.winfo_children())
            preview=next(w for w in actions if isinstance(w,ttk.Button) and w.cget('text')=='预览差异 / 冲突')
            preview.invoke();self.assertIn('请先选择一个提案',tabs['status'].get())


if __name__=='__main__':unittest.main()
