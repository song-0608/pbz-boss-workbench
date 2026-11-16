import ast
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import terrain_position_input as camera


class CameraInputTests(unittest.TestCase):
    def test_only_fixed_camera_gestures_change_after_the_same_input_gates(self):
        original=(camera.ROOT/'tools/research_game_menu.py').read_text(encoding='utf-8')
        start=original.index('    if positioning_key is not None:\n        u.keybd_event(positioning_key,0,0,0)')
        end=original.index("    if purpose in ('control_lab_next'",start)
        for direction,expected in {'left':(-100,0),'right':(100,0),'fine-left':(-20,0),'fine-right':(20,0),'down':(0,40)}.items():
            source,dx,dy=camera.render_startup_camera(direction)
            self.assertEqual((dx,dy),expected);ast.parse(source)
            self.assertEqual(source[:start],original[:start])
            self.assertTrue(source.endswith(original[end:]))
            self.assertIn("for _ in range(6):",source[start:])
            self.assertIn("if u.GetForegroundWindow()!=h:raise RuntimeError('Research window lost focus')",source[start:])

    def test_arbitrary_gesture_rejected_before_any_window_access(self):
        for direction in ('up','right-9000','fine-left-forever',''):
            with self.assertRaises(AssertionError):camera.render_startup_camera(direction)
        with patch.object(camera,'FROZEN','0'*64),self.assertRaises(AssertionError):camera.render_startup_camera('down')


if __name__=='__main__':unittest.main()
