import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import issue_phantom_boss_control_binding as issuer
import phantom_boss_pair_session as pair
from build_phantom_boss_candidate import canonical,sha
from test_phantom_boss_control_abi import valid_report


class ControlBindingTests(unittest.TestCase):
    def fixture(self,name):
        root=Path(name);receipt=root/'session.json';now=int(time.time())
        session=dict(session='a'*32,issued_at=now-10,expires_at=now+600,exe_sha256=issuer.abi.load_schema()['exe_sha256'],
            catalog_sha256='b'*64,upstream_commit='c'*40,bosses=dict(host='ahua_guitoudao',guest='056_youlong'),
            instances={role:dict(activation=token*32,game_pid=pid,game_identity=dict(pid=pid,created=134000000000000001+pid))
                for role,pid,token in [('host',42,'d'),('guest',43,'e')]},deployed=[],formal_before={})
        receipt.write_bytes(canonical(session))
        checked=issuer.abi.validate_declarations(valid_report(),session['exe_sha256'])
        checked.update(session=session['session'],role='host',pid=42,activation='d'*32,
            game_identity=session['instances']['host']['game_identity'],session_sha256=sha(receipt.read_bytes()),
            declarations_sha256='f'*64)
        def virtual(role,logical):
            return root/role/Path(logical).relative_to(pair.GAME)
        for role in pair.BOXES:virtual(role,pair.GAME/'platform/steam/ue4ss/Mods/PBZCoop/Scripts').mkdir(parents=True)
        payload=('return '+issuer.lua_value(issuer.launch_data(session,'host',checked))+'\n').encode('ascii')
        return root,receipt,session,checked,virtual,payload

    def publish(self,receipt,session,checked,virtual,payload):
        with patch.object(issuer,'virtual',side_effect=virtual),\
                patch.object(issuer,'validate_receipt',return_value=(session,session['instances']['host'])),\
                patch.object(pair,'process_identity',return_value=session['instances']['host']['game_identity']):
            return issuer.publish(receipt,session,'host',checked,payload)

    def test_process_creation_filetime_keeps_every_bit_as_text(self):
        for created in (134000000000000001,134000000000000002):
            self.assertEqual(issuer.process_token(dict(pid=42,created=created)),f'42:{created}')
        for invalid in (True,0,-1,1.25):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):issuer.process_token(dict(pid=42,created=invalid))

    def test_launch_data_contains_only_verified_control_bindings_and_exact_role(self):
        with tempfile.TemporaryDirectory() as name:
            _,_,session,checked,_,_=self.fixture(name)
            result=issuer.launch_data(session,'host',checked)
            self.assertEqual(result['process_identity'],'42:134000000000000043')
            self.assertEqual(result['boss_id'],'ahua_guitoudao')
            self.assertEqual(result['native_player_class'],issuer.PLAYER_CLASS)
            self.assertNotIn('visual',result['assembly']['bindings'])
            self.assertNotIn('workbench_ui',result['assembly']['bindings'])

    def test_guest_or_other_activation_cannot_receive_host_binding(self):
        with tempfile.TemporaryDirectory() as name:
            _,_,session,checked,_,_=self.fixture(name)
            with self.assertRaises(ValueError):issuer.launch_data(session,'guest',checked)
            checked['activation']='0'*32
            with self.assertRaises(ValueError):issuer.launch_data(session,'host',checked)

    def test_optional_unverified_ui_cannot_be_smuggled_into_control_data(self):
        with tempfile.TemporaryDirectory() as name:
            _,_,session,checked,_,_=self.fixture(name)
            checked['bindings']['workbench_ui']=dict(binding_verified=True)
            with self.assertRaisesRegex(ValueError,'unproven optional'):issuer.launch_data(session,'host',checked)

    def test_lua_serializer_rejects_non_data_and_roundtrips_special_utf8_bytes(self):
        with self.assertRaises(ValueError):issuer.lua_value(lambda:None)
        with self.assertRaises(ValueError):issuer.lua_value({1:'bad key'})
        value='"; error("must not execute") --\n\\\x00中文'
        literal=issuer.lua_value(value)
        with tempfile.TemporaryDirectory() as name:
            path=Path(name)/'check.lua'
            expected=','.join(str(b) for b in value.encode('utf-8'))
            path.write_text('local v='+literal+'\nlocal wanted={'+expected+'}\nassert(#v==#wanted)\n'
                'for i,b in ipairs(wanted)do assert(v:byte(i)==b)end\n'
                'local data=assert(load('+issuer.lua_value('return '+literal)+',"@data","t",{}))()\nassert(data==v)\n',encoding='ascii')
            result=subprocess.run([str(issuer.ROOT.parent/'build/lua-harness/Release/lua-lab.exe'),str(path)],capture_output=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_complete_binding_is_published_with_journal_and_original_session_unchanged(self):
        with tempfile.TemporaryDirectory() as name:
            root,receipt,session,checked,virtual,payload=self.fixture(name);before=receipt.read_bytes()
            record=self.publish(receipt,session,checked,virtual,payload)
            self.assertEqual(record['status'],'published')
            self.assertEqual(Path(record['target']).read_bytes(),payload)
            self.assertFalse(Path(record['pending']).exists())
            self.assertEqual(receipt.read_bytes(),before)
            self.assertEqual(json.loads((root/'host-control-binding.json').read_bytes()),record)
            self.assertEqual(issuer.owned_files(receipt,session,'host',resolver=virtual),[Path(record['target']),Path(record['pending'])])

    def test_existing_binding_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as name:
            root,receipt,session,checked,virtual,payload=self.fixture(name)
            target=virtual('host',pair.GAME/'platform/steam/ue4ss/Mods/PBZCoop/Scripts/bwb_current_bindings.lua')
            target.write_bytes(b'existing recovery owner')
            with self.assertRaisesRegex(ValueError,'already exists'):self.publish(receipt,session,checked,virtual,payload)
            self.assertEqual(target.read_bytes(),b'existing recovery owner')
            self.assertFalse((root/'host-control-binding.json').exists())

    def test_same_pid_with_new_creation_time_never_publishes_pending_binding(self):
        with tempfile.TemporaryDirectory() as name:
            root,receipt,session,checked,virtual,payload=self.fixture(name)
            with patch.object(issuer,'virtual',side_effect=virtual),\
                    patch.object(issuer,'validate_receipt',return_value=(session,session['instances']['host'])),\
                    patch.object(pair,'process_identity',return_value=dict(pid=42,created=999)),\
                    self.assertRaisesRegex(ValueError,'original role process changed'):
                issuer.publish(receipt,session,'host',checked,payload)
            record=json.loads((root/'host-control-binding.json').read_bytes())
            self.assertEqual(record['status'],'prepared');self.assertFalse(Path(record['target']).exists())
            self.assertEqual(Path(record['pending']).read_bytes(),payload)
            self.assertEqual(len(issuer.owned_files(receipt,session,'host',resolver=virtual)),2)

    def test_modified_session_prevents_any_journal_or_game_file_write(self):
        with tempfile.TemporaryDirectory() as name:
            root,receipt,session,checked,virtual,payload=self.fixture(name);receipt.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'session changed'):self.publish(receipt,session,checked,virtual,payload)
            self.assertFalse((root/'host-control-binding.json').exists())
            self.assertEqual(list((root/'host').rglob('*.lua')),[])

    def test_unknown_binding_and_modified_owned_payload_are_preserved(self):
        with tempfile.TemporaryDirectory() as name:
            _,receipt,session,checked,virtual,payload=self.fixture(name)
            record=self.publish(receipt,session,checked,virtual,payload)
            target=Path(record['target']);target.write_bytes(b'user changed')
            with self.assertRaisesRegex(ValueError,'preserve changed'):issuer.owned_files(receipt,session,'host',resolver=virtual)
            target.unlink();(receipt.parent/'host-control-binding.json').unlink();target.write_bytes(b'unknown')
            with self.assertRaisesRegex(ValueError,'preserve unrecognized'):issuer.owned_files(receipt,session,'host',resolver=virtual)

    def test_journal_cannot_redirect_cleanup_outside_its_role(self):
        with tempfile.TemporaryDirectory() as name:
            root,receipt,session,checked,virtual,payload=self.fixture(name)
            record=self.publish(receipt,session,checked,virtual,payload)
            record['pending']=str(root/'guest/do-not-touch.pending')
            (root/'host-control-binding.json').write_bytes(canonical(record))
            with self.assertRaisesRegex(ValueError,'escaped its role'):issuer.owned_files(receipt,session,'host',resolver=virtual)

    def test_pair_cleanup_removes_only_owned_binding_and_preserves_current_progress(self):
        with tempfile.TemporaryDirectory() as name:
            root,receipt,session,checked,virtual,payload=self.fixture(name)
            record=self.publish(receipt,session,checked,virtual,payload)
            save=root/'host/ProjectPBZ/Saved/SaveGames/current.sav';save.parent.mkdir(parents=True);save.write_bytes(b'latest progress')
            with patch.object(pair,'load_run',return_value=(receipt,session)),patch.object(pair,'virtual',side_effect=virtual),\
                    patch.object(pair,'api'),patch.object(pair,'pids',return_value=[]),patch.object(pair,'formal_files',return_value={}):
                pair.cleanup(receipt)
            self.assertFalse(Path(record['target']).exists());self.assertEqual(save.read_bytes(),b'latest progress')
            self.assertTrue((root/'host-control-binding.json').exists())

    def test_cleanup_rejects_changed_binding_before_removing_other_payload(self):
        with tempfile.TemporaryDirectory() as name:
            root,receipt,session,checked,virtual,payload=self.fixture(name)
            record=self.publish(receipt,session,checked,virtual,payload);Path(record['target']).write_bytes(b'changed')
            other=root/'host/platform/steam/dwmapi.dll';other.parent.mkdir(parents=True,exist_ok=True);other.write_bytes(b'keep')
            session['deployed']=[dict(role='host',path=str(other),sha256=sha(b'keep'))]
            with patch.object(pair,'load_run',return_value=(receipt,session)),patch.object(pair,'virtual',side_effect=virtual),\
                    patch.object(pair,'api'),patch.object(pair,'pids',return_value=[]),self.assertRaises(ValueError):
                pair.cleanup(receipt)
            self.assertEqual(other.read_bytes(),b'keep')


if __name__=='__main__':unittest.main()
