"""稳定性证据拒绝不足时长、心跳中断、错会话与旧恢复回读。"""
from datetime import datetime, timedelta
from pathlib import Path
import json
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from collect_practice_stability import proof


class StabilityTests(unittest.TestCase):
    session = '20261114-150000'

    def fixture(self, seconds=600):
        start = datetime(2026, 11, 14, 15)
        def line(at, content):
            return '['+(start+timedelta(seconds=at)).isoformat(sep=' ')+'] '+content+'\n'
        text = line(0, 'PBZ_CONTROL_LIFECYCLE:INTERACTIVE_READY=cleanup in 600 seconds')
        text += line(0, '[PBZBossControl] enter success=true state=ACTIVE reason=')
        for at in range(seconds):
            if at == seconds - 10:
                text += line(at, '[PBZBossControl] exit success=true state=OFF reason=user exit')
                text += line(at, 'ORIGINAL_PLAYER_POSITION_DELTA=0.0')
                text += line(at, 'ORIGINAL_PLAYER_NEW_ACTIVE_COUNT=0')
                text += line(at, 'CAMERA_CLEANUP_ENGINE_VERIFIED=true')
            status = {'at': 1000+at, 'expires_at': 2000, 'session': 'official-validation-'+self.session,
                      'player': 'Player /Game/Test', 'text': '新娘阿花 | '+('ACTIVE' if at < seconds-10 else 'OFF')+'\n生命 9000'}
            text += line(at, 'PBZ_PLAYER_UI:STATUS='+json.dumps(status, ensure_ascii=False))
        return text+line(seconds, 'PBZ_CONTROL_LIFECYCLE:INTERACTIVE_END=bounded input probe complete')

    def test_full_window_and_restoration(self):
        result = proof(self.fixture(), self.session)
        self.assertTrue(result['passed'])
        self.assertEqual(result['elapsed_seconds'], 600)

    def test_572_seconds_cannot_be_rounded_up(self):
        self.assertFalse(proof(self.fixture(572), self.session)['passed'])

    def test_heartbeat_outage_is_not_continuous_running(self):
        text = '\n'.join(line for line in self.fixture().splitlines() if not ('15:03:' in line))
        self.assertFalse(proof(text, self.session)['passed'])

    def test_wrong_session_invalid_status_and_faults(self):
        text = self.fixture()
        for altered in (text.replace('official-validation-'+self.session, 'other-session', 1),
                        text.replace('"at": 1000', '"at": "invalid"', 1),
                        text.replace('bounded input probe complete', 'state=FAULTED')):
            self.assertFalse(proof(altered, self.session)['passed'])

    def test_last_entry_cannot_borrow_previous_restoration(self):
        text = self.fixture().replace('PBZ_CONTROL_LIFECYCLE:INTERACTIVE_END=',
            '[PBZBossControl] enter success=true state=ACTIVE reason=\n[2026-11-14 15:10:00] PBZ_CONTROL_LIFECYCLE:INTERACTIVE_END=')
        self.assertFalse(proof(text, self.session)['passed'])

    def test_extra_assembly_and_missing_readback_fail(self):
        text = self.fixture()
        for altered in (text + text, text.replace('CAMERA_CLEANUP_ENGINE_VERIFIED=true', 'CAMERA_REMOVED')):
            self.assertFalse(proof(altered, self.session)['passed'])

    def test_separate_active_periods_cannot_be_added_as_continuous_time(self):
        lines = self.fixture().splitlines()
        for i, line in enumerate(lines):
            if 'PBZ_PLAYER_UI:STATUS=' in line:
                prefix, encoded = line.split('PBZ_PLAYER_UI:STATUS=', 1)
                row = json.loads(encoded)
                if (row['at'] - 1000) % 100 == 99:
                    row['text'] = '新娘阿花 | OFF\n'
                    lines[i] = prefix + 'PBZ_PLAYER_UI:STATUS=' + json.dumps(row, ensure_ascii=False)
        result = proof('\n'.join(lines), self.session)
        self.assertGreater(result['active_span_seconds'], 300)
        self.assertLess(result['longest_continuous_active_seconds'], 100)
        self.assertFalse(result['passed'])


if __name__ == '__main__':
    unittest.main()
