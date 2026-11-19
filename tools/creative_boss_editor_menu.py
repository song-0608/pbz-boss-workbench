"""PBZ role authoring menu, loaded by the UE project's normal Python startup."""
import unreal as ue

ROOT = '/Game/PBZCreative/BossLibrary20261119'
MAP = ROOT + '/L_PBZBossGallery_v3'
ROLES = {'AHua': '阿花', 'WanJun': '巨贼克万钧', 'YouLong': '游龙',
         'YanQianSui': '烟千岁', 'XianZhe': '弦儿', 'MadDocter': '谢秋冬'}
_frame_handle = None


def blueprint(role):
    return ROOT + '/Characters/BP_Boss_' + role + ('_Clothed' if role == 'XianZhe' else '')


def idle_editor():
    assert not ue.get_editor_subsystem(ue.UnrealEditorSubsystem).get_game_world(), '请先结束 PIE，再使用角色创作菜单。'


def spawn(role):
    idle_editor()
    assert role in ROLES
    actors = ue.get_editor_subsystem(ue.EditorActorSubsystem)
    selected = actors.get_selected_level_actors()
    location = selected[0].get_actor_location() + ue.Vector(250, 0, 0) if selected else ue.Vector(0, 0, 0)
    cls = ue.EditorAssetLibrary.load_blueprint_class(blueprint(role))
    assert cls, '角色库尚未接收完整'
    actor = actors.spawn_actor_from_class(cls, location)
    assert actor
    actor.set_actor_label(ROLES[role] + ' | ' + role)
    actor.set_folder_path('PBZCreative/角色创作')
    actors.set_selected_level_actors([actor])
    return actor


def browse():
    ue.EditorAssetLibrary.sync_browser_to_objects([blueprint(role) for role in ROLES])


def gallery():
    idle_editor()
    assert not ue.EditorLoadingAndSavingUtils.get_dirty_map_packages(), '当前关卡尚有未保存改动，请先保存后再打开角色展厅。'
    assert ue.get_editor_subsystem(ue.LevelEditorSubsystem).load_level(MAP)
    frame_on_start()


def frame_gallery(role=None):
    idle_editor()
    editor = ue.get_editor_subsystem(ue.UnrealEditorSubsystem)
    world = editor.get_editor_world()
    assert world and world.get_path_name().startswith(MAP + '.'), '请先打开角色展厅，再定位角色。'
    if role:
        assert role in ROLES
        actors = ue.get_editor_subsystem(ue.EditorActorSubsystem)
        actor = next(a for a in actors.get_all_level_actors()
                     if a.get_actor_label() == ROLES[role] + ' | ' + role)
        target, extent = actor.get_actor_bounds(False)
        distance = max(extent.x, extent.y, extent.z, 70) * 3.0
        camera = target + ue.Vector(-distance * .35, distance, distance * .25)
        actors.set_selected_level_actors([actor])
    else:
        camera, target = ue.Vector(1600, -2300, 1400), ue.Vector(0, 400, 170)
    editor.set_level_viewport_camera_info(camera, ue.MathLibrary.find_look_at_rotation(camera, target))


def frame_on_start():
    global _frame_handle
    if _frame_handle is not None:
        return
    attempts = 0
    def tick(_delta):
        nonlocal attempts
        global _frame_handle
        attempts += 1
        try:
            editor = ue.get_editor_subsystem(ue.UnrealEditorSubsystem)
            world = editor.get_editor_world()
            ready = bool(world and world.get_path_name().startswith(MAP + '.'))
            if ready:
                frame_gallery()
        except Exception:
            ready = False
        if ready or attempts >= 300:
            ue.unregister_slate_post_tick_callback(_frame_handle)
            _frame_handle = None
    _frame_handle = ue.register_slate_post_tick_callback(tick)


def register():
    menus = ue.ToolMenus.get()
    parent = menus.extend_menu('LevelEditor.MainMenu.Tools')
    menu = parent.add_sub_menu('PBZBossLibrary', 'PBZCreative', 'PBZBossLibrary', 'PBZ 角色工作台')
    entries = [('Browse', '浏览六个角色蓝图', 'browse()'), ('Gallery', '打开角色展厅（须先保存当前关卡）', 'gallery()')]
    entries += [(role, '放入角色：' + label, 'spawn(' + repr(role) + ')') for role, label in ROLES.items()]
    for key, label, action in entries:
        entry = ue.ToolMenuEntry(name='PBZBossLibrary.' + key, type=ue.MultiBlockType.MENU_ENTRY)
        entry.set_label(label)
        entry.set_string_command(ue.ToolMenuStringCommandType.PYTHON, '',
                                 'import pbz_boss_editor_menu; pbz_boss_editor_menu.' + action)
        menu.add_menu_entry('Roles', entry)
    focus = menu.add_sub_menu('PBZBossLibrary', 'PBZCreative', 'PBZBossFocus', '定位展厅角色')
    for role, label in ROLES.items():
        entry = ue.ToolMenuEntry(name='PBZBossLibrary.Focus.' + role, type=ue.MultiBlockType.MENU_ENTRY)
        entry.set_label(label)
        entry.set_string_command(ue.ToolMenuStringCommandType.PYTHON, '',
                                 'import pbz_boss_editor_menu; pbz_boss_editor_menu.frame_gallery(' + repr(role) + ')')
        focus.add_menu_entry('Focus', entry)
    menus.refresh_all_widgets()
    frame_on_start()
    ue.log('PBZ_BOSS_EDITOR_MENU_REGISTERED=6 roles')
