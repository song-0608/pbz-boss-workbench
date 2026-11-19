"""Starter setup safety uses fake assets; native UE proof is recorded separately."""
import ast
import json
from pathlib import Path
import runpy
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import creative_workspace as cw
import creative_starter_workspace as starter


class CreativeStarterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.project=cw.initialize(self.root);self.engine=self.root/'EngineInstall'
        for name in ('ThirdPersonCharacter','ThirdPersonGameMode','ThirdPersonPlayerController'):
            self.seed('Templates/TP_ThirdPersonBP/Content/ThirdPerson/Blueprints/BP_'+name+'.uasset',name.encode())
        for mount,relative in [('Characters','Mannequins/Sample.uasset'),('Input','Actions/IA_Move.uasset'),
                ('LevelPrototyping','Meshes/SM_Cube.uasset')]:
            self.seed('Templates/TemplateResources/High/'+mount+'/Content/'+relative,b'fake template bytes')
        self.seed('Engine/Binaries/Win64/UnrealEditor-Cmd.exe',b'never executed')

    def seed(self,name,raw):
        path=self.engine/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)

    def complete(self):
        for name in starter.REQUIRED:
            path=self.project.parent/'Content/PBZCreative'/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(b'fake asset - not native validation')
        cw.atomic(starter.state_path(self.project),cw.canonical(dict(schema=1,completed=True,map=starter.MAP)))

    def test_template_mounts_match_unreal_package_paths(self):
        with patch.object(starter,'editor_processes',return_value=[]):starter.prepare(self.project,self.engine)
        content=self.project.parent/'Content'
        self.assertTrue((content/'Input/Actions/IA_Move.uasset').is_file())
        self.assertTrue((content/'Characters/Mannequins/Sample.uasset').is_file())
        self.assertTrue((content/'LevelPrototyping/Meshes/SM_Cube.uasset').is_file())
        self.assertFalse((content/'Actions/IA_Move.uasset').exists())
        self.assertFalse(starter.ready(self.project),'directory seeding must not claim a working map')

    def test_existing_author_assets_and_unrelated_settings_are_preserved(self):
        path=self.project.parent/'Content/Input/Actions/IA_Move.uasset';path.parent.mkdir(parents=True);path.write_bytes(b'author edit')
        ini=self.project.parent/'Config/DefaultInput.ini';ini.write_text('[OwnSettings]\nkeep=yes\n',encoding='utf-8')
        with patch.object(starter,'editor_processes',return_value=[]):result=starter.prepare(self.project,self.engine)
        self.assertEqual(path.read_bytes(),b'author edit')
        self.assertIn('Input/Actions/IA_Move.uasset',result['preserved_modified'])
        self.assertIn('keep=yes',ini.read_text());self.assertIn('EnhancedPlayerInput',ini.read_text())

    def test_running_project_blocks_generation_before_any_source_changes(self):
        before=self.project.read_bytes()
        with patch.object(starter,'editor_processes',return_value=[dict(ProcessId=123)]),self.assertRaisesRegex(AssertionError,'保存并关闭'):
            starter.prepare(self.project,self.engine)
        self.assertEqual(self.project.read_bytes(),before)

    def test_native_commandlet_is_headless_and_sets_default_map_only_on_success(self):
        calls=[]
        def native(command,**kwargs):
            calls.append(command);self.complete();return SimpleNamespace(returncode=0)
        with patch.object(starter,'editor_processes',return_value=[]),patch.object(starter.subprocess,'run',side_effect=native):
            starter.ensure(self.project,self.engine)
        self.assertEqual(len(calls),1);self.assertIn('-run=pythonscript',calls[0]);self.assertIn('-NullRHI',calls[0])
        ini=(self.project.parent/'Config/DefaultEngine.ini').read_text()
        self.assertIn('EditorStartupMap='+starter.MAP,ini)

    def test_failed_native_build_keeps_empty_scene_unaccepted(self):
        with (patch.object(starter,'editor_processes',return_value=[]),
                patch.object(starter.subprocess,'run',return_value=SimpleNamespace(returncode=1)),
                self.assertRaisesRegex(AssertionError,'生成未完成')):
            starter.ensure(self.project,self.engine)
        self.assertFalse(starter.ready(self.project))
        self.assertIn('/Engine/Maps/Entry',(self.project.parent/'Config/DefaultEngine.ini').read_text())
        self.assertFalse((self.project.parent/'Saved/PBZCreative/starter.lock').exists())

    def test_reopening_retains_saved_user_changes_and_does_not_rebuild(self):
        self.complete();path=self.project.parent/'Content/PBZCreative'/starter.REQUIRED[0]
        path.write_bytes(b'edited map')
        with patch.object(starter,'prepare',side_effect=AssertionError('must preserve existing scene')):
            starter.ensure(self.project,self.engine)
        self.assertEqual(path.read_bytes(),b'edited map')

    def test_custom_startup_map_is_not_replaced(self):
        ini=self.project.parent/'Config/DefaultEngine.ini'
        ini.write_text('[/Script/EngineSettings.GameMapsSettings]\nEditorStartupMap=/Game/MyMap\n',encoding='utf-8')
        starter.ini_values(ini,'/Script/EngineSettings.GameMapsSettings',{'EditorStartupMap':starter.MAP},allowed={'/Engine/Maps/Entry'})
        self.assertIn('/Game/MyMap',ini.read_text())

    def test_unicode_editor_ownership_is_checked(self):
        data=json.dumps([dict(ProcessId=321,CommandLine='UnrealEditor.exe "'+str(self.project)+'"')],ensure_ascii=False)
        with patch.object(starter.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=data)):
            self.assertEqual(starter.editor_processes(self.project)[0]['ProcessId'],321)

    def test_scene_script_has_valid_python_syntax(self):
        ast.parse(starter.SOURCE.read_text(encoding='utf-8'))

    def test_label_repair_preserves_active_dirty_and_unrelated_maps(self):
        self.complete();report=starter.state_path(self.project)
        cw.atomic(report,cw.canonical(dict(completed=True,map=starter.MAP,layout_version=2)))
        original=report.read_bytes()
        for playing,dirty,world in ((True,[],starter.MAP+'.Map'),(False,[object()],starter.MAP+'.Map'),
                                   (False,[],'/Game/AuthorMap.AuthorMap')):
            levels=SimpleNamespace(is_in_play_in_editor=lambda:playing)
            unreal_editor=SimpleNamespace(get_editor_world=lambda:SimpleNamespace(get_path_name=lambda:world))
            fake=SimpleNamespace(Paths=SimpleNamespace(project_dir=lambda:str(self.project.parent)),
                LevelEditorSubsystem='levels',UnrealEditorSubsystem='world',
                EditorLoadingAndSavingUtils=SimpleNamespace(get_dirty_map_packages=lambda:dirty),
                get_editor_subsystem=lambda key:{'levels':levels,'world':unreal_editor}[key])
            with patch.dict(sys.modules,unreal=fake):
                module=runpy.run_path(str(starter.VIEW_SOURCE),run_name='starter_view_tests')
                module['repair_first_layout']()
            self.assertEqual(report.read_bytes(),original)

    def test_label_repair_changes_only_identifiable_unedited_starter_labels(self):
        self.complete();report=starter.state_path(self.project)
        cw.atomic(report,cw.canonical(dict(completed=True,map=starter.MAP,layout_version=2)))
        changed=[];saved=[]
        class TextActor:
            def __init__(self,name,position,text=None):
                self.name=name;self.position=position
                self.text_render=SimpleNamespace(get_editor_property=lambda _:name if text is None else text)
            def get_folder_path(self):return 'PBZCreative/Guide'
            def get_actor_label(self):return self.name
            def get_actor_location(self):return SimpleNamespace(x=self.position[0],y=self.position[1],z=self.position[2])
            def get_actor_rotation(self):return SimpleNamespace(pitch=0,yaw=0,roll=0)
            def set_actor_rotation(self,value,_):changed.append((self.name,value))
        actors=[TextActor('3C LAB',(1350,-800,440)),TextActor('SCENE LAB',(10,20,30)),
                TextActor('VFX LAB',(1350,800,440),'my own heading')]
        levels=SimpleNamespace(is_in_play_in_editor=lambda:False,save_current_level=lambda:saved.append(True) or True)
        fake=SimpleNamespace(Paths=SimpleNamespace(project_dir=lambda:str(self.project.parent)),
            LevelEditorSubsystem='levels',UnrealEditorSubsystem='world',EditorActorSubsystem='actors',TextRenderActor=TextActor,
            Rotator=lambda **kw:kw,EditorLoadingAndSavingUtils=SimpleNamespace(get_dirty_map_packages=lambda:[]),
            get_editor_subsystem=lambda key:{'levels':levels,
                'world':SimpleNamespace(get_editor_world=lambda:SimpleNamespace(get_path_name=lambda:starter.MAP+'.Map')),
                'actors':SimpleNamespace(get_all_level_actors=lambda:actors)}[key])
        with patch.dict(sys.modules,unreal=fake):
            module=runpy.run_path(str(starter.VIEW_SOURCE),run_name='starter_view_tests')
            module['repair_first_layout']();module['repair_first_layout']()
        self.assertEqual(changed,[('3C LAB',dict(pitch=0,yaw=180,roll=0))])
        self.assertEqual(saved,[True]);self.assertEqual(cw.read(report)['layout_version'],3)


if __name__=='__main__':unittest.main()
