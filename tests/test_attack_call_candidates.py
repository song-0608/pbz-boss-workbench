"""用途：确保字节码线索只接受已验证引用，拒绝截断和伪指针；不运行游戏。"""
import struct
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from inspect_ahua_attack_lifecycle import call_candidates


class CallCandidates(unittest.TestCase):
    def test_known_function_and_virtual_name(self):
        data = b'\x1c' + struct.pack('<Q', 0x100000) + b'\x1b' + struct.pack('<II', 20, 0)
        rows = call_candidates(data, lambda p: '/Script/Test.EndAbility' if p == 0x100000 else None,
                               lambda n, i: 'K2_ActivateAbility' if (n, i) == (20, 0) else '')
        self.assertEqual([r['offset'] for r in rows], [0, 9])
        self.assertEqual(rows[0]['function'], '/Script/Test.EndAbility')

    def test_truncated_reference_is_not_read(self):
        self.assertEqual(call_candidates(b'\x1c\x00\x00', lambda p: self.fail(), lambda n, i: self.fail()), [])

    def test_non_function_pointer_is_not_a_call(self):
        self.assertEqual(call_candidates(b'\x68' + struct.pack('<Q', 0x100000), lambda p: None, lambda n, i: ''), [])

    def test_invalid_virtual_name_is_discarded(self):
        self.assertEqual(call_candidates(b'\x1b' + struct.pack('<II', 20, 0), lambda p: None, lambda n, i: '/NotAFunction'), [])


if __name__ == '__main__':
    unittest.main()
