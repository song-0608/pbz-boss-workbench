import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from player_experience_focus import analyze,TAGS
from collect_auto_world_reassembly import proof


class FocusProofTests(unittest.TestCase):
    def fixture(self):
        rows=[dict(path=str(i),address=hex(i+1),health=100,position=[0,0,0])for i in range(4)]
        samples=[dict(tag=tag,state_file='owned',candidate_manifest_sha256='a'*64,
            foreground_game=index in (0,3),at=100+index*4,log_offset=index,participants=copy.deepcopy(rows))
            for index,tag in enumerate(TAGS)]
        raw='abc[PBZBossControl] exit success=true state=OFF reason=\nORIGINAL_PLAYER_POSITION_DELTA=0\n'
        raw+='ORIGINAL_PLAYER_NEW_ACTIVE_COUNT=0\nCAMERA_CLEANUP_ENGINE_VERIFIED=true\n'
        return samples,raw

    def test_idle_focus_roundtrip_does_not_claim_held_key_release(self):
        samples,raw=self.fixture();result=analyze(samples,raw)
        self.assertTrue(result['passed']);self.assertFalse(result['held_key_release_tested'])

    def test_unobserved_background_or_replaced_actor_rejected(self):
        for mode in ('focus','actor','health','duration'):
            samples,raw=self.fixture()
            if mode=='focus':samples[1]['foreground_game']=True
            if mode=='actor':samples[2]['participants'][0]['address']='0xdead'
            if mode=='health':samples[2]['participants'][0]['health']=90
            if mode=='duration':samples[2]['at']=samples[1]['at']+.5
            with self.subTest(mode=mode),self.assertRaises(AssertionError):analyze(samples,raw)

    def test_drift_and_incomplete_native_restoration_fail(self):
        samples,raw=self.fixture();samples[2]['participants'][1]['position']=[20,0,0]
        self.assertFalse(analyze(samples,raw)['passed'])
        samples,raw=self.fixture();self.assertFalse(analyze(samples,raw.replace('CAMERA_CLEANUP_ENGINE_VERIFIED=true',''))['passed'])

    def test_world_proof_cannot_accept_only_ready_or_static_identity(self):
        self.assertFalse(proof('PLAYER_ENTRY_READY=ahua\nPLAYER_ENTRY_READY=ahua\n')['passed'])


if __name__=='__main__':unittest.main()
