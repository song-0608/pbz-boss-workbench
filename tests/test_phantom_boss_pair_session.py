import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import phantom_boss_pair_session as session
import phantom_boss_online_readonly as reader


class PairSessionTests(unittest.TestCase):
    def test_atomic_receipt_roundtrip_leaves_no_pending_file(self):
        with tempfile.TemporaryDirectory() as name:
            path=Path(name)/'session.json'
            session.atomic(path,{'status':'prepared'})
            session.atomic(path,{'status':'active'})
            self.assertEqual(json.loads(path.read_bytes()),{'status':'active'})
            self.assertEqual([p.name for p in path.parent.iterdir()],['session.json'])

    def test_run_is_bound_to_exact_managed_directory_and_roles(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);directory=root/('a'*32);directory.mkdir();path=directory/'session.json'
            value=dict(schema=1,mode='two-player-online-research',session='a'*32,
                instances={r:dict(box=b) for r,b in session.BOXES.items()})
            with patch.object(session,'RUNS',root):
                session.atomic(path,value);self.assertEqual(session.load_run(path)[1],value)
                value['instances']['guest']['box']='PBZSteamLab';session.atomic(path,value)
                with self.assertRaises(AssertionError):session.load_run(path)
                with self.assertRaises(AssertionError):session.load_run(root/'session.json')

    def test_read_receipt_requires_live_bounded_online_lease(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);directory=root/'runtime/online-runs'/('a'*32);directory.mkdir(parents=True)
            path=directory/'session.json'
            value=dict(schema=1,session='a'*32,mode='two-player-online-research',status='active',issued_at=100,
                expires_at=700,instances=dict(host=dict(box=session.BOXES['host'],game_pid=42)))
            with patch.object(reader,'ROOT',root):
                session.atomic(path,value);self.assertEqual(reader.validate_receipt(path,'host',101)[1]['game_pid'],42)
                for key,bad in (('mode','offline'),('status','prepared'),('issued_at',True),('expires_at',1401)):
                    changed={**value,key:bad};session.atomic(path,changed)
                    with self.subTest(key=key),self.assertRaises(AssertionError):reader.validate_receipt(path,'host',101)
                session.atomic(path,value)
                with self.assertRaises(AssertionError):reader.validate_receipt(path,'host',700)

    def test_stop_only_signals_two_owned_mod_gates(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);path=root/'session.json';value=dict(session='a'*32)
            def virtual(role,logical):return root/role
            for role in session.BOXES:(root/role/'Scripts').mkdir(parents=True)
            with patch.object(session,'load_run',return_value=(path,value)),patch.object(session,'virtual',side_effect=virtual):
                session.request_stop(path)
            self.assertTrue((root/'stop.json').is_file())
            for role in session.BOXES:
                self.assertEqual((root/role/'Scripts/bwb_stop.txt').read_bytes(),b'stop\n')
                self.assertFalse((root/role/'net_stop.txt').exists())

    def test_cleanup_preserves_research_saves(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);path=root/'session.json';value=dict(session='a'*32,status='prepared',formal_before={},deployed=[])
            def virtual(role,logical):
                return root/role/Path(logical).relative_to(session.GAME)
            for role in session.BOXES:
                mod=virtual(role,session.GAME/'platform/steam/ue4ss/Mods/PBZCoop');(mod/'Scripts').mkdir(parents=True)
                payload=mod/'Scripts/main.lua';payload.write_bytes(b'return true\n')
                value['deployed'].append(dict(role=role,path=str(payload),sha256=session.digest(payload)))
                save=root/role/'ProjectPBZ/Saved/SaveGames/current.sav';save.parent.mkdir(parents=True);save.write_bytes(b'new progress')
            with patch.object(session,'load_run',return_value=(path,value)),patch.object(session,'virtual',side_effect=virtual),\
                    patch.object(session,'api'),patch.object(session,'pids',return_value=[]),patch.object(session,'formal_files',return_value={}):
                session.cleanup(path)
            for role in session.BOXES:
                self.assertEqual((root/role/'ProjectPBZ/Saved/SaveGames/current.sav').read_bytes(),b'new progress')
                self.assertFalse(Path(next(r['path'] for r in value['deployed'] if r['role']==role)).exists())

    def test_cleanup_refuses_drift_before_removing_any_file(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);path=root/'session.json'
            def virtual(role,logical):return root/role/Path(logical).relative_to(session.GAME)
            payload=root/'host/platform/steam/dwmapi.dll';payload.parent.mkdir(parents=True);payload.write_bytes(b'changed')
            value=dict(session='a'*32,deployed=[dict(role='host',path=str(payload),sha256='0'*64)])
            with patch.object(session,'load_run',return_value=(path,value)),patch.object(session,'virtual',side_effect=virtual),\
                    patch.object(session,'api'),patch.object(session,'pids',return_value=[]):
                with self.assertRaises(AssertionError):session.cleanup(path)
            self.assertEqual(payload.read_bytes(),b'changed')

    def test_pid_reuse_or_foreign_container_cannot_be_terminated(self):
        identity=dict(pid=42,image='PBZ.exe',created=100)
        with patch.object(session,'pids',return_value=[]):self.assertFalse(session.terminate_owned(None,'host',identity))
        with patch.object(session,'pids',return_value=[42]),patch.object(session,'process_identity',return_value={**identity,'created':101}):
            self.assertFalse(session.terminate_owned(None,'host',identity))

    def test_temporary_network_changes_only_dedicated_box_network_rules(self):
        for online,game_auth in ((True,False),(False,False),(True,True)):
            with patch.object(session,'api'),patch.object(session,'change') as change,patch.object(session,'verify_policy') as verify:
                session.network_policy(online,game_auth)
                for call in change.call_args_list:
                    self.assertIn(call.args[1],session.BOXES.values());self.assertEqual(call.args[2],'NetworkAccess')
                self.assertEqual(verify.call_count,2)
                self.assertTrue(all(c.args[-2:]==(online,game_auth) for c in verify.call_args_list))
                rules=[c.args[3] for c in change.call_args_list]
                self.assertEqual('steam.exe,Allow' in rules,online)
                self.assertEqual('PBZ.exe,Allow;Protocol=TCP' in rules,game_auth)
                self.assertEqual('PBZ.exe,Allow;Port=53;Protocol=UDP' in rules,game_auth)
                self.assertNotIn('PBZ.exe,Allow',rules)
                self.assertTrue(all('PBZ.exe,Allow;Address=127.0.0.1;Protocol=UDP' in rules for _ in (0,)))

    def test_cached_user_does_not_qualify_as_online_game_authorization(self):
        value=dict(status='clients-running',instances={r:{} for r in session.BOXES})
        results={r:dict(official_existing_user=True,official_logged_on=(r=='host'),active_client_in_same_box=True)
            for r in session.BOXES}
        with patch.object(session,'load_run',return_value=(Path('session.json'),value)),\
                patch.object(session,'bootstrap',side_effect=lambda p,r,a:results[r]),patch.object(session,'atomic'):
            self.assertFalse(session.inspect_clients('session.json'))
            self.assertEqual(value['status'],'clients-running')
            results['guest']['official_logged_on']=True
            self.assertTrue(session.inspect_clients('session.json'))

    def test_activation_retry_refuses_any_initialized_game(self):
        value=dict(official_game_auth=True,expires_at=int(time.time())+600)
        from unittest.mock import MagicMock
        game=MagicMock();game.__enter__.return_value.count=100
        with patch.object(session,'load_run',return_value=(Path('session.json'),value)),\
                patch.object(reader,'OnlineGameRead',return_value=game),patch.object(session,'terminate_owned') as terminate:
            with self.assertRaises(AssertionError):session.retry_uninitialized_game('session.json','guest')
            terminate.assert_not_called()

    def test_game_discovery_uses_only_two_role_process_lists(self):
        expected=dict(pid=42,image=str(session.GAME/'platform/steam/PBZ.exe'),created=1)
        foreign=dict(pid=43,image=r'D:\another\PBZ.exe',created=2)
        with patch.object(session,'pids',side_effect=lambda dll,box:[42,43] if box==session.BOXES['guest'] else []),\
                patch.object(session,'process_identity',side_effect=lambda pid:expected if pid==42 else foreign):
            self.assertEqual(session.discover_games(None),dict(guest=expected))


if __name__=='__main__':unittest.main()
