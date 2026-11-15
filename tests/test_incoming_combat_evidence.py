"""合成证据夹具：拒绝仅掉血、Kill、手动恢复和缺失清理，不是实机证据。"""
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from collect_incoming_combat import proof

FIXTURE = '''INCOMING_COMBAT_BEGIN=health=9000.0|sources=2|seconds=360
INCOMING_COMBAT_CAST=BP_Monster_AHua_GuiTouDao_C owned_1|skill=skill_07|number=1|active=1
INCOMING_COMBAT_CAST=BP_Monster_AHua_GuiTouDao_C owned_2|skill=skill_07|number=1|active=1
OWNED_COMBAT_HEALTH=before=9000.0|after=450.0
OWNED_COMBAT_HEALTH=before=450.0|after=0.0
INCOMING_COMBAT_STOP=all_source_abilities_inactive=true
[PBZBossControl] auto_exit success=true state=OFF reason=boss health depleted
ORIGINAL_PLAYER_POSITION_DELTA=0.0
ORIGINAL_PLAYER_NEW_ACTIVE_COUNT=0
CAMERA_CLEANUP_ENGINE_VERIFIED=true
'''


class EvidenceTests(unittest.TestCase):
    def test_complete_sequence(self):
        self.assertTrue(proof(FIXTURE)['passed'])

    def test_damage_alone_or_manual_exit_is_insufficient(self):
        for old, new in (('after=0.0', 'after=1.0'), ('auto_exit', 'exit'),
                         ('reason=boss health depleted', 'reason=owned boss disposed'),
                         ('before=450.0', 'before=400.0')):
            with self.subTest(old=old):
                self.assertFalse(proof(FIXTURE.replace(old, new))['passed'])

    def test_missing_or_late_cleanup(self):
        stop = 'INCOMING_COMBAT_STOP=all_source_abilities_inactive=true\n'
        for text in (FIXTURE.replace(stop, ''), FIXTURE.replace(stop, '') + stop,
                     FIXTURE.replace('CAMERA_CLEANUP_ENGINE_VERIFIED=true', '')):
            self.assertFalse(proof(text)['passed'])

    def test_kill_fault_or_duplicate_cast(self):
        for text in (FIXTURE + 'OWNED_DEATH_TRIAL_KILL_REQUESTED=true',
                     FIXTURE + 'state=FAULTED', FIXTURE + 'ISSUE_INCOMING_COMBAT=failure',
                     FIXTURE.replace('owned_2', 'owned_1')):
            self.assertFalse(proof(text)['passed'])

    def test_post_restore_changes_only_snapshot_requires_complete_window(self):
        text = FIXTURE + '''INCOMING_COMBAT_SNAPSHOT=stopped|player_health=808.000000|position=0
INCOMING_COMBAT_POST_RESTORE_BEGIN=seconds=60
INCOMING_COMBAT_POST_RESTORE_END=true
'''
        self.assertTrue(proof(text)['post_restore_stability_verified'])
        self.assertFalse(proof(text.replace('INCOMING_COMBAT_POST_RESTORE_END=true', ''))['post_restore_stability_verified'])
        self.assertFalse(proof(text + 'INCOMING_COMBAT_SNAPSHOT=after_restore|player_health=700.000000|position=0')['post_restore_stability_verified'])


if __name__ == '__main__':
    unittest.main()
