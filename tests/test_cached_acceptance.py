import importlib
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import run_four_boss_cached_acceptance as runner


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'tools').mkdir()
        self.source = self.root / 'tools/source.lua'
        self.source.write_text('one', encoding='utf-8')
        self.calls = 0

        def calculate():
            self.calls += 1
            return {'source': self.source.read_text(encoding='utf-8'), 'rows': []}

        self.original = calculate
        self.builder = types.ModuleType('test_pure_builder')
        self.builder.expected = calculate
        self.alias = types.ModuleType('test_pure_alias')
        self.alias.base_expected = calculate
        self.modules = patch.dict(sys.modules, {self.builder.__name__: self.builder,
                                                self.alias.__name__: self.alias})
        self.modules.start(); self.addCleanup(self.modules.stop)
        self.names = patch.object(runner, 'BUILDERS', (self.builder.__name__,))
        self.names.start(); self.addCleanup(self.names.stop)

    def test_aliases_share_calculation_and_results_are_isolated(self):
        with runner.calculation_cache(self.root):
            first = self.builder.expected()
            first['rows'].append('mutation')
            self.assertEqual(self.alias.base_expected(), {'source': 'one', 'rows': []})
            self.assertEqual(self.calls, 1)
        self.assertIs(self.alias.base_expected, self.original)

    def test_changed_input_rejects_cached_verification(self):
        with self.assertRaisesRegex(AssertionError, 'inputs changed'):
            with runner.calculation_cache(self.root):
                self.builder.expected()
                self.source.write_text('two', encoding='utf-8')
        self.assertIs(self.builder.expected, self.original)

    def test_exception_restores_original_calculators(self):
        with self.assertRaisesRegex(RuntimeError, 'failed gate'):
            with runner.calculation_cache(self.root):
                self.alias.base_expected()
                raise RuntimeError('failed gate')
        self.assertIs(self.builder.expected, self.original)
        self.assertIs(self.alias.base_expected, self.original)


if __name__ == '__main__':
    unittest.main()
