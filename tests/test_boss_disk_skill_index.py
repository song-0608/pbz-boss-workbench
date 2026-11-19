from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import boss_disk_skill_index as skills

PACKAGE='/PBZCombatAsset/ActorData/Mobs/057_WanJun/Ability/GA_Test'


def ref(kind,name,index):
    return dict(ObjectName=f"{kind}'{name}'",ObjectPath=PACKAGE+'.'+str(index))


def fixture():
    return [dict(Type='GA_Test_C',Name='Default__GA_Test_C',Properties={'Cost':3}),
        dict(Type='LGAAction_PlayMontage',Name='Play',Properties={'MontageToPlay':
            dict(ObjectName="AnimMontage'NativeMontage'",ObjectPath='/HuaShira/Animations/NativeMontage.0')}),
        dict(Type='LGATimeline',Name='Main',Properties={'Actions':[
            dict(StartTime=0.0,duration=2.0,TrackIndex=0,
                 Action=ref('LGAAction_PlayMontage','GA_Test_C:Main.Play',1)),
            dict(StartTime=0.5,duration=0.0,TrackIndex=1,
                 Action=ref('LGAAction_PlayMontage','GA_Test_C:Main.Play',1))]}),
        dict(Type='LegoAbilityBlueprintGeneratedClass',Name='GA_Test_C',Package=PACKAGE,
             ClassDefaultObject=ref('GA_Test_C','Default__GA_Test_C',0),
             Properties={'AbilityTimelines':[ref('LGATimeline','GA_Test_C:Main',2)]})]


class SkillIndexTests(unittest.TestCase):
    def test_serialized_timeline_order_and_overlap_preserved(self):
        row,=skills.abilities(fixture(),PACKAGE)
        self.assertEqual(row['issues'],[])
        self.assertEqual(row['serialized_cdo_properties'],{'Cost':3})
        timeline,=row['timelines']
        self.assertEqual([a['start_seconds'] for a in timeline['actions']],[0.0,0.5])
        self.assertEqual([a['track'] for a in timeline['actions']],[0,1])
        self.assertEqual(timeline['declared_end_seconds'],2.0)
        self.assertTrue(all(a['action_resolved'] for a in timeline['actions']))
        self.assertFalse(row['declared_end_is_runtime_completion'])
        self.assertFalse(row['live_grant_verified'])
        self.assertFalse(row['playable'])

    def test_export_index_must_match_both_name_and_type(self):
        exports=fixture()
        self.assertIsNone(skills.resolve_local(ref('Other','GA_Test_C:Main.Play',1),PACKAGE,exports))
        self.assertIsNone(skills.resolve_local(ref('LGAAction_PlayMontage','Other',1),PACKAGE,exports))
        foreign=ref('LGAAction_PlayMontage','GA_Test_C:Main.Play',1)
        foreign['ObjectPath']='/Other/GA_Test.1'
        self.assertIsNone(skills.resolve_local(foreign,PACKAGE,exports))
        self.assertIsNone(skills.resolve_local(ref('LGAAction_PlayMontage','Play',99),PACKAGE,exports))

    def test_missing_or_invalid_timing_never_invents_default(self):
        for bad in (None,True,float('nan'),float('inf')):
            exports=fixture()
            exports[2]['Properties']['Actions'][0]['StartTime']=bad
            row,=skills.abilities(exports,PACKAGE)
            timeline,=row['timelines']
            self.assertIsNone(timeline['declared_end_seconds'])
            self.assertFalse(timeline['actions'][0]['timing_fields_valid'])
            self.assertTrue(row['issues'])

    def test_unresolved_timeline_and_cdo_stay_explicit(self):
        exports=fixture()
        exports[3]['ClassDefaultObject']=ref('Wrong','Default__GA_Test_C',0)
        exports[3]['Properties']['AbilityTimelines']=[ref('LGATimeline','Unknown',2)]
        row,=skills.abilities(exports,PACKAGE)
        self.assertIsNone(row['serialized_cdo_properties'])
        self.assertEqual(row['timelines'],[])
        self.assertEqual(len(row['issues']),2)

    def test_reference_pointers_preserve_exact_native_values(self):
        value={'a/b':[{'x~y':ref('LGATimeline','GA_Test_C:Main',2)}]}
        row,=list(skills.references(value))
        self.assertEqual(row['pointer'],'/a~1b/0/x~0y')
        self.assertEqual(row['ObjectPath'],PACKAGE+'.2')

    def test_only_actual_serialized_generated_ability_classes(self):
        exports=fixture()
        exports.append(dict(Type='Texture2D',Name='GA_Fake_C'))
        exports.append(dict(Type='BlueprintGeneratedClass',Name='BP_Fake_C'))
        self.assertEqual(len(skills.abilities(exports,PACKAGE)),1)
        self.assertEqual(skills.package_name(skills.MOUNT+'ActorData/Mobs/057_WanJun/Ability/GA_Test.uasset'),PACKAGE)

    def test_case_only_native_identity_is_preserved(self):
        exports=fixture()
        exports[3]['Package']=PACKAGE.replace('Ability','ability')
        row,=skills.abilities(exports,PACKAGE)
        self.assertEqual(row['issues'],[])
        self.assertEqual(row['class_path'],exports[3]['Package']+'.GA_Test_C')
        exports[3]['Package']='/Other/GA_Test'
        row,=skills.abilities(exports,PACKAGE)
        self.assertIsNone(row['class_path'],'a mismatched source must never invent a local class path')

    def test_native_negative_preroll_is_preserved(self):
        exports=fixture()
        exports[2]['Properties']['Actions'][0]['StartTime']=-2.9802322e-08
        row,=skills.abilities(exports,PACKAGE)
        self.assertEqual(row['issues'],[])
        action=row['timelines'][0]['actions'][0]
        self.assertEqual(action['start_seconds'],-2.9802322e-08)
        self.assertTrue(action['has_pre_roll'])


if __name__=='__main__':
    unittest.main()
