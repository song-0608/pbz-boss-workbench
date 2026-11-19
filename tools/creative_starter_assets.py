"""Execute only inside Unreal's native Python commandlet. Never edits PBZ assets."""
import json
import math
from pathlib import Path
import unreal as ue

ROOT='/Game/PBZCreative'
MAP=ROOT+'/Maps/L_PBZCreativeHub'
EAL=ue.EditorAssetLibrary
assets=ue.AssetToolsHelpers.get_asset_tools()
actors=ue.get_editor_subsystem(ue.EditorActorSubsystem)
levels=ue.get_editor_subsystem(ue.LevelEditorSubsystem)
project=Path(ue.Paths.project_dir()).resolve()
report_path=project/'Saved/PBZCreative/starter-complete.json'


def asset(path):
    value=ue.load_asset(path)
    assert value,'missing installed UE template asset: '+path
    return value


def blueprint(name,parent):
    path=ROOT+'/Characters/'+name
    if EAL.does_asset_exist(path):
        value=asset(path)
        assert EAL.get_metadata_tag(value,'PBZCreativeRecipe')=='starter-v1','existing user blueprint preserved: '+path
    else:
        factory=ue.BlueprintFactory();factory.set_editor_property('parent_class',EAL.load_blueprint_class(parent))
        value=assets.create_asset(name,ROOT+'/Characters',ue.Blueprint,factory)
        assert value,'could not create '+path
        EAL.set_metadata_tag(value,'PBZCreativeRecipe','starter-v1')
    ue.BlueprintEditorLibrary.compile_blueprint(value)
    assert value.get_editor_property('status')!=ue.BlueprintStatus.BS_ERROR,'blueprint compiler rejected '+path
    cls=EAL.load_blueprint_class(path);assert cls
    return value,cls,ue.get_default_object(cls)


def material(name,color,emissive=False):
    path=ROOT+'/Materials/'+name
    if EAL.does_asset_exist(path):return asset(path)
    value=assets.create_asset(name,ROOT+'/Materials',ue.Material,ue.MaterialFactoryNew())
    expression=ue.MaterialEditingLibrary.create_material_expression(value,ue.MaterialExpressionConstant3Vector,-250,0)
    expression.set_editor_property('constant',ue.LinearColor(*color))
    ue.MaterialEditingLibrary.connect_material_property(expression,'',ue.MaterialProperty.MP_BASE_COLOR)
    if emissive:ue.MaterialEditingLibrary.connect_material_property(expression,'',ue.MaterialProperty.MP_EMISSIVE_COLOR)
    ue.MaterialEditingLibrary.recompile_material(value)
    EAL.save_loaded_asset(value,only_if_is_dirty=False)
    return value


def spawn(cls,name,location=(0,0,0),rotation=(0,0,0),folder='PBZCreative/Scene'):
    value=actors.spawn_actor_from_class(cls,ue.Vector(*location),
        ue.Rotator(pitch=rotation[0],yaw=rotation[1],roll=rotation[2]))
    assert value,'actor spawn failed: '+name
    value.set_actor_label(name);value.set_folder_path(folder)
    return value


def mesh(name,location,scale,material_value,shape='Cube',rotation=(0,0,0)):
    value=spawn(ue.StaticMeshActor,name,location,rotation)
    component=value.static_mesh_component
    component.set_static_mesh(asset('/Engine/BasicShapes/'+shape))
    component.set_material(0,material_value);value.set_actor_scale3d(ue.Vector(*scale))
    return value


def label(text,location,size=55,color=(170,225,255,255)):
    value=spawn(ue.TextRenderActor,text.replace('\n',' '),location,(0,180,0),'PBZCreative/Guide')
    component=value.text_render
    component.set_text(text);component.set_world_size(size);component.set_text_render_color(ue.Color(*color))
    component.set_horizontal_alignment(ue.HorizTextAligment.EHTA_CENTER)
    return value


