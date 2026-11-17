from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import collect_boss_skill_retry_session as collector


class RefusalRetentionTests(unittest.TestCase):
    def fixture(self):
        attempt='no verified 9m same-level movement clearance within 192 navigation queries\n'
        attempt+='\n'.join('OWNED_DESTROY_VERIFIED='+n+'|engine_unusable=true' for n in
            ('boss','boss_controller','target','target_controller'))+'\n'
        return ''.join('PBZ_CONTROL_LIFECYCLE:SPAWN_ATTEMPT='+str(i)+'\n'+attempt for i in range(1,4))+(
            'PREREQUISITE_RETRY_SAFE=true\nEND=initialization rejected before takeover; original player restoration verified\n')

    def test_clean_precondition_refusal_is_retained(self):
        collector.refused_before_extra_target(self.fixture())

    def test_any_takeover_or_missing_cleanup_rejected(self):
        for text in (self.fixture()+'enter success=true',self.fixture()+'ISSUE_',
                     self.fixture().replace('OWNED_DESTROY_VERIFIED=boss|','missing=boss|'),
                     self.fixture().replace('PREREQUISITE_RETRY_SAFE=true','')):
            with self.assertRaises(AssertionError):collector.refused_before_extra_target(text)


if __name__=='__main__':unittest.main()
