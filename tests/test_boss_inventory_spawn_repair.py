import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import boss_inventory_spawn_repair as repair


class InventorySpawnRepairTests(unittest.TestCase):
    def test_delayed_target_uses_current_assets_and_preserves_frozen_release(self):
        source = repair.ROOT / 'releases' / repair.BASE / repair.MODULE
        before = source.read_bytes()
        files = repair.overrides()
        self.assertEqual(set(files), {'owned_arena.lua'})
        text = files['owned_arena.lua'].decode('utf-8')
        self.assertEqual(text.count('local inventory_spawn_assets='), 1)
        self.assertEqual(text.count('inventory_spawn_assets.target('), 1)
        target = text.split('        local function spawn_training_target(index)\n', 1)[1]
        self.assertLess(target.index('            guard()'), target.index('inventory_spawn_assets.target('))
        self.assertLess(target.index('inventory_spawn_assets.target('), target.index('maths:MakeTransform('))
        self.assertLess(target.index('inventory_spawn_assets.target('), target.index('statics:BeginDeferredActorSpawnFromClass('))
        self.assertIn('target_profile=require(assembly_profile.training_target_profile)', text)
        self.assertIn('local target_profile=assembly_profile', text)
        self.assertIn('pawn.AIControllerClass=controller_class', target)
        self.assertIn('isolate_initialization(pawn)', target)
        self.assertIn('FinishSpawningActor identity mismatch', text)
        self.assertEqual(source.read_bytes(), before)

    def test_changed_baseline_or_missing_patch_anchor_cannot_be_used(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            path = root / 'releases' / repair.BASE / repair.MODULE
            path.parent.mkdir(parents=True)
            path.write_bytes(b'changed arena')
            manifest = dict(release_id=repair.BASE, files={repair.MODULE: 'wrong digest'})
            with patch.object(repair, 'validate_package', return_value=manifest):
                with self.assertRaisesRegex(AssertionError, 'accepted arena'):
                    repair.payload(root)
                manifest['files'][repair.MODULE] = hashlib.sha256(path.read_bytes()).hexdigest()
                with self.assertRaises(AssertionError):
                    repair.payload(root)
            self.assertEqual(path.read_bytes(), b'changed arena')


if __name__ == '__main__':
    unittest.main()
