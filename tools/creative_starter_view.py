"""Frame the owned hub once when opening the full editor, never a commandlet."""
import json
from pathlib import Path
import unreal as ue

MAP='/Game/PBZCreative/Maps/L_PBZCreativeHub'
_handle=None
_attempts=0


def frame():
    editor=ue.get_editor_subsystem(ue.UnrealEditorSubsystem)
    world=editor.get_editor_world()
    if not world or not world.get_path_name().startswith(MAP+'.'):return False
    if editor.get_level_viewport_camera_info() is None:return False
    location=ue.Vector(-2350,-2450,1900)
    editor.set_level_viewport_camera_info(location,ue.MathLibrary.find_look_at_rotation(location,ue.Vector(300,0,160)))
    ue.log('PBZ_CREATIVE_VIEW_READY')
    return True


def start():
    global _handle,_attempts
    if _handle is not None:return
    _attempts=0
    def tick(_delta):
        global _handle,_attempts
        _attempts+=1
        try:done=frame()
        except Exception:done=False
        if done:
            try:repair_first_layout()
            except Exception as error:ue.log_warning('PBZ starter labels preserved: '+str(error))
        if done or _attempts>=300:
            ue.unregister_slate_post_tick_callback(_handle);_handle=None
    _handle=ue.register_slate_post_tick_callback(tick)


def repair_first_layout():
    """Face untouched starter labels toward spawn, only on a clean idle map."""
    project=Path(ue.Paths.project_dir()).resolve();path=project/'Saved/PBZCreative/starter-complete.json'
    if not path.is_file():return
    value=json.loads(path.read_text(encoding='utf-8'))
    if value.get('layout_version',1)>=3:return
    levels=ue.get_editor_subsystem(ue.LevelEditorSubsystem)
    if levels.is_in_play_in_editor() or ue.EditorLoadingAndSavingUtils.get_dirty_map_packages():return
    world=ue.get_editor_subsystem(ue.UnrealEditorSubsystem).get_editor_world()
    if not world or not world.get_path_name().startswith(MAP+'.'):return
    expected={'3C LAB':(1350,-800,440),'SCENE LAB':(1350,0,440),'VFX LAB':(1350,800,440),
        'PBZ CREATIVE WORKBENCH':(1650,0,760),
        'WASD MOVE  |  MOUSE LOOK  |  SPACE JUMP':(1650,0,620),
        'EDITOR PRACTICE - NOT A PBZ GAME LEVEL':(-800,0,18)}
    changed=[]
    for actor in ue.get_editor_subsystem(ue.EditorActorSubsystem).get_all_level_actors():
        if not isinstance(actor,ue.TextRenderActor) or str(actor.get_folder_path())!='PBZCreative/Guide':continue
        name=actor.get_actor_label()
        if name not in expected or str(actor.text_render.get_editor_property('text'))!=name:continue
        position=actor.get_actor_location();target=expected[name];rotation=actor.get_actor_rotation()
        if any(abs(a-b)>.01 for a,b in zip((position.x,position.y,position.z),target)):continue
        if any(abs(a)>.01 for a in (rotation.pitch,rotation.yaw,rotation.roll)):continue
        actor.set_actor_rotation(ue.Rotator(pitch=0,yaw=180,roll=0),False);changed.append(name)
    if changed:assert levels.save_current_level()
    value['layout_version']=3
    value['label_facing_migration']={'changed':changed,'preserved_author_changes':True}
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    repair_first_layout()
    start()
