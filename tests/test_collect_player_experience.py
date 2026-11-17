import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from collect_player_experience import analyze, IDS


class ExperienceProofTests(unittest.TestCase):
    def fixture(self):
        raw='PLAYER_ENTRY_READY='+IDS[0]+'\n';records=[]
        def add(action,text):
            nonlocal raw
            records.append(dict(action=action,log_offset=len(raw)))
            raw+=text+'\n'
        add('enter','[PBZBossControl] enter success=true state=ACTIVE\nTARGET_CAMERA_LOCK=true|initial')
        add('shift_cast','[PBZBossControl] slot1 success=true state=ACTIVE\n'
            'KEY_SKILL_BEGIN=skill_01|target=owned|health=9000|active=1\n'
            'KEY_SKILL_END=skill_01|peak=1|active=0|natural=true|health_after=9000')
        add('exit','[PBZBossControl] exit success=true state=OFF reason=\n'
            'ORIGINAL_PLAYER_POSITION_DELTA=0\nORIGINAL_PLAYER_NEW_ACTIVE_COUNT=0\nCAMERA_CLEANUP_ENGINE_VERIFIED=true')
        return raw,records

    def test_partial_native_cast_is_not_complete_release(self):
        raw,records=self.fixture();result=analyze(raw,records)
        self.assertTrue(all(t['passed']for t in result['trials']))
        self.assertTrue(result['roles'][IDS[0]]['shift_movement_native_cast'])
        self.assertFalse(result['feature_trial_passed'])
        self.assertFalse(result['runtime_acceptance_current'])

    def test_next_input_cannot_complete_previous_cast_or_restore(self):
        raw,records=self.fixture()
        broken=raw.replace('KEY_SKILL_END=skill_01','KEY_SKILL_END=other')
        broken+='\nKEY_SKILL_END=skill_01|peak=1|active=0|natural=true|health_after=8000\n'
        self.assertFalse(analyze(broken,records)['trials'][1]['passed'])
        broken=raw.replace('ORIGINAL_PLAYER_NEW_ACTIVE_COUNT=0','ORIGINAL_PLAYER_NEW_ACTIVE_COUNT=1')
        self.assertFalse(analyze(broken,records)['trials'][-1]['passed'])

    def test_wrong_target_readback_or_fault_refused(self):
        raw,records=self.fixture();records.append(dict(action='cycle_target',log_offset=len(raw)))
        raw+='target_request success=true state=ACTIVE reason=requested; awaiting readback: owned1\ntarget verified: owned2\n'
        self.assertFalse(analyze(raw,records)['trials'][-1]['passed'])
        raw,records=self.fixture();raw+='state=FAULTED\n'
        self.assertFalse(analyze(raw,records)['trials'][-1]['passed'])


if __name__=='__main__':unittest.main()
