import ast
import inspect
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import prepare_offline_acceptance as entry


class PreparationTests(unittest.TestCase):
    def test_only_duration_guard_differs_from_frozen_preparation(self):
        original = inspect.getsource(entry.validation.prepare)
        self.assertEqual(entry.render().replace(entry.NEW, entry.OLD), original)

    def test_long_duration_requires_offline_without_client_network(self):
        function = ast.parse(entry.render()).body[0]
        guard = next(row for row in function.body if isinstance(row, ast.If)).test
        code = compile(ast.Expression(guard), '<duration guard>', 'eval')
        for duration in (12, 20, 40, 0, 21, 41, 60):
            for offline in (False, True):
                for network in (False, True):
                    refused = eval(code, {}, dict(lease_minutes=duration,
                        offline_validation=offline, client_network=network))
                    allowed = duration == 12 or duration in (20, 40) and offline and not network
                    self.assertEqual(refused, not allowed)

    def test_failure_restores_original_preparation_and_cannot_reissue(self):
        original = entry.validation.prepare
        with patch.object(entry.practice, 'prepare', side_effect=RuntimeError('Existing session preserved')):
            with self.assertRaisesRegex(RuntimeError, 'Existing session'):
                entry.prepare()
        self.assertIs(entry.validation.prepare, original)


if __name__ == '__main__':
    unittest.main()
