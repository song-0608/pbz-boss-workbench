"""初始化耗时不能挤掉十分钟交互，也不能突破总会话期限。"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from practice_lease import issue_expiry, INTERACTIVE_SECONDS, CLEANUP_SECONDS


class LeaseTests(unittest.TestCase):
    def test_new_practice_reserves_full_interactive_window(self):
        expiry = issue_expiry(1000, 2200, practice=True)
        for initialization in (0, 38, 120):
            self.assertEqual(min(INTERACTIVE_SECONDS, expiry - (1000 + initialization) - CLEANUP_SECONDS), 600)

    def test_session_deadline_always_wins(self):
        self.assertEqual(issue_expiry(1000, 1400, practice=True), 1370)

    def test_short_experiments_keep_their_original_limits(self):
        self.assertEqual(issue_expiry(1000, 2200), 1045)
        self.assertEqual(issue_expiry(1000, 2200, remote=True), 1090)

    def test_no_expired_or_nonfinite_grant(self):
        for now, deadline in ((1000, 1029), (1000, 1030), (float('nan'), 2200), (1000, float('inf'))):
            with self.assertRaises(ValueError):
                issue_expiry(now, deadline, practice=True)

    def test_integer_expiry_never_exceeds_session_margin(self):
        self.assertEqual(issue_expiry(1000.8, 1400.9, practice=True), 1370)


if __name__ == '__main__':
    unittest.main()
