"""Read-only skill tab for the desktop Boss workbench."""
import tkinter as tk
from tkinter import ttk

from workbench_skill_catalog import Catalog, ROLES, short


def attach(notebook, root):
    tab = ttk.Frame(notebook, padding=12)
    notebook.add(tab, text='Boss 技能目录')
    toolbar = ttk.Frame(tab)
    toolbar.pack(fill='x', pady=(0, 8))
    ttk.Label(toolbar, text='资源分组').pack(side='left')
    role = ttk.Combobox(toolbar, state='readonly', width=31)
    role.pack(side='left', padx=(6, 14))
    ttk.Label(toolbar, text='搜索技能').pack(side='left')
    query = tk.StringVar()
    ttk.Entry(toolbar, textvariable=query, width=30).pack(side='left', padx=6, fill='x', expand=True)

    panes = ttk.Panedwindow(tab, orient='horizontal')
    panes.pack(fill='both', expand=True)
    left, right = ttk.Frame(panes), ttk.Frame(panes)
    panes.add(left, weight=1)
    panes.add(right, weight=2)
    skills = ttk.Treeview(left, columns=('type',), show='tree headings', selectmode='browse')
    skills.heading('#0', text='技能类')
    skills.heading('type', text='连招')
    skills.column('#0', width=235)
    skills.column('type', width=48, minwidth=45, stretch=False, anchor='center')
    details = tk.Text(right, width=46, wrap='word', state='disabled')
    for parent, widget in ((left, skills), (right, details)):
        scroll = ttk.Scrollbar(parent, command=widget.yview)
        widget.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        widget.pack(side='left', fill='both', expand=True)

    status = tk.StringVar(value='离线资源 · 游戏内生效情况待实测')
    ttk.Label(tab, textvariable=status, wraplength=800).pack(anchor='w', pady=(7, 0))
    catalog = None
    folders = []
    visible = {}

    def show(text):
        details.configure(state='normal')
        details.delete('1.0', 'end')
        details.insert('1.0', text)
        details.configure(state='disabled')

    def show_selection(_event=None):
        selected = skills.selection()
        row = visible.get(selected[0]) if selected else None
        try:
            show(catalog.details(row) if row else '')
        except (OSError, ValueError, KeyError) as error:
            show(f'技能详情读取失败：{error}')

    def refresh(*_args):
        if catalog is None or role.current() < 0:
            return
        previous = skills.selection()
        skills.delete(*skills.get_children())
        visible.clear()
        folder = folders[role.current()]
        try:
            rows = catalog.role(folder)['skills']
        except (OSError, ValueError, KeyError) as error:
            status.set(f'角色技能读取失败：{error}')
            show('')
            return
        search = query.get().strip().casefold()
        for row in rows:
            path = row['class_path']
            if search in path.casefold():
                visible[path] = row
                skills.insert('', 'end', iid=path, text=short(path), values=('是' if path in catalog.parents else '',))
        status.set(f'显示 {len(visible)} / {len(rows)} 项技能 · 离线资源 · 游戏内生效情况待实测')
        selection = previous[0] if previous and previous[0] in visible else next(iter(visible), None)
        if selection is not None:
            skills.selection_set(selection)
            skills.see(selection)
        show_selection()

    def load_tab(_event=None):
        nonlocal catalog
        if notebook.select() != str(tab) or catalog is not None:
            return
        try:
            catalog = Catalog(root)
        except (OSError, ValueError, KeyError) as error:
            status.set(f'离线技能目录读取失败：{error}')
            return
        folders.extend(folder for folder in ROLES if folder in catalog.folders)
        folders.extend(folder for folder in catalog.folders if folder not in ROLES)
        role.configure(values=[f'{ROLES[folder]} · {folder}' if folder in ROLES else folder for folder in folders])
        role.current(0)
        refresh()

    notebook.bind('<<NotebookTabChanged>>', load_tab, add='+')
    role.bind('<<ComboboxSelected>>', refresh)
    skills.bind('<<TreeviewSelect>>', show_selection)
    query.trace_add('write', refresh)
    return tab
