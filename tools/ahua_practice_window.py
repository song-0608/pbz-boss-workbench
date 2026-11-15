"""用途：为零基础用户提供阿花训练按钮；后台步骤按顺序执行，错误集中显示在窗口。"""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import player_keymap
import player_settings

ROOT = Path(__file__).resolve().parents[1]


def main(smoke=False):
    window = tk.Tk()
    window.title('Boss 工作台 · 离线操控')
    window.geometry('880x690')
    window.minsize(780, 600)
    frame = ttk.Frame(window, padding=20)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='Boss 工作台：角色选择、操控与技能', font=('Microsoft YaHei UI', 17, 'bold')).pack(anchor='w')
    ttk.Label(frame, text='隔离副本独立运行 · 当前核定PBZ构建 · 使用已启用且通过校验的Mod版本',
              wraplength=810).pack(anchor='w', pady=(8, 12))
    choice=ttk.Frame(frame);choice.pack(fill='x',pady=(0,8))
    ttk.Label(choice,text='选择Boss：').pack(side='left')
    boss_choice=tk.StringVar(value=player_settings.BOSSES[player_settings.read()['boss_id']])
    boss_box=ttk.Combobox(choice,textvariable=boss_choice,values=list(player_settings.BOSSES.values()),state='readonly',width=22)
    boss_box.pack(side='left')
    ttk.Label(choice,text='角色配置与下方键位在下一次启用时生效').pack(side='left',padx=10)
    def select_boss(_):
        selected=next(key for key,name in player_settings.BOSSES.items()if name==boss_choice.get())
        player_settings.save(ROOT/'玩家设置.json',player_settings.validate({'boss_id':selected}))
    boss_box.bind('<<ComboboxSelected>>',select_boss)
    status = tk.StringVar(value='先点第1步，等待准备完成。普通Steam或其他游戏正在运行时，入口会停止并保留它们。')
    ttk.Label(frame, textvariable=status, wraplength=810).pack(anchor='w', pady=(0, 12))
    messages = queue.Queue()
    busy = {'value': False, 'closing': False}
    buttons = []
    output = tk.Text(frame, height=14, wrap='word', font=('Microsoft YaHei UI', 10), state='disabled')

    def add_line(text):
        output.configure(state='normal')
        output.insert('end', text.rstrip() + '\n')
        output.see('end')
        output.configure(state='disabled')

    def job(action, close_after=False):
        if busy['value']:
            return
        busy['value'] = True
        for button in buttons:
            button.configure(state='disabled')
        status.set('正在执行，请看下方进度；不会自动反复退出重进游戏。')

        def run():
            command = [sys.executable, str(ROOT / 'tools/ahua_practice.py'), action]
            if action == 'launch':
                command.append('--cloud-off-reviewed')
            try:
                process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                           text=True, encoding='utf-8', errors='replace',
                                           env=dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1'),
                                           creationflags=subprocess.CREATE_NO_WINDOW)
                for line in process.stdout:
                    messages.put(('line', line))
                messages.put(('done', (process.wait(), close_after)))
            except Exception as error:
                messages.put(('line', str(error)))
                messages.put(('done', (1, False)))
        threading.Thread(target=run, daemon=True).start()

    for label, action in [('1　准备隔离副本与独立Steam', 'prepare'),
                          ('2　我已确认研究Steam云同步关闭，启动训练游戏', 'launch'),
                          ('3　已进入游戏场景并站稳，启用所选Boss', 'arm'),
                          ('4　结束本轮训练并核对正式存档', 'stop')]:
        button = ttk.Button(frame, text=label, command=lambda selected=action: job(selected))
        button.pack(fill='x', pady=4)
        buttons.append(button)
    binding_text=tk.StringVar(value='Insert 打开游戏内 Boss 工作台，↑ / ↓ 选择，Enter 确认。\nWASD移动，鼠标镜头。技能实际开放项会在第3步完成后显示。\n'
        '可编辑玩家键位.json，下次装配生效；未验收技能不能通过改键解锁。\n'
        '两个临时敌人供训练。收招后再切换/出招，距离和障碍物仍会影响命中。')
    ttk.Label(frame,textvariable=binding_text,wraplength=810).pack(anchor='w',pady=12)
    output.pack(fill='both', expand=True)
    links = ttk.Frame(frame)
    links.pack(fill='x', pady=(10, 0))
    ttk.Button(links, text='打开操作说明', command=lambda: os.startfile(ROOT / '64-双Boss工作台操作说明.md')).pack(side='left')
    ttk.Button(links, text='打开源码', command=lambda: os.startfile(ROOT / 'mod/PBZBossControl/Scripts')).pack(side='left', padx=8)
    ttk.Button(links, text='查看本轮状态', command=lambda: job('status')).pack(side='left')
    def edit_keys():
        dialog=tk.Toplevel(window);dialog.title('Boss技能与按键设置');dialog.geometry('660x790')
        # 所有已支持动作都可滚动到，增加技能后保存按钮仍固定可见。
        footer=ttk.Frame(dialog,padding=12);footer.pack(side='bottom',fill='x')
        body=ttk.Frame(dialog);body.pack(fill='both',expand=True)
        canvas=tk.Canvas(body,highlightthickness=0)
        scrollbar=ttk.Scrollbar(body,orient='vertical',command=canvas.yview)
        scrollbar.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        panel=ttk.Frame(canvas,padding=18);content=canvas.create_window((0,0),window=panel,anchor='nw')
        panel.bind('<Configure>',lambda event:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda event:canvas.itemconfigure(content,width=event.width))
        ttk.Label(panel,text='只修改已支持动作的按键；WASD与Esc保留。保存后下次启用生效。',wraplength=550).grid(row=0,column=0,columnspan=2,pady=(0,12),sticky='w')
        data=player_keymap.read();variables={};row=1
        selected=next(key for key,name in player_settings.BOSSES.items()if name==boss_choice.get())
        skill_labels=player_settings.editor_skill_labels(selected)
        description=tk.StringVar(value='点击任意按键框，查看该动作的说明和验收范围。')
        for group in ('controls','skills'):
            for action,key in data[group].items():
                if group=='skills'and action not in skill_labels:continue
                label=skill_labels[action]if group=='skills'else player_settings.LABELS[action]
                ttk.Label(panel,text=label).grid(row=row,column=0,sticky='w',pady=4)
                variable=tk.StringVar(value=key);variables[group,action]=variable
                combo=ttk.Combobox(panel,textvariable=variable,values=sorted(player_keymap.ALLOWED),state='readonly',width=23)
                combo.grid(row=row,column=1,sticky='e',pady=4)
                detail=(label+'：使用本角色原生能力，保留冷却、目标与状态限制。'
                    if selected=='057_wanjun'and group=='skills'else player_settings.DESCRIPTIONS[action])
                combo.bind('<FocusIn>',lambda event,detail=detail:description.set(detail))
                row+=1
        note=('万钧开放四项独立能力。其余角色键位保留，保存仍检查整张按键表的冲突。'
              if selected=='057_wanjun'else '左键是技能01快捷键，R是原生连招。被动、剧情及未验证招式不显示为可用键。')
        ttk.Label(panel,text=note,wraplength=550).grid(row=row,column=0,columnspan=2,sticky='w',pady=12)
        ttk.Label(footer,textvariable=description,wraplength=600).pack(anchor='w',pady=8)
        def save_keys():
            updated={group:{action:variables[group,action].get()if (group,action)in variables else key
                for action,key in data[group].items()}for group in ('controls','skills')}
            try:player_keymap.validate(updated);player_settings.save(ROOT/'玩家键位.json',updated)
            except (OSError,ValueError)as error:messagebox.showerror('键位未保存',str(error),parent=dialog);return
            add_line('键位已保存，下次启用生效；当前游戏按键保持原装配。');dialog.destroy()
        ttk.Button(footer,text='保存键位',command=save_keys).pack(anchor='e')
    ttk.Button(links,text='技能与改键',command=edit_keys).pack(side='left',padx=8)
    def manage_mod():
        subprocess.Popen([sys.executable,str(ROOT/'tools/mod_manager_window.py')],cwd=ROOT,
            creationflags=subprocess.CREATE_NO_WINDOW)
    ttk.Button(links,text='安装管理',command=manage_mod).pack(side='left',padx=8)

    def pump():
        try:
            while True:
                kind, payload = messages.get_nowait()
                if kind == 'line':
                    add_line(payload)
                elif kind == 'done':
                    code, close_after = payload
                    busy['value'] = False
                    for button in buttons:
                        button.configure(state='normal')
                    status.set('本步骤完成；按顺序继续。' if code == 0 else '本步骤未完成，请看最后一条错误；不会自动重试或重启。')
                    try:
                        owner=json.loads((ROOT/'runtime/ahua-practice.json').read_text(encoding='utf-8'))
                        if owner.get('phase')=='armed':
                            keys=owner.get('actual_controls')
                            if not keys:
                                add_line('当前会话缺少控制键快照，请以游戏内本轮状态层为准；下一轮启用后更新。')
                                continue
                            binding_text.set(keys['enter']+'开始｜'+keys['exit']+'回主角｜'+keys['cycle_target']+'切敌人｜WASD移动｜鼠标镜头\n'
                                +'；'.join(row['key']+' '+row['skill']for row in owner.get('actual_bindings',[]))
                                +'\nEsc先恢复主角，再按Esc进入原菜单；短时训练结束后研究箱自动关闭。')
                    except (OSError,ValueError,KeyError)as error:
                        add_line('键位显示未更新：'+str(error))
                    if close_after and code == 0:
                        window.destroy()
                        return
        except queue.Empty:
            pass
        window.after(150, pump)

    def close():
        if busy['value']:
            status.set('当前步骤尚在执行。完成后再关闭窗口；独立监督器仍限制本轮总时长。')
            return
        job('stop', close_after=True)

    window.protocol('WM_DELETE_WINDOW', close)
    pump()
    if smoke:
        # 用途：只验证窗口可以创建；不会准备、启动游戏或读取存档。
        window.after(350, window.destroy)
    window.mainloop()


if __name__ == '__main__':
    main('--smoke' in sys.argv)
