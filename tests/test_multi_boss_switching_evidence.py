"""双角色共用技能ID时拒绝串类、旧装配和伪造按键。"""
from pathlib import Path
import sys
import json
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from collect_multi_boss_switching import exact_role_proof,movement_camera_proof,retry_sources,CHECKS
from boss_adaptation_workflow import sha


class RoleEvidence(unittest.TestCase):
    def setUp(self):
        self.cls='/WanJun/GA_Heavy.GA_Heavy_C'
        self.prefix=('PBZ_CONTROL_LIFECYCLE:DEFERRED_ACTOR=boss\n'
            'GRANTED_ABILITY=Class '+self.cls+'\n'
            'PLAYER_BINDING=slot1|skill_01|F1\n'
            'PLAYER_ENTRY_READY=057_wanjun\n')
        self.body=('KEY_SKILL_BEGIN=skill_01|target=target|health=9000|active=1\n'
            'SKILL_INSTANCE=skill_01|active=true|cancelable=true|object=GA_Heavy_C /World.Boss.Instance\n'
            'KEY_SKILL_END=skill_01|peak=1|active=0|natural=true|health_before=9000|health_after=8800|distance=10\n')

    def check(self,prefix=None,body=None,expected=None):
        prefix=self.prefix if prefix is None else prefix
        body=self.body if body is None else body
        action={'skill':'skill_01','binding':{'slot':'slot1','skill':'skill_01','key':'F1'},
                'log_offset':len(prefix),'log_end':len(prefix+body)}
        return exact_role_proof(prefix+body,action,'057_wanjun',expected or self.cls)

    def test_current_exact_registered_class_passes(self):
        self.assertTrue(self.check()['natural_completion'])

    def test_same_id_foreign_class_rejected(self):
        with self.assertRaises(AssertionError):self.check(expected='/Ahua/GA_Heavy.GA_Heavy_C')
        with self.assertRaises(AssertionError):self.check(body=self.body.replace('GA_Heavy_C','GA_Ahua_C'))

    def test_pending_or_other_role_and_wrong_binding_rejected(self):
        for prefix in (self.prefix.replace('PLAYER_ENTRY_READY=057_wanjun','WORKBENCH_BOSS_SELECTED=057_wanjun'),
                       self.prefix.replace('=057_wanjun','=ahua_guitoudao'),
                       self.prefix.replace('|F1','|F2'),self.prefix+'PLAYER_ENTRY_READY=057_wanjun\n'):
            with self.subTest(prefix=prefix),self.assertRaises(AssertionError):self.check(prefix=prefix)

    def test_actual_movement_and_both_camera_readbacks_required(self):
        text=('CAMERA_CONTROL_YAW=1\nCAMERA_ARM_YAW=1\n'
              'CAMERA_CONTROL_YAW=2\nCAMERA_ARM_YAW=2\nCONTROLLED_BOSS_POSITION_DELTA=30\n')
        self.assertTrue(movement_camera_proof(text)['passed'])
        for altered in (text.replace('DELTA=30','DELTA=0'),text.replace('ARM_YAW=2','ARM_YAW=1'),
                        text+'KEY_SKILL_BEGIN=skill_01|',text.replace('DELTA=30','DELTA=1e999')):
            with self.subTest(altered=altered):self.assertFalse(movement_camera_proof(altered)['passed'])


