"""落点重试不能冒充多轮操控，也不能跳过旧对象回收。"""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from collect_boss_candidate_acceptance import candidate_interval


class CandidateIntervals(unittest.TestCase):
    def setUp(self):
        self.final=('PBZ_CONTROL_LIFECYCLE:SPAWN_ATTEMPT=2\n'
            'PBZ_CONTROL_LIFECYCLE:CANDIDATE_IDENTITY_READY=boss|class|config\n'
            'PBZ_CONTROL_LIFECYCLE:INTERACTIVE_READY=cleanup in 600 seconds\n')
        self.retry=('PBZ_CONTROL_LIFECYCLE:SPAWN_ATTEMPT=1\n'
            'PBZ_CONTROL_LIFECYCLE:CANDIDATE_IDENTITY_READY=boss|class|config\n'
            'INITIALIZATION_ATTEMPT_REJECTED=visibility\n'+''.join(
                'OWNED_DESTROY_VERIFIED='+label+'|engine_unusable=true\n'
                for label in ('boss','boss_controller','target','target_controller'))+
            'INITIALIZATION_RETRY=1\n')

    def test_cleaned_retry_is_separate_from_one_actual_assembly(self):
        offset,rejected=candidate_interval(self.retry+self.final,'boss')
        self.assertEqual(offset,len(self.retry));self.assertEqual(len(rejected),1)

    def test_unretired_or_previously_played_attempt_is_rejected(self):
        for earlier in (self.retry.replace('OWNED_DESTROY_VERIFIED=target|','REMOVED='),
                        self.retry+'[PBZBossControl] enter success=true\n',
                        self.retry+'CANDIDATE_LIVE_BINDING=prior\n'):
            with self.subTest(earlier=earlier),self.assertRaises(AssertionError):
                candidate_interval(earlier+self.final,'boss')

    def test_duplicate_interactive_or_wrong_identity_is_rejected(self):
        for raw in (self.retry+self.final+self.final,self.retry+self.final.replace('=boss|','=foreign|')):
            with self.subTest(raw=raw),self.assertRaises(AssertionError):candidate_interval(raw,'boss')


if __name__=='__main__':unittest.main()
