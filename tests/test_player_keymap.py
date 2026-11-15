"""用途：验证错误键位在写入研究游戏之前被拒绝，用户文本不能变成Lua代码。"""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import player_keymap as keys

class KeymapTests(unittest.TestCase):
    def test_current_file_and_lua_are_valid(self):
        value=keys.read();self.assertIn('enter="F6"',keys.lua(value))
    def test_duplicate_controls_and_skills_are_rejected(self):
        value=copy.deepcopy(keys.read());value['skills']['dash']=value['controls']['exit']
        with self.assertRaisesRegex(ValueError,'重复按键'):keys.validate(value)
    def test_source_text_and_reserved_movement_are_rejected(self):
        for key in ('W','ESCAPE','Q"; os.execute("x")'):
            value=copy.deepcopy(keys.read());value['skills']['dash']=key
            with self.assertRaises(ValueError):keys.lua(value)
    def test_missing_or_extra_action_is_rejected(self):
        value=copy.deepcopy(keys.read());value['skills']['grant_ability']='R'
        with self.assertRaises(ValueError):keys.validate(value)
    def test_prior_keymap_schema_remains_readable(self):
        value=copy.deepcopy(keys.read());value['skills'].pop('native_combo',None)
        self.assertEqual(keys.validate(value),value)

    def test_workbench_key_is_reserved_in_both_groups(self):
        for group,action in (('controls','enter'),('skills','dash')):
            value=copy.deepcopy(keys.read());value[group][action]='F11'
            with self.assertRaisesRegex(ValueError,'窗口热键保留'):keys.validate(value)
            value[group][action]='INS'
            with self.assertRaisesRegex(ValueError,'工作台保留'):keys.validate(value)

    def test_missing_optional_defaults_participate_in_conflict_checks(self):
        value=copy.deepcopy(keys.read());value['skills'].pop('skill_04')
        value['skills']['dash']='ONE'
        with self.assertRaisesRegex(ValueError,'重复按键'):keys.validate(value)

    def test_effective_old_config_displays_defaults_without_mutation(self):
        value=copy.deepcopy(keys.read())
        for action in keys.OPTIONAL_SKILLS:value['skills'].pop(action,None)
        before=copy.deepcopy(value);effective=keys.effective(value)
        self.assertEqual(value,before)
        for action,key in keys.OPTIONAL_DEFAULTS.items():
            self.assertEqual(effective['skills'][action],key)
            self.assertIn(action+'="'+key+'"',keys.lua(value))

if __name__=='__main__':unittest.main()
