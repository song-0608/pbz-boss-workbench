import copy
import json
from pathlib import Path
import re
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from collect_youlong_attempt import ROOT,actions_proof,candidate_interval


class YouLongActionProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work=ROOT/'evidence/official-validation/20261116-073449'
        cls.raw=(cls.work/'UE4SS.log').read_text(encoding='utf-8',errors='replace')
        cls.actions=json.loads((cls.work/'player-extra-skill-actions.json').read_text(encoding='utf-8'))
        cls.state=str(ROOT/'runtime/official-validation-20261116-073449/state.json')
        cls.begin,_=candidate_interval(cls.raw,'056_youlong')
        cls.bindings=dict(re.findall(r'CANDIDATE_LIVE_BINDING=056_youlong\|([^|\r\n]+)\|([^\r\n]+)',cls.raw[cls.begin:]))

    def check(self,actions=None,bindings=None,raw=None):
        return actions_proof(raw or self.raw,actions if actions is not None else self.actions,self.state,
            self.begin,bindings if bindings is not None else self.bindings)

    def test_eight_real_native_actions_reparse(self):
        result=self.check();self.assertEqual(len(result),8)
        self.assertTrue(all(r['local_displacement_verified']and r['activation_instance_verified']for r in result))

    def test_omitted_duplicate_or_changed_action_refused(self):
        variants=[self.actions[:-1],self.actions+[self.actions[0]]]
        for field,value in (('passed',False),('cast_dispatched',False),('state_file','foreign'),
                            ('lines',['changed']),('log_end',self.actions[0]['log_end']-2)):
            data=copy.deepcopy(self.actions);data[0][field]=value;variants.append(data)
        for i,actions in enumerate(variants):
            with self.subTest(i=i),self.assertRaises(AssertionError):self.check(actions)

    def test_wrong_native_class_or_registered_key_refused(self):
        bindings=dict(self.bindings);bindings['skill_01']='/Foreign.Ability_C'
        with self.assertRaises(AssertionError):self.check(bindings=bindings)
        actions=copy.deepcopy(self.actions);actions[0]['binding']['key']='F12'
        with self.assertRaises(AssertionError):self.check(actions)


if __name__=='__main__':unittest.main()
