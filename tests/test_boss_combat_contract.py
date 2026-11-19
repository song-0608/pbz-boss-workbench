from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import boss_combat_contract as contract


def function(name,parameters,native=False):
    return dict(name=name,flags=hex(0x400 if native else 0),parameter_count=len(parameters),
        parameters=[dict(name=n,type=t,array_dim=1,property_flags='0x80') for n,t in parameters])


def fixture():
    cue=dict(path=contract.CUE,super='/Script/LegoAbility.LGAAction_Executable',
        properties=[dict(name=n,type='ArrayProperty',element_size=16) for n in ('Cascade Comps','Niagara Comps')],
        functions=[function('Spawn Particles',[('Avatar','ObjectProperty')]),function('End Particles',[]),
            function('Received_ActionBegin',[(n,'FloatProperty') for n in ('ElapsedTime','TotalDuration','BeginTime')]),
            function('Received_ActionEnd',[(n,'BoolProperty') for n in ('bAbilityFinished','bActionFinished')])])
    return dict(pid=42,state_file='lease',reflection_ready=True,source_sha256='source',
        gameplay_called=False,input_sent=False,grants_changed=False,tags_changed=False,runtime_behavior_verified=False,
        classes=[cue,dict(path=contract.NPC,
            super='/PBZDeflectSystem/Abilities/BP_StanceAction_Base.BP_StanceAction_Base_C'),
            dict(path='/Script/LegoAbility.LGAAction',functions=[function('GetAvatarActor',[('ReturnValue','ObjectProperty')],True)]),
            dict(path='/Script/GameplayAbilities.GameplayAbility',functions=[function('K2_CancelAbility',[],True)])])


class ContractTests(unittest.TestCase):
    def check_report(self,r):
        with patch.object(contract,'sha',return_value='source'):
            return contract.validate(r,42,'lease')

    def test_exact_current_declarations_are_not_gameplay_acceptance(self):
        c=self.check_report(fixture())
        self.assertTrue(c['declaration_verified'])
        self.assertNotIn('cue_render_verified',c)
        self.assertNotIn('script_gate_verified',c)

    def test_old_process_source_and_mutated_reports_are_rejected(self):
        for key,value in [('pid',43),('state_file','old'),('source_sha256','old'),
            ('reflection_ready',False),('gameplay_called',True)]:
            r=fixture();r[key]=value
            with self.subTest(key=key),self.assertRaises(AssertionError):self.check_report(r)

    def test_native_script_kind_and_precise_parameters_are_required(self):
        for mode in ('native','parameter','count','array','ancestry','duplicate'):
            r=fixture();cue=r['classes'][0]
            if mode=='native':cue['functions'][0]['flags']='0x400'
            elif mode=='parameter':cue['functions'][0]['parameters'][0]['type']='StructProperty'
            elif mode=='count':cue['functions'][0]['parameter_count']=0
            elif mode=='array':cue['properties'][0]['element_size']=8
            elif mode=='ancestry':cue['super']='/Fake'
            else:r['classes'].append(cue)
            with self.subTest(mode=mode),self.assertRaises(AssertionError):self.check_report(r)


if __name__=='__main__':unittest.main()
