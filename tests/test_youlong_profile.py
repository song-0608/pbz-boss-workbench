import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import build_youlong_profile as profile


class YouLongProfileTests(unittest.TestCase):
    def report(self):
        prefix='/PBZCombatAsset/ActorData/Mobs/056_YouLong/Ability/Abilities/GA_YouLong_'
        return {'id':'056_youlong','target_build_sha256':profile.BUILD,'base_control_accepted':True,'playable':False,
            'stability':{'passed':True},'cleanup':{k:True for k in
                ('boss','boss_controller','target','target_controller','extra_target','extra_target_controller')},
            'movement_camera':{k:True for k in('movement_verified','camera_rotation_verified','milestone_passed')},
            'accepted_skills':{skill:{'class_path':prefix+native+'.GA_YouLong_'+native+'_C',
                'natural_completion_verified':True,'cancellation_runtime_verified':True,
                'gameplay_verified':False,'movement_runtime_verified':True}for _,skill,_,_,native in profile.SLOTS}}

    def test_four_independent_native_actions_required(self):
        self.assertEqual(len(profile.validate_report(self.report())),4)
        for change in ('missing','foreign','duplicate','natural','cancel','effect'):
            value=self.report();skills=value['accepted_skills']
            if change=='missing':del skills['dash']
            elif change=='foreign':skills['skill_01']['class_path']='/Foreign.Ability_C'
            elif change=='duplicate':skills['dash']=copy.deepcopy(skills['skill_02'])
            elif change=='natural':skills['skill_01']['natural_completion_verified']=False
            elif change=='cancel':skills['skill_01']['cancellation_runtime_verified']=False
            else:skills['skill_01']['movement_runtime_verified']=False
            with self.subTest(change=change),self.assertRaises(AssertionError):profile.validate_report(value)

    def test_stability_cleanup_motion_and_scope_required(self):
        for section,field in (('stability','passed'),('cleanup','target'),('movement_camera','camera_rotation_verified')):
            value=self.report();value[section][field]=False
            with self.subTest(section=section),self.assertRaises(AssertionError):profile.validate_report(value)
        value=self.report();value['playable']=True
        with self.assertRaises(AssertionError):profile.validate_report(value)


if __name__=='__main__':unittest.main()
