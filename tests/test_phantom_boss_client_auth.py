from datetime import datetime
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import inspect_phantom_boss_client_auth as auth
from build_phantom_boss_candidate import canonical


class ClientAuthTests(unittest.TestCase):
    def setUp(self):self.now=int(time.time());self.issued=self.now-60
    def line(self,message,at=None):
        stamp=datetime.fromtimestamp(self.now-10 if at is None else at).strftime('%Y-%m-%d %H:%M:%S')
        return '['+stamp+'] [U:1:123456789] [private] '+message+'\n'
    def events(self,text):return auth.status_events(text,self.issued,self.now)

    def test_current_session_replacement_and_official_ok_are_separate_facts(self):
        text=self.line("RecvMsgClientLoggedOff('Session Replaced')")+self.line("RecvMsgClientLogOnResponse() : [U:1:123456789] 'OK'")
        result=self.events(text)
        self.assertEqual(result['session_replaced_events'],1)
        self.assertEqual(result['last_session_replaced_at'],self.now-10)
        self.assertEqual(result['last_official_logon_ok_at'],self.now-10)

    def test_old_log_events_do_not_accuse_this_lease_of_a_conflict(self):
        result=self.events(self.line("RecvMsgClientLoggedOff('Session Replaced')",self.issued-1))
        self.assertEqual(result['session_replaced_events'],0);self.assertIsNone(result['last_session_replaced_at'])

    def test_future_or_invalid_timestamp_cannot_be_accepted_as_current(self):
        text=self.line("RecvMsgClientLoggedOff('Session Replaced')",self.now+60)
        text+="[2026-99-99 23:00:00] RecvMsgClientLoggedOff('Session Replaced')\n"
        result=self.events(text)
        self.assertEqual(result['session_replaced_events'],0);self.assertEqual(result['unparsed_replacement_timestamps'],1)

    def test_missing_timestamp_is_reported_without_fabricating_event_time(self):
        result=self.events("RecvMsgClientLoggedOff('Session Replaced')")
        self.assertEqual(result['unparsed_replacement_timestamps'],1);self.assertIsNone(result['last_session_replaced_at'])

    def test_failed_logon_does_not_treat_processing_complete_as_a_second_failure(self):
        result=self.events(self.line("RecvMsgClientLogOnResponse() : 'Denied'")+
            self.line('RecvMsgClientLogOnResponse() : processing complete'))
        self.assertEqual(result['failed_logon_responses'],1);self.assertIsNone(result['last_official_logon_ok_at'])

    def test_identifiers_credentials_and_raw_lines_are_never_returned(self):
        text=self.line("RecvMsgClientLogOnResponse() : password=secret-value email=example@example.invalid 'Denied'")
        result=json.dumps(self.events(text))
        for private in ('123456789','secret-value','example@example.invalid','RecvMsgClient'):self.assertNotIn(private,result)

    def test_log_tail_read_is_bounded_and_older_prefix_is_ignored(self):
        with tempfile.TemporaryDirectory() as name:
            path=Path(name)/'connection_log.txt'
            path.write_text(self.line("RecvMsgClientLoggedOff('Session Replaced')")+'x'*(auth.MAX_BYTES+20)+'\n'+
                self.line("RecvMsgClientLogOnResponse() : 'OK'"),encoding='utf-8')
            result=auth.read_status(path,self.issued,self.now)
            self.assertTrue(result['log_present']);self.assertEqual(result['session_replaced_events'],0)
            self.assertEqual(result['last_official_logon_ok_at'],self.now-10)

    def test_missing_connection_log_is_explicit(self):
        with tempfile.TemporaryDirectory() as name:
            result=auth.read_status(Path(name)/'missing.txt',self.issued,self.now)
            self.assertFalse(result['log_present']);self.assertEqual(result['session_replaced_events'],0)

    def test_readiness_requires_both_official_online_booleans(self):
        roles={r:dict(official_existing_user=True,official_logged_on=True,session_replaced_events=0)for r in ('host','guest')}
        self.assertEqual(auth.verdict(roles),'both-clients-officially-logged-on-at-observation')
        roles['guest']['official_logged_on']=False;roles['guest']['session_replaced_events']=1
        self.assertEqual(auth.verdict(roles),'official-login-session-conflict')
        roles['guest']['session_replaced_events']=0;self.assertEqual(auth.verdict(roles),'official-login-not-ready')
        roles['guest']['official_logged_on']=1;self.assertEqual(auth.verdict(roles),'official-login-not-ready')

    def test_missing_role_and_invalid_lease_are_rejected(self):
        with self.assertRaises(ValueError):auth.verdict({})
        for issued,now in ((True,self.now),(0,self.now),(self.now+1,self.now)):
            with self.subTest(issued=issued),self.assertRaises(ValueError):auth.status_events('',issued,now)

    def test_workflow_cannot_treat_a_conflict_or_pending_login_as_success(self):
        self.assertEqual(auth.exit_code('both-clients-officially-logged-on-at-observation'),0)
        self.assertEqual(auth.exit_code('official-login-not-ready'),2)
        self.assertEqual(auth.exit_code('official-login-session-conflict'),3)
        with self.assertRaises(KeyError):auth.exit_code('unknown')

    def fixture(self,name):
        root=Path(name);path=root/'session.json'
        session=dict(status='clients-running',issued_at=self.issued,expires_at=self.now+600,session='a'*32)
        path.write_bytes(canonical(session))
        def virtual(role,logical):return root/role
        for role in auth.BOXES:
            directory=root/role/'logs';directory.mkdir(parents=True)
            (directory/'connection_log.txt').write_text(self.line("RecvMsgClientLoggedOff('Session Replaced')"),encoding='utf-8')
        return root,path,session,virtual

    def test_observation_writes_only_unique_sanitized_reports_and_keeps_session_unchanged(self):
        with tempfile.TemporaryDirectory() as name:
            root,path,session,virtual=self.fixture(name);before=path.read_bytes()
            with patch.object(auth,'load_run',return_value=(path,session)),patch.object(auth,'virtual',side_effect=virtual),\
                    patch.object(auth,'bootstrap',return_value=dict(official_existing_user=True,official_logged_on=False)):
                result=auth.inspect(path);auth.inspect(path)
            self.assertEqual(result['status'],'official-login-session-conflict')
            self.assertEqual(len(list(root.glob('client-auth-*.json'))),2)
            self.assertEqual(path.read_bytes(),before)
            self.assertFalse(result['game_started_by_tool']);self.assertFalse(result['login_automated'])
            self.assertFalse(result['raw_log_lines_published']);self.assertFalse(result['credential_stores_opened'])
            self.assertNotIn('123456789',json.dumps(result))

    def test_session_change_during_observation_prevents_report(self):
        with tempfile.TemporaryDirectory() as name:
            root,path,session,virtual=self.fixture(name)
            def bootstrap(*args):
                path.write_bytes(b'changed');return dict(official_existing_user=True,official_logged_on=False)
            with patch.object(auth,'load_run',return_value=(path,session)),patch.object(auth,'virtual',side_effect=virtual),\
                    patch.object(auth,'bootstrap',side_effect=bootstrap),self.assertRaisesRegex(AssertionError,'session changed'):
                auth.inspect(path)
            self.assertEqual(list(root.glob('client-auth-*.json')),[])

    def test_expired_lease_prevents_bootstrap_or_report(self):
        with tempfile.TemporaryDirectory() as name:
            root,path,session,virtual=self.fixture(name);session['expires_at']=self.issued
            with patch.object(auth,'load_run',return_value=(path,session)),patch.object(auth,'bootstrap')as bootstrap,\
                    self.assertRaises(AssertionError):auth.inspect(path)
            bootstrap.assert_not_called();self.assertEqual(list(root.glob('client-auth-*.json')),[])


if __name__=='__main__':unittest.main()
