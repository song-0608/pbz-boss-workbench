import ast
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import collect_yanqiansui_dense_terrain as collector
from build_yanqiansui_dense_candidate import verify


class CollectionTests(unittest.TestCase):
    def test_all_historical_refusal_gates_are_identical(self):
        rendered = collector.render()
        ast.parse(rendered)
        restored = rendered
        for before, after in reversed(collector.CHANGES):
            self.assertEqual(restored.count(after), 1)
            restored = restored.replace(after, before)
        self.assertEqual(restored.encode(), (collector.ROOT / 'tools/collect_yanqiansui_terrain.py').read_bytes())
        self.assertIs(collector.collector().verify, verify)

    def test_changed_historical_collector_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'tools').mkdir()
            (root / 'tools/collect_yanqiansui_terrain.py').write_text('raise RuntimeError()', encoding='utf-8')
            with self.assertRaises(AssertionError):
                collector.render(root)

    def test_versioned_receipt_never_claims_integration(self):
        source = collector.render()
        self.assertIn("'ordinary_integration_accepted':False", source)
        self.assertIn("assert not output.exists(),'Preserve historical observations'", source)
        self.assertIn("trace[2]=='false'", source)
        self.assertIn('current_assembly_preserved', source)
        self.assertEqual(hashlib.sha256((collector.ROOT / 'tools/collect_yanqiansui_terrain.py').read_bytes()).hexdigest(), collector.FROZEN)


if __name__ == '__main__':
    unittest.main()
