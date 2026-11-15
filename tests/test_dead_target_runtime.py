"""死亡目标测试必须保留真实伤害、同一对象及连续血量证据。"""
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import test_dead_target_recovery_runtime as runtime


class DeadTargetRuntimeTests(unittest.TestCase):
    def cast(self, skill='skill_06', actor='BP_AHua_C /World.OwnedTarget', before=9000, after=0):
        return (f'KEY_SKILL_BEGIN={skill}|target={actor}|health={before}|active=1\n'
            f'SKILL_INSTANCE={skill}|active=true|cancelable=true|object=GA_Test_C /World.Boss.Instance\n'
            f'KEY_SKILL_END={skill}|peak=1|active=0|natural=true|health_before={before}'
            f'|health_after={after}|distance=710\n')

    def row(self, name='新娘阿花', value=0):
        return {'target': name, 'hud': {'text': f'新娘阿花 | ACTIVE\n目标：{name} | 生命 {value}\n'}}

    def test_exact_instance_and_real_death_pass(self):
        actor, proof = runtime.validate_cast(self.cast(), 'skill_06', 9000)
        self.assertEqual(actor, 'BP_AHua_C /World.OwnedTarget')
        self.assertEqual(proof['health_after'], 0)

    def test_miss_and_incomplete_lifecycle_fail(self):
        for text in (self.cast(after=9000), self.cast().replace('SKILL_INSTANCE=', 'MISSING='),
                     self.cast().replace('natural=true', 'natural=false')):
            with self.subTest(text=text), self.assertRaises(RuntimeError):
                runtime.validate_cast(text, 'skill_06', 9000)

    def test_same_display_name_cannot_replace_target_instance(self):
        with self.assertRaisesRegex(RuntimeError, 'instance changed'):
            runtime.validate_cast(self.cast(actor='BP_AHua_C /World.OtherTarget'), 'skill_06',
                9000, 'BP_AHua_C /World.OwnedTarget')

    def test_health_chain_mismatch_and_foreign_skill_fail(self):
        for text, previous in ((self.cast(), 8750),
                (self.cast().replace('health_before=9000', 'health_before=8750'), 9000),
                (self.cast() + 'KEY_SKILL_BEGIN=skill_07|target=other|health=9000|active=1\n', 9000),
                (self.cast() + self.cast(), 9000)):
            with self.subTest(text=text), self.assertRaises(RuntimeError):
                runtime.validate_cast(text, 'skill_06', previous)

    def test_dead_annotation_preserves_name_but_not_other_targets(self):
        self.assertEqual(runtime.target_health(self.row('新娘阿花（已死亡）'), '新娘阿花'), ('新娘阿花', 0))
        with self.assertRaises(RuntimeError):
            runtime.target_health(self.row('其他角色（已死亡）'), '新娘阿花')
        for row in (None, {'target': None}, self.row(value=-1), self.row(value='NaN')):
            with self.subTest(row=row), self.assertRaises(RuntimeError):
                runtime.target_health(row)

    def test_plan_only_never_reads_session_or_sends_input(self):
        output = io.StringIO()
        with patch.object(sys, 'argv', ['recovery', '--plan-only']), \
                patch.object(runtime.practice, 'owned_session', side_effect=AssertionError('session read')), \
                patch.object(runtime.menu, 'click', side_effect=AssertionError('input sent')), \
                contextlib.redirect_stdout(output):
            self.assertEqual(runtime.main(), 0)
        plan = json.loads(output.getvalue())
        self.assertEqual(plan['maximum_casts'], 8)
        self.assertEqual(set(plan['skills']), {'skill_06', 'skill_09'})
        self.assertFalse(plan['game_input_sent'])
        self.assertTrue(plan['stop_on_miss'])


if __name__ == '__main__':
    unittest.main()
