"""Offline collaboration contracts; synthetic files, never launch editor/game."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import creative_workspace as cw


class CreativeWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.storage=Path(self.temp.name);cw.initialize(self.storage);cw.initialize(self.storage,'backend')

    def config(self,profiles,lane='ue'):
        path=cw.paths(self.storage,lane)['workspace']/cw.CONFIGS[0]
        path.write_bytes(cw.canonical(dict(schema=1,profiles=profiles)))

    def asset(self,data,lane='ue'):
        path=cw.paths(self.storage,lane)['workspace']/'Content/PBZCreative/Effect.uasset'
        path.write_bytes(data);return path

    def submit(self,lane='ue'):return cw.submit(self.storage,lane)
    def integrate(self,key):return cw.integrate(key,self.storage)

    def test_initialization_preserves_user_files_and_never_launches(self):
        path=self.asset(b'user-owned source');self.config({'*':{'mouse_scale':.4}})
        with patch('subprocess.Popen',side_effect=AssertionError('no automatic launch')):
            project=cw.initialize(self.storage)
        self.assertEqual(path.read_bytes(),b'user-owned source')
        self.assertEqual(cw.read(project)['EngineAssociation'],'5.8')
        self.assertEqual(cw.read(project.parent/cw.CONFIGS[0])['profiles']['*']['mouse_scale'],.4)

    def test_drafts_do_not_change_active_tuning(self):
        self.config({'*':{'mouse_scale':.4}})
        self.assertEqual(cw.tuning(self.storage),({},None))
        key=self.submit();self.assertEqual(cw.tuning(self.storage),({},None))
        integration=self.integrate(key);profiles,identity=cw.tuning(self.storage)
        self.assertEqual(profiles['*']['mouse_scale'],.4)
        self.assertEqual(identity['integration'],integration)
        self.assertEqual(identity['visual_assets_state'],'editor_source_not_cooked')
        _,manifest=cw.active(self.storage)[1:]
        self.assertIs(manifest['runtime_accepted'],False)

    def test_parallel_lanes_merge_fields_and_preserve_each_workspace(self):
        self.config({'*':{'mouse_scale':.31}})
        self.config({'056_youlong':{'walk_speed_cm_s':610}},'backend')
        user=self.submit();backend=self.submit('backend')
        user_path=cw.paths(self.storage)['workspace']/cw.CONFIGS[0];before=user_path.read_bytes()
        self.integrate(backend)
        self.assertIsNone(cw.read(user_path.parent.parent.parent/'.pbz-base.json')['proposal'])
        result=self.integrate(user)
        profiles,_=cw.tuning(self.storage)
        self.assertEqual(profiles,{'*':{'mouse_scale':.31},'056_youlong':{'walk_speed_cm_s':610}})
        self.assertEqual(user_path.read_bytes(),before)
        self.assertEqual(self.integrate(user),result,'repeat integration is idempotent')
        # Subsequent author edits retain the other lane's accepted fields.
        self.config({'*':{'mouse_scale':.34}});self.integrate(self.submit())
        self.assertEqual(cw.tuning(self.storage)[0]['056_youlong']['walk_speed_cm_s'],610)

    def test_conflict_keeps_active_pointer_and_both_sources(self):
        self.config({'*':{'mouse_scale':.31}});self.config({'*':{'mouse_scale':.6}},'backend')
        user=self.submit();backend=self.submit('backend');self.integrate(backend)
        pointer=cw.paths(self.storage)['active'].read_bytes()
        plan=cw.merge_plan(user,self.storage)
        self.assertEqual(plan['conflicts'],[cw.CONFIGS[0]+'/profiles/*/mouse_scale'])
        with self.assertRaisesRegex(AssertionError,'合并冲突'):self.integrate(user)
        self.assertEqual(cw.paths(self.storage)['active'].read_bytes(),pointer)
        self.assertEqual(cw.read(cw.paths(self.storage)['workspace']/cw.CONFIGS[0])['profiles']['*']['mouse_scale'],.31)

    def test_binary_assets_are_merged_by_identity_and_conflict_is_not_overwritten(self):
        user_file=self.asset(b'user version');self.asset(b'backend version','backend')
        user=self.submit();backend=self.submit('backend');self.integrate(backend)
        self.assertIn('Content/PBZCreative/Effect.uasset',cw.merge_plan(user,self.storage)['conflicts'])
        with self.assertRaises(AssertionError):self.integrate(user)
        self.assertEqual(user_file.read_bytes(),b'user version')

    def test_reviewed_conflict_choices_are_recorded_and_stale_review_is_rejected(self):
        self.config({'*':{'mouse_scale':.31}});self.config({'*':{'mouse_scale':.6}},'backend')
        user=self.submit();backend=self.submit('backend');current=self.integrate(backend)
        field=cw.CONFIGS[0]+'/profiles/*/mouse_scale'
        with self.assertRaisesRegex(AssertionError,'另一方更新'):
            cw.integrate(user,self.storage,resolutions={field:'incoming'},expected_current=None)
        key=cw.integrate(user,self.storage,resolutions={field:'incoming'},expected_current=current)
        self.assertEqual(cw.tuning(self.storage)[0]['*']['mouse_scale'],.31)
        _,manifest=cw.checked_snapshot('integration',key,self.storage)
        self.assertEqual(manifest['conflict_resolutions'],{field:'incoming'})

    def test_binary_conflict_can_explicitly_keep_current(self):
        self.asset(b'user');self.asset(b'backend','backend')
        user=self.submit();backend=self.submit('backend');current=self.integrate(backend)
        key=cw.integrate(user,self.storage,resolutions={'Content/PBZCreative/Effect.uasset':'current'},expected_current=current)
        directory,_=cw.checked_snapshot('integration',key,self.storage)
        self.assertEqual((directory/'files/Content/PBZCreative/Effect.uasset').read_bytes(),b'backend')

    def test_three_way_distinguishes_deletion_from_new_fields(self):
        value,issues=cw.three_way({'a':1,'b':2},{'b':2},{'a':1,'b':3})
        self.assertEqual((value,issues),({'b':3},[]))
        _,issues=cw.three_way({'a':{'v':1}}, {}, {'a':{'v':2}})
        self.assertEqual(issues,['/a'])

    def test_conflict_paths_escape_slashes_in_visual_preset_names(self):
        _,issues=cw.three_way({'a/b~c':1},{'a/b~c':2},{'a/b~c':3})
        self.assertEqual(issues,['/a~1b~0c'])
        value,issues=cw.three_way({'a/b~c':1},{'a/b~c':2},{'a/b~c':3},resolutions={'/a~1b~0c':'incoming'})
        self.assertEqual((value,issues),({'a/b~c':2},[]))

    def test_config_validation_rejects_nonfinite_types_unknowns_and_ranges(self):
        for n in [True,'1',float('nan'),float('inf'),0,1.01]:
            with self.subTest(n=n),self.assertRaises((AssertionError,ValueError)):
                cw.validate_config(cw.CONFIGS[0],dict(schema=1,profiles={'*':{'mouse_scale':n}}))
        for value in [dict(schema=True,profiles={}),dict(schema=1,profiles={'unknown':{}}),
                dict(schema=1,profiles={'*':{'unknown':1}}),dict(schema=1,profiles={},unknown=1)]:
            with self.subTest(value=value),self.assertRaises(AssertionError):cw.validate_config(cw.CONFIGS[0],value)
        with self.assertRaises(ValueError):cw.validate_config(cw.CONFIGS[1],dict(schema=1,presets={'x':float('nan')}))

    def test_manifest_and_contents_are_verified(self):
        path=self.asset(b'original');key=self.submit()
        directory,_=cw.checked_snapshot('proposal',key,self.storage)
        (directory/'files'/path.relative_to(cw.paths(self.storage)['workspace'])).write_bytes(b'changed!')
        with self.assertRaises(AssertionError):cw.checked_snapshot('proposal',key,self.storage)

    def test_extra_snapshot_files_are_rejected(self):
        key=self.submit();directory,_=cw.checked_snapshot('proposal',key,self.storage)
        (directory/'files/Content/PBZCreative').mkdir(parents=True,exist_ok=True)
        (directory/'files/Content/PBZCreative/extra.uasset').write_bytes(b'extra')
        with self.assertRaisesRegex(AssertionError,'file set'):cw.checked_snapshot('proposal',key,self.storage)

    def test_paths_and_unknown_file_types_are_rejected(self):
        for name in ('../file.uasset','Content/PBZCreative/../../file.uasset',
                'Content/PBZCreative/file.py','D:/file.uasset','Content\\PBZCreative\\file.uasset'):
            with self.subTest(name=name),self.assertRaises(AssertionError):cw.relative(name)
        with self.assertRaises(AssertionError):cw.checked_snapshot('proposal','../escape',self.storage)
        with patch.object(Path,'is_symlink',return_value=True),self.assertRaises(AssertionError):cw.paths(self.storage)

    def test_failed_submission_cleans_staging_and_publishes_no_proposal(self):
        original=cw.shutil.copyfileobj;calls=[]
        config=cw.paths(self.storage)['workspace']/cw.CONFIGS[0]
        def editing(src,dest,*args):
            original(src,dest,*args);calls.append(src.name)
            if len(calls)==2:config.write_bytes(cw.canonical(dict(schema=1,profiles={'*':{'mouse_scale':.33}})))
        with patch.object(cw.shutil,'copyfileobj',side_effect=editing),self.assertRaisesRegex(AssertionError,'changed saved content'):
            self.submit()
        self.assertEqual(list(cw.paths(self.storage)['proposals'].iterdir()),[])

    def test_file_set_change_is_rejected_before_publication(self):
        original=cw.shutil.copyfileobj
        def adding(src,dest,*args):original(src,dest,*args);self.asset(b'created during save')
        with patch.object(cw.shutil,'copyfileobj',side_effect=adding),self.assertRaisesRegex(AssertionError,'file set'):
            self.submit()
        self.assertEqual(list(cw.paths(self.storage)['proposals'].iterdir()),[])

    def test_size_and_count_limits_publish_nothing(self):
        for limit in ('MAX_BYTES','MAX_FILES'):
            with patch.object(cw,limit,1),self.assertRaises(AssertionError):self.submit()
        self.assertFalse(cw.paths(self.storage)['proposals'].exists())

    def test_merge_lock_and_stale_profile_reject_parallel_write(self):
        with cw.merge_lock(self.storage):
            with self.assertRaises(RuntimeError),cw.merge_lock(self.storage):pass
        config=cw.paths(self.storage)['workspace']/cw.CONFIGS[0];old=cw.digest(config.read_bytes())
        cw.save_profile('*',{'mouse_scale':.3},old,self.storage)
        before=config.read_bytes()
        with self.assertRaisesRegex(AssertionError,'其他编辑'):cw.save_profile('*',{'mouse_scale':.6},old,self.storage)
        self.assertEqual(config.read_bytes(),before)
        self.assertFalse(cw.paths(self.storage)['lock'].exists())

    def test_unchanged_defaults_are_not_pinned_as_overrides(self):
        path=cw.paths(self.storage)['workspace']/cw.CONFIGS[0];raw=path.read_bytes()
        self.assertEqual(cw.save_profile('*',{},cw.digest(raw),self.storage),cw.digest(raw))
        self.assertEqual(path.read_bytes(),raw)

    def test_integrated_lua_resolves_global_role_and_explicit_priority(self):
        self.config({'*':{'mouse_scale':.4,'walk_speed_cm_s':570},'056_youlong':{'walk_speed_cm_s':620}})
        self.integrate(self.submit())
        text,identity=cw.render_tuning((ROOT/'tools/player_3c_tuning.lua').read_text(encoding='utf-8'),self.storage)
        module=self.storage/'tuning.lua';module.write_text(text,encoding='utf-8')
        script=self.storage/'test.lua';script.write_text("local t=assert(loadfile(arg[1]))()\n"
            "assert(t.resolve('058_maddoctor').mouse_scale==0.4)\n"
            "assert(t.resolve('058_maddoctor').walk_speed_cm_s==570)\n"
            "assert(t.resolve('056_youlong').walk_speed_cm_s==620)\n"
            "assert(t.resolve('056_youlong',{walk_speed_cm_s=700}).walk_speed_cm_s==700)\n",encoding='utf-8')
        executable=ROOT.parent/'build/lua-harness/Release/lua-lab.exe'
        result=subprocess.run([str(executable),str(script),str(module)],capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,(result.stdout+result.stderr).decode(errors='replace'))
        self.assertEqual(identity['integration'],cw.active(self.storage)[0])

    def test_candidate_pins_one_snapshot_even_if_active_changes_mid_build(self):
        import build_player_travel_candidate as candidate
        self.config({'*':{'mouse_scale':.4}});self.integrate(self.submit())
        selected=cw.tuning(self.storage)
        # A different integration is now active, but the build has pinned selected.
        self.config({'*':{'mouse_scale':.5}});self.integrate(self.submit())
        with patch.object(cw,'tuning',return_value=selected) as get:
            manifest,files=candidate.expected()
        self.assertEqual(get.call_count,1)
        self.assertEqual(manifest['travel_repair_identity']['creative_integration'],selected[1])
        self.assertIn(b'0.4',files[candidate.PREFIX+'player_3c_tuning.lua'])
        self.assertNotIn(b'0.5',files[candidate.PREFIX+'player_3c_tuning.lua'])


if __name__=='__main__':unittest.main()