class RetryEvidence(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.work=Path(self.temp.name)
        self.raw='initial\nresume\nCAMERA_ARM_YAW=2\nWORKBENCH_INPUT_LOCKED=2\n'
        self.path=self.work/'multi-boss-switching-camera-first-attempt.json'
        self.previous={'passed':False,'error':'ordinary WanJun actual movement/camera change not verified',
            'checks':CHECKS[:3],'state_file':'state.json','log_offset':0,'log_end':8,'lines':['initial']}
        self.path.write_text(json.dumps(self.previous),encoding='utf-8')
        self.actions={'state_file':'state.json','log_offset':0,'log_end':len(self.raw),
            'resumed_from':self.path.name,'resumed_from_sha256':sha(self.path),
            'resume_log_offset':8,'camera_after_input_offset':15}

    def test_exact_failed_prefix_and_fresh_camera_accepted(self):
        self.assertEqual(retry_sources(self.actions,self.work,self.raw),[self.path])

    def test_missing_or_modified_first_attempt_rejected(self):
        self.path.write_text('{}',encoding='utf-8')
        with self.assertRaises(AssertionError):retry_sources(self.actions,self.work,self.raw)
        self.path.unlink()
        with self.assertRaises(FileNotFoundError):retry_sources(self.actions,self.work,self.raw)

    def test_old_sample_and_foreign_failure_rejected(self):
        self.actions['camera_after_input_offset']=self.raw.index('WORKBENCH_INPUT_LOCKED=')
        with self.assertRaises(AssertionError):retry_sources(self.actions,self.work,self.raw)
        self.actions['camera_after_input_offset']=15
        self.previous['error']='runtime fault'
        self.path.write_text(json.dumps(self.previous),encoding='utf-8')
        self.actions['resumed_from_sha256']=sha(self.path)
        with self.assertRaises(AssertionError):retry_sources(self.actions,self.work,self.raw)

    def test_raw_prefix_tampering_rejected(self):
        with self.assertRaises(AssertionError):retry_sources(self.actions,self.work,self.raw.replace('initial','changed'))

    def entry_fixture(self,extra=''):
        prefix=('PLAYER_ENTRY_READY=057_wanjun\n'
            '[PBZBossControl] enter success=false state=OFF reason=capture failed before mutation: '
            'stop moving before entering boss control; velocity=3,0,0\n'+extra)
        self.raw=prefix+'resume\nCAMERA_ARM_YAW=2\nWORKBENCH_INPUT_LOCKED=2\n'
        self.path=self.work/'multi-boss-switching-entry-first-attempt.json'
        self.previous.update(error='skill_01: Entry not verified\n',checks=CHECKS[:2],
            log_end=len(prefix),lines=prefix.splitlines())
        self.path.write_text(json.dumps(self.previous),encoding='utf-8')
        self.actions.update(resumed_from=self.path.name,resumed_from_sha256=sha(self.path),
            log_end=len(self.raw),resume_log_offset=len(prefix),camera_after_input_offset=len(prefix)+7)

    def test_undispatched_stationary_refusal_can_resume_same_role(self):
        self.entry_fixture()
        self.assertEqual(retry_sources(self.actions,self.work,self.raw),[self.path])

    def test_entry_resume_rejects_dispatch_switch_or_fault(self):
        for extra in ('KEY_SKILL_BEGIN=skill_01\n','enter success=true\n',
                      'PLAYER_ENTRY_READY=ahua_guitoudao\n','WORKBENCH_BOSS_SELECTED=ahua_guitoudao\n',
                      'state=FAULTED\n','PBZ_CONTROL_RESTORE:FAILED=bad\n'):
            self.entry_fixture(extra)
            with self.subTest(extra=extra),self.assertRaises(AssertionError):
                retry_sources(self.actions,self.work,self.raw)

    def completion_fixture(self,extra='',reason='stop moving before entering boss control; velocity=3,0,0'):
        prefix='PLAYER_ENTRY_READY=ahua_guitoudao\nenter success=false '+reason+'\n'+extra
        self.raw=prefix+'fresh Ahua validation\n'
        self.path=self.work/'multi-boss-switching-ahua-settling-attempt.json'
        self.previous={'passed':False,'error':'skill_01: Entry not verified\n','checks':CHECKS[:4],
            'state_file':'state.json','log_offset':0,'log_end':len(prefix),'lines':prefix.splitlines()}
        self.path.write_text(json.dumps(self.previous),encoding='utf-8')
        self.actions={'state_file':'state.json','log_offset':0,'log_end':len(self.raw),
            'completion_resumed_from':self.path.name,'completion_resumed_from_sha256':sha(self.path),
            'completion_resume_log_offset':len(prefix)}

    def test_completion_only_resumes_preserved_stationary_refusal(self):
        self.completion_fixture()
        self.assertEqual(retry_sources(self.actions,self.work,self.raw),[self.path])

    def test_completion_rejects_dead_actor_dispatch_switch_fault_and_altered_receipt(self):
        self.completion_fixture(reason='living control participants required')
        with self.assertRaises(AssertionError):retry_sources(self.actions,self.work,self.raw)
        for extra in ('KEY_SKILL_BEGIN=skill_01\n','enter success=true\n','PLAYER_ENTRY_READY=ahua_guitoudao\n',
                      'WORKBENCH_BOSS_SELECTED=057_wanjun\n','state=FAULTED\n','PBZ_CONTROL_RESTORE:FAILED=bad\n'):
            self.completion_fixture(extra)
            with self.subTest(extra=extra),self.assertRaises(AssertionError):retry_sources(self.actions,self.work,self.raw)
        self.completion_fixture();self.actions['completion_resumed_from_sha256']='wrong'
        with self.assertRaises(AssertionError):retry_sources(self.actions,self.work,self.raw)


if __name__=='__main__':unittest.main()
