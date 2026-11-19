"""UE authoring and integration tabs in the existing verified Boss workbench."""
import json
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk

import creative_workspace as workspace

DEFAULTS=dict(mouse_scale=.22,look_step_degrees=45,manual_unlock_degrees=1,
    skill_buffer_seconds=.18,walk_speed_cm_s=480,turn_rate_degrees_s=540)
ROLE_DEFAULTS={'057_wanjun':dict(walk_speed_cm_s=420,turn_rate_degrees_s=420),
    '073_yanqiansui':dict(walk_speed_cm_s=450,turn_rate_degrees_s=480),
    '056_youlong':dict(walk_speed_cm_s=520,turn_rate_degrees_s=600)}
LABELS=dict(mouse_scale='鼠标灵敏度',look_step_degrees='单次镜头转角上限（度）',
    manual_unlock_degrees='手动解锁阈值（度）',skill_buffer_seconds='技能缓冲（秒）',
    walk_speed_cm_s='期望步速（厘米/秒）',turn_rate_degrees_s='转身速率（度/秒）')


def attach(window,notebook,root,smoke=False):
    creative=ttk.Frame(notebook,padding=18);integration=ttk.Frame(notebook,padding=18)
    notebook.add(creative,text='UE 创作与 3C');notebook.add(integration,text='统一集成与冲突')
    p=workspace.paths();messages=queue.Queue();busy=False;closed=False;buttons=[];inputs=[]
    status=tk.StringVar(value='你编辑 UE 资源，我继续 Boss 适配；保存、提交后在此统一集成。')
    ttk.Label(creative,textvariable=status,wraplength=790).pack(anchor='w')
    ttk.Label(creative,text='创作区：'+str(p['workspace']),wraplength=790).pack(anchor='w',pady=8)
    ttk.Label(creative,text='只提交已保存的 Content/PBZCreative 与 Config/PBZCreative；不覆盖后端源码或冻结发布包。',wraplength=790).pack(anchor='w')
    toolbar=ttk.Frame(creative);toolbar.pack(fill='x',pady=10)
    output=tk.Text(integration,height=10,wrap='word',state='disabled')
    def write(text):
        output.configure(state='normal');output.insert('end',text+'\n');output.see('end');output.configure(state='disabled')
    def job(label,fn,done=None):
        nonlocal busy
        if busy:return
        busy=True;status.set(label+'…')
        for button in buttons:button.configure(state='disabled')
        for widget,_ in inputs:widget.configure(state='disabled')
        def run():
            try:messages.put((True,fn(),done))
            except Exception as error:messages.put((False,str(error),None))
        threading.Thread(target=run,daemon=True).start()
    def button(parent,label,fn):
        def invoke():
            try:fn()
            except Exception as error:status.set('未完成：'+str(error));write('未完成：'+str(error))
        widget=ttk.Button(parent,text=label,command=invoke);widget.pack(side='left',padx=(0,7));buttons.append(widget)
    def open_path(path):
        assert Path(path).exists(),'请先初始化创作区'
        os.startfile(path);return '已打开 '+str(path)
    button(toolbar,'初始化创作区',lambda:job('初始化',workspace.initialize,lambda _:load_profile()))
    button(toolbar,'打开 UE 练习场',lambda:job('准备并打开 UE 练习场（首次会生成内容）',workspace.open_editor))
    button(toolbar,'打开创作目录',lambda:job('打开目录',lambda:open_path(p['workspace'])))
    button(toolbar,'提交已保存改动',lambda:job('冻结创作提案',workspace.submit,lambda key:(write('新提案：'+key),refresh())))
    library_bar=ttk.LabelFrame(creative,text='真实角色资产库 · UE 创作源',padding=8)
    library_bar.pack(fill='x',pady=5)
    import creative_boss_library as boss_library
    try:
        library=boss_library.status();role_labels={r['name']+' ('+r['role']+')':r['role'] for r in library['roles']}
        library_text='六个真实角色模型、18段原生动画；选择蓝图拖入场景。游戏技能事件和原版着色器仍须另行适配。'
    except (OSError,ValueError,AssertionError):
        role_labels={};library_text='角色资产尚未完成原生导入验收；保留当前创作工程。'
    selected_library_role=tk.StringVar(value=next(iter(role_labels),''))
    library_choices=ttk.Combobox(library_bar,textvariable=selected_library_role,values=list(role_labels),state='readonly',width=24)
    library_choices.pack(side='left',padx=(0,6));inputs.append((library_choices,'readonly'))
    button(library_bar,'接收已验证角色库',lambda:job('合并并添加角色资产',boss_library.publish,lambda value:(write(str(value)),refresh())))
    def open_library_role():
        selected_role=role_labels.get(selected_library_role.get())
        job('打开角色资源目录',lambda:boss_library.open_selected(selected_role))
    button(library_bar,'打开角色目录',open_library_role)
    ttk.Label(creative,text=library_text,wraplength=790).pack(anchor='w',pady=3)
    controls=ttk.LabelFrame(creative,text='3C 参数草稿：集成后进入下一次开发构建',padding=12)
    controls.pack(fill='x',pady=8)
    role=tk.StringVar(value='*');known=sorted(workspace.ROLES)
    ttk.Label(controls,text='角色（* 表示通用配置）').grid(row=0,column=0,sticky='w')
    choices=ttk.Combobox(controls,textvariable=role,values=known,state='readonly',width=23)
    choices.grid(row=0,column=1,sticky='w')
    inputs.append((choices,'readonly'))
    fields={};loaded={'sha':None}
    for row,(key,label) in enumerate(LABELS.items(),1):
        low,high=workspace.LIMITS[key]
        ttk.Label(controls,text=f'{label} [{low}–{high}]').grid(row=row,column=0,sticky='w',pady=3)
        value=tk.StringVar(value=str(DEFAULTS[key]));fields[key]=value
        entry=ttk.Entry(controls,textvariable=value,width=25);entry.grid(row=row,column=1,sticky='w')
        inputs.append((entry,'normal'))
    def load_profile(_=None):
        try:
            path=p['workspace']/workspace.CONFIGS[0];raw=path.read_bytes()
            data=workspace.validate_config(workspace.CONFIGS[0],json.loads(raw));loaded['sha']=workspace.digest(raw)
            settings={**DEFAULTS,**ROLE_DEFAULTS.get(role.get(),{}),**data['profiles'].get('*',{}),**data['profiles'].get(role.get(),{})}
            loaded.update(role=role.get(),own=dict(data['profiles'].get(role.get(),{})),effective=settings)
            for key,value in fields.items():value.set(str(settings[key]))
        except (OSError,AssertionError,ValueError) as error:
            loaded['sha']=None;status.set('可先初始化创作区；'+str(error))
    def save_profile():
        # Capture Tk variables on the UI thread; the worker only handles data.
        selected=role.get();values={key:float(value.get()) for key,value in fields.items()}
        expected=loaded['sha'];assert expected,'请先初始化或刷新参数'
        assert selected==loaded['role'],'请先刷新当前角色参数'
        settings=dict(loaded['own'])
        settings.update({key:value for key,value in values.items() if value!=loaded['effective'][key]})
        job('保存参数草稿',lambda:workspace.save_profile(selected,settings,expected),lambda _:load_profile())
    controls_bar=ttk.Frame(creative);controls_bar.pack(fill='x',pady=8)
    button(controls_bar,'刷新参数',load_profile)
    button(controls_bar,'保存 3C 草稿',save_profile)
    button(controls_bar,'编辑特效配置',lambda:job('打开特效草稿',lambda:open_path(p['workspace']/workspace.CONFIGS[1])))
    button(controls_bar,'编辑场景配置',lambda:job('打开场景草稿',lambda:open_path(p['workspace']/workspace.CONFIGS[2])))
    choices.bind('<<ComboboxSelected>>',load_profile)
    ttk.Label(creative,text='UE 素材仍须 Cook、挂载与游戏加载验证；当前整合的是创作源。3C 草稿不会立即修改正在运行的游戏。',wraplength=790).pack(anchor='w',pady=10)
    summary=tk.StringVar(value='尚无已集成提案。')
    ttk.Label(integration,textvariable=summary,wraplength=790).pack(anchor='w',pady=(0,8))
    listing=ttk.Treeview(integration,columns=('files','state'),show='tree headings',height=5)
    listing.heading('#0',text='创作提案');listing.heading('files',text='文件数');listing.heading('state',text='来源 / 状态')
    listing.column('#0',width=320);listing.column('files',width=80);listing.column('state',width=190)
    listing.pack(fill='both',expand=True)
    review={'proposal':None,'current':workspace.MISSING,'resolutions':{}}
    conflict_list=ttk.Treeview(integration,columns=('choice',),show='tree headings',height=3)
    conflict_list.heading('#0',text='冲突字段 / 资源（预览后选择取舍）');conflict_list.heading('choice',text='取舍')
    conflict_list.column('#0',width=530);conflict_list.column('choice',width=160)
    conflict_list.pack(fill='x',pady=6)
    def selected():
        rows=listing.selection();assert len(rows)==1,'请先选择一个提案'
        return rows[0]
    def refresh():
        # UI refresh reads metadata only; it never rehashes every asset per frame.
        listing.delete(*listing.get_children());conflict_list.delete(*conflict_list.get_children());active_proposal=None
        review.update(proposal=None,current=workspace.MISSING,resolutions={})
        if p['active'].exists():
            pointer=workspace.read(p['active']);key=pointer['integration']
            assert __import__('re').fullmatch('[a-f0-9]{24}',key)
            manifest=workspace.read(workspace.plain(p['integrations']/key/'manifest.json'))
            assert workspace.digest(workspace.canonical(manifest))[:24]==key
            active_proposal=manifest['proposal'];summary.set('已集成：'+key+'；3C 用于下次开发构建，视觉资源待 Cook/实机验证。')
        if p['proposals'].exists():
            rows=[x for x in p['proposals'].iterdir() if x.is_dir() and not x.name.startswith('.')]
            for directory in sorted(rows,key=lambda x:x.stat().st_mtime_ns,reverse=True)[:100]:
                manifest=workspace.read(workspace.plain(directory/'manifest.json'))
                assert workspace.digest(workspace.canonical(manifest))[:24]==directory.name
                listing.insert('', 'end',iid=directory.name,text=directory.name,
                    values=(len(manifest['files']),('UE / ' if manifest['lane']=='ue' else '后台 / ')+
                        ('已集成' if directory.name==active_proposal else '待检查 / 历史提案')))
    def preview():
        key=selected()
        def done(plan):
            review.update(proposal=key,current=plan['current'],resolutions={})
            conflict_list.delete(*conflict_list.get_children())
            for path in plan['conflicts']:conflict_list.insert('','end',iid=path,text=path,values=('未选择',))
            write('提案 '+key+'：'+('冲突：'+'；'.join(plan['conflicts']) if plan['conflicts'] else '可合并，共 '+str(len(plan['files']))+' 个文件。'))
        job('检查双方差异',lambda:workspace.merge_plan(key),done)
    def choose(choice):
        assert review['proposal']==selected(),'请先预览当前所选提案'
        rows=conflict_list.selection();assert rows,'请先选择冲突字段或资源'
        for path in rows:
            review['resolutions'][path]=choice
            conflict_list.item(path,values=('采用提案' if choice=='incoming' else '保留现有集成',))
    def integrate():
        key=selected();choices=dict(review['resolutions']) if review['proposal']==key else {}
        expected=review['current'] if review['proposal']==key else workspace.MISSING
        job('集成到下一次开发构建',lambda:workspace.integrate(key,resolutions=choices,expected_current=expected),
            lambda value:(write('集成快照：'+value),refresh(),load_profile()))
    def build():
        def run():
            from build_player_travel_candidate import build as freeze_candidate
            return freeze_candidate()
        job('生成开发候选（不安装）',run,lambda value:write('开发候选（尚未实机验收）：'+str(value)))
    conflict_actions=ttk.Frame(integration);conflict_actions.pack(fill='x',pady=3)
    button(conflict_actions,'所选冲突：采用提案',lambda:choose('incoming'))
    button(conflict_actions,'所选冲突：保留现有集成',lambda:choose('current'))
    actions=ttk.Frame(integration);actions.pack(fill='x',pady=8)
    button(actions,'刷新提案',refresh);button(actions,'预览差异 / 冲突',preview);button(actions,'集成所选提案',integrate)
    button(actions,'生成开发候选（不安装）',build)
    output.pack(fill='both',expand=True)
    def pump():
        nonlocal busy
        if closed:return
        try:
            while True:
                ok,result,done=messages.get_nowait();busy=False
                for widget in buttons:widget.configure(state='normal')
                for widget,state in inputs:widget.configure(state=state)
                status.set('完成：'+str(result) if ok else '未完成：'+str(result))
                if not ok:write('未完成：'+str(result))
                elif done:
                    try:done(result)
                    except Exception as error:status.set('结果刷新失败：'+str(error));write(str(error))
        except queue.Empty:pass
        window.after(100,pump)
    def retire(event):
        nonlocal closed
        if event.widget is window:closed=True
    window.bind('<Destroy>',retire,add='+')
    if not smoke:
        try:refresh()
        except Exception as error:status.set('提案状态读取失败：'+str(error))
        if (p['workspace']/workspace.CONFIGS[0]).exists():load_profile()
    pump()
    return dict(creative=creative,integration=integration,listing=listing,status=status)
