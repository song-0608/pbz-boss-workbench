from pathlib import Path
import struct
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from boss_actor_animations import identity
from boss_animation_sources import inspect_psa, inspect_usda


class SkeletalSourceTests(unittest.TestCase):
    def test_nested_reference_keeps_exact_export_identity(self):
        self.assertEqual(identity(('/Game/ABP', 2, 'BlendSpace', 'ABP_C:BlendSpace_1')),
                         ('/game/abp', 2, 'BlendSpace', 'BlendSpace_1'))

    def test_usda_samples_can_follow_a_long_skeleton(self):
        raw = (b'#usda 1.0\n' + b' ' * (2 ** 20) + b'def SkelAnimation "A" {\n'
               b'translations.timeSamples = {\n 0: [(0,0,0)]\n}\n'
               b'rotations.timeSamples = {\n 0: [(1,0,0,0)]\n}\n}\n')
        with TemporaryDirectory() as scratch:
            path = Path(scratch) / 'clip.usda'
            path.write_bytes(raw)
            self.assertEqual(inspect_usda(path)[1], len(raw))
            path.write_bytes(raw[:raw.index(b'rotations.timeSamples')] + b'}\n')
            with self.assertRaises(ValueError):
                inspect_usda(path)

    def test_psa_rejects_truncated_animation_chunk(self):
        raw = b''.join(struct.pack('<20siii', key, 0, size, count) + bytes(size * count)
                       for key, size, count in ((b'ANIMHEAD', 0, 0), (b'BONENAMES', 120, 1),
                                                (b'ANIMINFO', 168, 1), (b'ANIMKEYS', 32, 2)))
        with TemporaryDirectory() as scratch:
            path = Path(scratch) / 'clip.psa'
            path.write_bytes(raw)
            self.assertEqual(inspect_psa(path)[1], len(raw))
            path.write_bytes(raw[:-1])
            with self.assertRaises(ValueError):
                inspect_psa(path)


if __name__ == '__main__':
    unittest.main()