def main():
    assert project.name=='PBZCreative','wrong project for creative starter'
    assert not EAL.does_asset_exist(MAP),'existing map preserved; inspect it rather than overwrite'
    # Fail dependency checks before creating a level or any owned blueprint.
    for path in ('/Game/ThirdPerson/Blueprints/BP_ThirdPersonCharacter',
                 '/Game/ThirdPerson/Blueprints/BP_ThirdPersonGameMode',
                 '/Niagara/DefaultAssets/Templates/Systems/FountainLightweight'):
        asset(path)
    tuning=json.loads((project/'Config/PBZCreative/3c.json').read_text(encoding='utf-8'))['profiles'].get('*',{})
    character,char_class,cdo=blueprint('BP_CreativeCharacter','/Game/ThirdPerson/Blueprints/BP_ThirdPersonCharacter')
    movement=cdo.get_editor_property('character_movement')
    movement.set_editor_property('max_walk_speed',float(tuning.get('walk_speed_cm_s',480)))
    movement.set_editor_property('rotation_rate',ue.Rotator(pitch=0,yaw=float(tuning.get('turn_rate_degrees_s',540)),roll=0))
    EAL.save_loaded_asset(character,only_if_is_dirty=False)
    game,game_class,defaults=blueprint('BP_CreativeGameMode','/Game/ThirdPerson/Blueprints/BP_ThirdPersonGameMode')
    defaults.set_editor_property('default_pawn_class',char_class)
    EAL.save_loaded_asset(game,only_if_is_dirty=False)
    fx_path=ROOT+'/Effects/NS_CreativeFountain'
    effect=asset(fx_path) if EAL.does_asset_exist(fx_path) else assets.duplicate_asset(
        'NS_CreativeFountain',ROOT+'/Effects',asset('/Niagara/DefaultAssets/Templates/Systems/FountainLightweight'))
    assert effect,'Niagara example duplication failed'
    EAL.save_loaded_asset(effect,only_if_is_dirty=False)
    materials={name:material('M_'+name,color,glow) for name,color,glow in (
        ('Slate',(0.055,0.085,0.12),False),('Floor',(0.16,0.20,0.25),False),
        ('Cyan',(0.05,1.6,2.8),True),('Orange',(3.0,.5,.06),True),('White',(.65,.74,.8),False))}
    assert levels.new_level(MAP),'could not create creative map'
    world=ue.get_editor_subsystem(ue.UnrealEditorSubsystem).get_editor_world()
    world.get_world_settings().set_editor_property('default_game_mode',game_class)
    mesh('Arena foundation',(0,0,-65),(36,28,1),materials['Slate'])
    mesh('Playable floor',(0,0,-10),(34,26,.2),materials['Floor'])
    for x in range(-1500,1600,300):
        mesh('Floor stripe X '+str(x),(x,0,1),(.015,25,.015),materials['White'])
    for y in range(-1200,1201,300):
        mesh('Floor stripe Y '+str(y),(0,y,1),(33,.015,.015),materials['White'])
    for location,scale in (((0,1350,140),(36,.5,4)),((0,-1350,140),(36,.5,4)),((1750,0,140),(.5,27,4))):
        mesh('Perimeter',location,scale,materials['Slate'])
    for y,color,name in ((-800,'Cyan','3C LAB'),(0,'White','SCENE LAB'),(800,'Orange','VFX LAB')):
        mesh(name+' platform',(1050,y,20),(5,5,.4),materials['Slate'],'Cylinder')
        mesh(name+' trim',(1050,y,42),(4.6,4.6,.04),materials[color],'Cylinder')
        label(name,(1350,y,440),70)
    mesh('Movement step 1',(-150,-650,45),(2,4,.9),materials['Slate'])
    mesh('Movement step 2',(150,-650,90),(2,4,1.8),materials['Slate'])
    mesh('Movement step 3',(450,-650,135),(2,4,2.7),materials['Slate'])
    mesh('Scene example column',(1050,0,185),(1.5,1.5,3),materials['White'],'Cylinder')
    preview=spawn(char_class,'3C character preview',(1050,-800,150),(0,180,0),'PBZCreative/Preview')
    preview.set_editor_property('auto_possess_player',ue.AutoReceiveInput.DISABLED)
    niagara=spawn(ue.NiagaraActor,'Editable Niagara fountain',(1050,800,70),folder='PBZCreative/Effects')
    niagara.get_component_by_class(ue.NiagaraComponent).set_asset(effect)
    spawn(ue.PlayerStart,'Start here - WASD / mouse / Space',(-1100,0,120))
    sun=spawn(ue.DirectionalLight,'Main sunlight',(0,0,1600),(-50,-25,0),'PBZCreative/Lighting')
    sun.light_component.set_editor_property('intensity',6.0)
    sun.light_component.set_editor_property('mobility',ue.ComponentMobility.MOVABLE)
    sky=spawn(ue.SkyLight,'Ambient skylight',(0,0,1200),folder='PBZCreative/Lighting')
    sky.light_component.set_editor_property('mobility',ue.ComponentMobility.MOVABLE)
    sky.light_component.set_editor_property('intensity',1.0)
    spawn(ue.SkyAtmosphere,'Sky atmosphere',folder='PBZCreative/Lighting')
    label('PBZ CREATIVE WORKBENCH',(1650,0,760),100)
    label('WASD MOVE  |  MOUSE LOOK  |  SPACE JUMP',(1650,0,620),42)
    label('EDITOR PRACTICE - NOT A PBZ GAME LEVEL',(-800,0,18),32)
    unreal_editor=ue.get_editor_subsystem(ue.UnrealEditorSubsystem)
    camera=ue.Vector(-2350,-2450,1900);target=ue.Vector(300,0,120)
    unreal_editor.set_level_viewport_camera_info(camera,ue.MathLibrary.find_look_at_rotation(camera,target))
    assert levels.save_current_level(),'native level save failed'
    EAL.save_directory(ROOT,only_if_is_dirty=False,recursive=True)
    result=dict(schema=1,completed=True,layout_version=3,map=MAP,playable_character=ROOT+'/Characters/BP_CreativeCharacter',
        game_mode=ROOT+'/Characters/BP_CreativeGameMode',niagara=fx_path,actor_count=len(actors.get_all_level_actors()),
        editor_only=True,pbz_game_assets_imported=False,game_started=False,
        character_walk_speed=float(movement.get_editor_property('max_walk_speed')))
    report_path.parent.mkdir(parents=True,exist_ok=True)
    report_path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    ue.log('PBZ_CREATIVE_STARTER_COMPLETE '+json.dumps(result))


if __name__=='__main__':main()
