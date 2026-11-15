"""角色选择和控制键快照必须与本次实际装配一致。"""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import ahua_practice as practice
import player_keymap
import player_settings

class PlayerSettings(unittest.TestCase):
    def test_only_registered_string_boss(self):
        self.assertEqual(player_settings.validate({'boss_id':'ahua_guitoudao'}),{'boss_id':'ahua_guitoudao'})
        for value in ({'boss_id':[]},{'boss_id':None},{'boss_id':'invented'},{'boss_id':'ahua_guitoudao','unlock':True}):
            with self.assertRaises(ValueError):player_settings.validate(value)

    def test_deployed_controls_are_snapshot_not_next_round_file(self):
        data=copy.deepcopy(player_keymap.read())
        original=practice.deployed_controls({'player_keymap':data})
        used={key for group in data.values()for key in group.values()}
        replacement=next(key for key in sorted(player_keymap.ALLOWED)if key not in used)
        old_enter=original['enter'];data['controls']['enter']=replacement
        self.assertNotEqual(original,practice.deployed_controls({'player_keymap':data}))
        self.assertEqual(original['enter'],old_enter)
        with self.assertRaises(ValueError):practice.deployed_controls({'player_keymap':None})

    def test_developer_bank_uses_its_actual_fixed_controls(self):
        for mode in ('skill_lab','expanded'):
            self.assertEqual(practice.deployed_controls({mode:True,'player_keymap':None}),
                             {'enter':'F6','exit':'F10','cycle_target':'F7'})

    def test_editor_shows_only_selected_boss_actions(self):
        labels=player_settings.editor_skill_labels('057_wanjun')
        self.assertEqual(set(labels),{'slot1','heavy_01','skill_02','dash'})
        self.assertTrue(all(label.startswith('万钧')for label in labels.values()))
        labels=player_settings.editor_skill_labels('073_yanqiansui')
        self.assertEqual(set(labels),{'slot1','heavy_01','skill_02','dash'})
        self.assertTrue(all(label.startswith('烟千岁')for label in labels.values()))
        self.assertEqual(set(player_settings.editor_skill_labels('ahua_guitoudao')),set(player_keymap.read()['skills']))
        with self.assertRaises(ValueError):player_settings.editor_skill_labels('invented')

if __name__=='__main__':unittest.main()
