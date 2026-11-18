import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from player_travel_capture import verify_partial
from player_travel_ui_stage import initialization
from tests.test_player_travel_ui_stage import READY


class TravelCaptureTests(unittest.TestCase):
    def test_exact_idle_partial_capture_only(self):
        receipt = dict(research_pid=123, state_file='exact', workflow_sha256='frozen')
        captured = dict(receipt, lines=READY.splitlines(), bindings=initialization(READY),
            initialization_observed=True, runtime_acceptance_current=False)
        verify_partial(captured, receipt, READY + '\nread-only performance sample')
        for key, value in (('research_pid', 456), ('bindings', []), ('lines', ['unrelated']),
                           ('runtime_acceptance_current', True)):
            other = copy.deepcopy(captured); other[key] = value
            with self.subTest(key=key), self.assertRaises(AssertionError):
                verify_partial(other, receipt, READY)
        with self.assertRaises(AssertionError):
            verify_partial(captured, receipt, READY + '\n[PBZBossControl] enter success=true state=ACTIVE')


if __name__ == '__main__':
    unittest.main()
