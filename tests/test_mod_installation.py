"""在临时目录验收真实文件安装流程，不启动Steam或游戏。"""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import mod_installation as m


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.root=self.base/'workspace';self.root.mkdir()
        self.package=self.base/'candidate';self.package.mkdir()
        for name in ('Scripts/main.lua','Scripts/player_entry.lua','Scripts/profiles/ahua.lua','Experiments/spawn_lifecycle.lua'):
            path=self.package/'PBZBossControl'/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text('-- offline fixture '+name,encoding='utf-8')
        self.data={'schema':1,'release_id':'ahua-test-v1','scope':'local-protected-offline-launcher',
            'status':'acceptance-candidate','files':{p.relative_to(self.package).as_posix():m.digest(p)
                for p in self.package.rglob('*.lua')}}
        self.write_manifest()
        for name in ('玩家键位.json','玩家设置.json','sentinel-save.sav'):
            (self.root/name).write_bytes(('preserve '+name).encode('utf-8'))
        self.before={p.name:p.read_bytes()for p in self.root.iterdir()if p.is_file()}

    def write_manifest(self):
        (self.package/m.MANIFEST).write_text(json.dumps(self.data),encoding='utf-8')

    def session(self,restored,**extra):
        path=self.root/'runtime/official-validation-test/state.json'
        m.save(path,dict(restored=restored,**extra))
        m.save(self.root/'runtime/latest-official-validation.json',{'state_file':str(path)})

    def test_install_disable_enable_uninstall_preserves_personal_files(self):
        self.session(True,remaining_box_pids=[],ue4ss_deployed=True,research_loader_removed=True)
        receipt=m.install(self.package,self.root);installed=Path(receipt['directory'])
        self.assertEqual(m.active_mod_root(self.root),installed/'PBZBossControl')
        m.set_enabled(False,self.root)
        with self.assertRaisesRegex(RuntimeError,'disabled'):m.active_mod_root(self.root)
        m.set_enabled(True,self.root)
        self.assertEqual(m.active_mod_root(self.root),installed/'PBZBossControl')
        result=m.uninstall(self.root)
        self.assertFalse(result['installed']);self.assertFalse(installed.exists())
        self.assertEqual(self.before,{k:(self.root/k).read_bytes()for k in self.before})
        with self.assertRaisesRegex(RuntimeError,'not installed'):m.active_mod_root(self.root)
        self.assertGreaterEqual(len(list((self.root/'evidence/installation').glob('*.json'))),5)

    def test_active_session_blocks_every_mutation(self):
        m.install(self.package,self.root);self.session(False)
        for operation in (lambda:m.install(self.package,self.root),lambda:m.set_enabled(False,self.root),
                          lambda:m.uninstall(self.root)):
            with self.subTest(operation=operation),self.assertRaisesRegex(RuntimeError,'current research session'):operation()
        self.assertTrue(m.status(self.root)['enabled'])

    def test_restored_flag_without_loader_removal_still_blocks(self):
        self.session(True,ue4ss_deployed=True,research_loader_removed=False)
        with self.assertRaises(RuntimeError):m.install(self.package,self.root)

    def test_tampered_installed_file_is_preserved_and_never_deployed(self):
        receipt=m.install(self.package,self.root)
        path=Path(receipt['directory'])/'PBZBossControl/Scripts/main.lua'
        path.write_text('modified',encoding='utf-8')
        for operation in (lambda:m.active_mod_root(self.root),lambda:m.uninstall(self.root)):
            with self.assertRaisesRegex(RuntimeError,'differs'):operation()
        self.assertEqual(path.read_text(encoding='utf-8'),'modified')

    def test_undeclared_file_prevents_uninstall_before_any_delete(self):
        receipt=m.install(self.package,self.root);directory=Path(receipt['directory'])
        extra=directory/'personal-notes.txt';extra.write_text('preserve')
        with self.assertRaisesRegex(RuntimeError,'Undeclared'):m.uninstall(self.root)
        self.assertTrue((directory/'PBZBossControl/Scripts/main.lua').exists())
        self.assertEqual(extra.read_text(),'preserve')

    def test_rejects_traversal_and_incomplete_package(self):
        for bad in ('../outside.lua','PBZBossControl/Scripts/../../outside.lua',
                    'PBZBossControl\\Scripts\\main.lua','PBZBossControl/Scripts/C:bad.lua'):
            self.data['files'][bad]='a'*64;self.write_manifest()
            with self.subTest(path=bad),self.assertRaises(RuntimeError):m.validate_package(self.package)
            del self.data['files'][bad]
        self.data['files'].pop('PBZBossControl/Scripts/player_entry.lua');self.write_manifest()
        with self.assertRaises(RuntimeError):m.validate_package(self.package)

    def test_same_id_cannot_replace_different_package(self):
        m.install(self.package,self.root)
        path=self.package/'PBZBossControl/Scripts/main.lua';path.write_text('new version')
        self.data['files']['PBZBossControl/Scripts/main.lua']=m.digest(path);self.write_manifest()
        with self.assertRaisesRegex(RuntimeError,'different content'):m.install(self.package,self.root)

    def test_development_fallback_only_before_first_install(self):
        self.assertEqual(m.active_mod_root(self.root),self.root/'mod/PBZBossControl')
        m.install(self.package,self.root);m.uninstall(self.root)
        with self.assertRaises(RuntimeError):m.active_mod_root(self.root)
        m.install(self.package,self.root)
        self.assertTrue(m.active_mod_root(self.root).is_dir())

    def test_receipt_cannot_select_an_external_directory(self):
        m.install(self.package,self.root)
        receipt=m.read(m.receipt_path(self.root));receipt['directory']=str(self.package)
        m.save(m.receipt_path(self.root),receipt)
        with self.assertRaisesRegex(RuntimeError,'outside'):m.active_mod_root(self.root)


if __name__=='__main__':unittest.main()
