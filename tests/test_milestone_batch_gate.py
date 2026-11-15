"""批量验收不得复用旧装配、混入开发键或延长旧凭据；此测试不发送游戏输入。"""
from datetime import datetime,timezone,timedelta
from pathlib import Path
import sys
import json
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from run_ahua_milestone_acceptance import SKILLS,validate_start,validate_active_heartbeat


class BatchGateTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,14,16,0,5,tzinfo=timezone(timedelta(hours=8))).timestamp()
        self.owner={'phase':'armed','player_entry':True,'actual_bindings':[{'slot':s,'skill':s,'key':'test'}for s in SKILLS]}
        self.state={'started_at':'2026-11-14T15:55:00+08:00','deadline_unix':self.now+900,'control_probe_expires_at':self.now+640}
        self.text='MAP_TRAVEL_GUARD_READY=true\n[2026-11-14 16:00:00.0000000] PBZ_CONTROL_LIFECYCLE:INTERACTIVE_READY=ready; cleanup in 600 seconds\n'

    def test_fresh_ordinary_assembly(self):self.assertEqual(validate_start(self.owner,self.state,self.text,self.now),self.now-5)

    def test_old_or_short_assembly_rejected(self):
        for now,state,text in ((self.now+30,self.state,self.text),
            (self.now,dict(self.state,control_probe_expires_at=self.now+580),self.text),
            (self.now,self.state,self.text+self.text),(self.now,self.state,self.text+'INTERACTIVE_END=done')):
            with self.subTest(now=now),self.assertRaises(RuntimeError):validate_start(self.owner,state,text,now)

    def test_developer_mode_or_missing_binding_rejected(self):
        for owner in (dict(self.owner,scene_transition_trial=True),dict(self.owner,skill_lab=True),
                      dict(self.owner,actual_bindings=self.owner['actual_bindings'][:-1])):
            with self.assertRaises(RuntimeError):validate_start(owner,self.state,self.text,self.now)

    def test_unprotected_ordinary_entry_rejected(self):
        with self.assertRaises(RuntimeError):
            validate_start(self.owner,self.state,self.text.replace('MAP_TRAVEL_GUARD_READY=true',''),self.now)

    def test_stability_requires_current_continuous_active_heartbeat(self):
        status={'session':'current','at':100,'expires_at':700,'player':'pc','text':'新娘阿花 | ACTIVE\n'}
        encode=lambda value:'PBZ_PLAYER_UI:STATUS='+json.dumps(value)+'\n'
        validate_active_heartbeat(encode(status),'current',100)
        for change in ({'session':'old'},{'at':96},{'text':'新娘阿花 | OFF\n'},{'expires_at':99}):
            with self.subTest(change=change),self.assertRaises(RuntimeError):
                validate_active_heartbeat(encode(status)+encode(dict(status,**change)),'current',100)


if __name__=='__main__':unittest.main()
