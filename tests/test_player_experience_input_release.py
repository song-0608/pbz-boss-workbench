import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from test_player_experience_inputs import send_fixed_chord


class User:
    def __init__(self):self.front=7;self.events=[]
    def GetForegroundWindow(self):return self.front
    def keybd_event(self,key,scan,flags,extra):self.events.append(('key',key,flags))
    def mouse_event(self,flags,*args):self.events.append(('mouse',flags))


class ReleaseTests(unittest.TestCase):
    def test_shift_w_skill_order_and_all_keys_released(self):
        user=User();send_fixed_chord(user,7,'shift_cast',lambda _:None)
        self.assertEqual(user.events,[('key',16,0),('key',87,0),('key',112,0),
            ('key',112,2),('key',87,2),('key',16,2)])

    def test_lost_focus_before_skill_releases_held_movement_without_cast(self):
        user=User()
        def unfocus(_):user.front=8
        with self.assertRaisesRegex(AssertionError,'lost focus'):send_fixed_chord(user,7,'shift_cast',unfocus)
        self.assertEqual(user.events,[('key',16,0),('key',87,0),('key',87,2),('key',16,2)])

    def test_lost_focus_releases_middle_click_and_never_accepts_arbitrary_action(self):
        user=User()
        def unfocus(_):user.front=8
        with self.assertRaises(AssertionError):send_fixed_chord(user,7,'lock',unfocus)
        self.assertEqual(user.events,[('mouse',32),('mouse',64)])
        user=User()
        with self.assertRaises(AssertionError):send_fixed_chord(user,7,'arbitrary',lambda _:None)
        self.assertEqual(user.events,[])


if __name__=='__main__':unittest.main()
