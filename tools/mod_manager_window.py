"""本机离线Mod安装管理窗口；所有操作可在游戏关闭时完成。"""
import os
from pathlib import Path
import sys
import tkinter as tk
from tkinter import filedialog,messagebox,ttk
import mod_installation as manager


def main(smoke=False):
    window=tk.Tk();window.title('新娘阿花 · Mod安装管理');window.geometry('760x510')
    frame=ttk.Frame(window,padding=20);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='Mod安装、停用与卸载',font=('Microsoft YaHei UI',16,'bold')).pack(anchor='w')
    ttk.Label(frame,text='管理本机研究启动器的Mod副本。正式游戏、存档和个人键位均不属于卸载范围。',
        wraplength=700).pack(anchor='w',pady=10)
    display=tk.StringVar();ttk.Label(frame,textvariable=display,wraplength=700).pack(anchor='w',pady=10)
    selected=tk.StringVar()
    candidates=manager.ROOT/'releases'
    if not candidates.exists()or not any((p/manager.MANIFEST).is_file()for p in candidates.iterdir()):
        candidates=manager.ROOT/'runtime/release-candidates'
    if candidates.exists():
        options=sorted((p for p in candidates.iterdir()if(p/manager.MANIFEST).is_file()),key=lambda p:p.stat().st_mtime_ns)
        if options:selected.set(str(options[-1]))
    ttk.Label(frame,text='候选或发布包目录：').pack(anchor='w')
    row=ttk.Frame(frame);row.pack(fill='x',pady=6)
    ttk.Entry(row,textvariable=selected).pack(side='left',fill='x',expand=True)
    def browse():
        choice=filedialog.askdirectory(parent=window,title='选择包含pbz-release.json的Mod包目录',initialdir=str(candidates))
        if choice:selected.set(choice)
    ttk.Button(row,text='选择目录',command=browse).pack(side='left',padx=(8,0))
    result=tk.StringVar(value='安装不启动游戏；准备前会逐文件校验已启用的版本。')
    ttk.Label(frame,textvariable=result,wraplength=700).pack(anchor='w',pady=10)
    def refresh():
        try:
            current=manager.status()
            if current.get('development_source_active'):text='当前使用项目开发源码；尚未选择受管理的安装包。'
            elif not current.get('installed'):text='Mod已卸载；准备和启用会被拦截，重新安装后恢复。'
            else:text=('已启用'if current.get('enabled')else'已停用')+'：'+current['release_id']+'\n状态：'+current.get('release_status','unknown')
            display.set(text)
        except Exception as error:display.set('安装校验未通过：'+str(error))
    def action(name):
        try:
            if name=='install':manager.install(Path(selected.get()))
            elif name=='verify':
                if selected.get():manager.validate_package(Path(selected.get()))
                else:manager.installed_package()
            elif name=='enable':manager.set_enabled(True)
            elif name=='disable':manager.set_enabled(False)
            elif name=='uninstall':manager.uninstall()
            result.set({'install':'安装完成；启动器下次仅使用已校验的安装副本。',
                'verify':'文件清单与SHA-256校验通过。','enable':'已启用，下次准备或启用时生效。',
                'disable':'已停用；准备和装配会在启动游戏之前被拦截。',
                'uninstall':'已卸载已登记的Mod文件；键位、角色设置与研究记录保留。'}[name])
        except Exception as error:messagebox.showerror('操作未完成',str(error),parent=window)
        refresh()
    for title,name in (('安装选定版本','install'),('校验包文件','verify'),('启用Mod','enable'),('停用Mod','disable'),('卸载Mod文件','uninstall')):
        ttk.Button(frame,text=title,command=lambda name=name:action(name)).pack(fill='x',pady=3)
    refresh()
    if smoke:window.after(300,window.destroy)
    window.mainloop()


if __name__=='__main__':main('--smoke'in sys.argv)
