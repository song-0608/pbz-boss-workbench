"""完整发布不能借旧源码、缺失按键、离散ACTIVE或未闭环载图记录过关。"""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from collect_release_readiness import evaluate


class ReleaseTests(unittest.TestCase):
    def fixture(self):
        bindings=[{'slot':str(i),'skill':str(i),'key':str(i)} for i in range(28)]
        bindings.append({'slot':'primary','skill':'0','key':'mouse'})
        skills=[{'skill':str(i),'natural_completion':{'active':0},'restoration':{'passed':True},
                 'active_cancel_and_restoration':True} for i in range(28)]
        return skills,bindings

    def test_all_required_evidence(self):
        skills,bindings=self.fixture()
        self.assertTrue(evaluate(skills,True,True,bindings,bindings,True,True)['ready_for_release'])

    def test_each_lifecycle_and_source_gate_is_required(self):
        skills,bindings=self.fixture()
        for index in (1,2,5,6):
            args=[skills,True,True,bindings,bindings,True,True];args[index]=False
            with self.subTest(index=index):self.assertFalse(evaluate(*args)['ready_for_release'])

    def test_primary_shortcut_and_every_ability_are_required(self):
        skills,bindings=self.fixture()
        for actions,actual in ((skills[:-1],bindings),(skills,bindings[:-1])):
            self.assertFalse(evaluate(actions,True,True,actual,bindings,True,True)['ready_for_release'])

    def test_natural_finish_without_restoration_cannot_pass(self):
        skills,bindings=self.fixture();skills[0]['restoration']['passed']=False
        self.assertEqual(evaluate(skills,True,True,bindings,bindings,True,True)['missing_natural'],['0'])


if __name__=='__main__':unittest.main()
