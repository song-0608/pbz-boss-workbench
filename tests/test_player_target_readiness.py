"""实时目标策略的离线验收；不启动游戏，不实际发送输入。"""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from player_target_readiness import ensure_visible_target, latest_target_status,deployed_boss_name,target_cycle_verified

SESSION = 'official-validation-20261114-160305'


def hud(condition='', **changes):
    row = {'at': 100, 'expires_at': 600, 'session': SESSION, 'player': 'CurrentPC',
           'text': '新娘阿花 | ACTIVE\n目标：目标甲' + condition + ' | 生命 9000'}
    row.update(changes)
    return 'PBZ_PLAYER_UI:STATUS=' + json.dumps(row, ensure_ascii=False) + '\n'


class TargetReadinessTests(unittest.TestCase):
    def test_deduplicated_hint_requires_exact_fresh_native_target_pair(self):
        request='[PBZBossControl] target_request success=true state=ACTIVE reason=requested; awaiting readback: Boss /World.Target\n'
        query='PBZ_COMBAT_TARGET:QUERY=Boss /World.Target|ignore_soft=Boss /World.Target\n'
        self.assertTrue(target_cycle_verified(request+query))
        self.assertFalse(target_cycle_verified(query+request))
        self.assertFalse(target_cycle_verified(request+query.replace('ignore_soft=Boss /World.Target','ignore_soft=Boss /Other.Target')))
        self.assertFalse(target_cycle_verified(request))

    def test_boss_switch_requires_completed_current_assembly(self):
        registry={'ahua':'新娘阿花','wanjun':'巨锤客：万钧'}
        owner={'player_entry':True};deployment={'player_entry':True,'boss_id':'ahua'}
        self.assertEqual(deployed_boss_name(owner,deployment,'',registry),'新娘阿花')
        start='PBZ_CONTROL_LIFECYCLE:WORKBENCH_BOSS_SELECTED=wanjun\n'
        with self.assertRaisesRegex(RuntimeError,'not completed'):
            deployed_boss_name(owner,deployment,start,registry)
        self.assertEqual(deployed_boss_name(owner,deployment,start+
            'PBZ_CONTROL_LIFECYCLE:PLAYER_ENTRY_READY=wanjun\n',registry),'巨锤客：万钧')
        with self.assertRaisesRegex(RuntimeError,'Unknown Boss'):
            deployed_boss_name(owner,deployment,start+'PBZ_CONTROL_LIFECYCLE:PLAYER_ENTRY_READY=unknown\n',registry)

    def test_independent_boss_identity_is_exact(self):
        text=hud(text='巨锤客：万钧 | ACTIVE\n目标：目标甲 | 生命 9000')
        self.assertIsNone(latest_target_status(text, SESSION, 100))
        self.assertIsNone(latest_target_status(hud(), SESSION, 100, '巨锤客：万钧'))
        self.assertIsNotNone(latest_target_status(text, SESSION, 100, '巨锤客：万钧'))
        click=Mock()
        result=ensure_visible_target(Mock(), 20, SESSION, Mock(return_value=text), click,
                                     lambda: 100, boss_name='巨锤客：万钧')
        self.assertFalse(result['cycle_sent'])
        click.assert_not_called()

    def test_visible_target_does_not_send_f7(self):
        path, click = Mock(), Mock()
        wait = Mock(return_value=hud())
        result = ensure_visible_target(path, 20, SESSION, wait, click, lambda: 100)
        self.assertFalse(result['cycle_sent'])
        click.assert_not_called()
        self.assertEqual(wait.call_args.args[1], 20)

    def test_blocked_target_cycles_once_and_requires_new_interval(self):
        path, click = Mock(), Mock()
        path.read_text.return_value = 'a' * 1000
        wait = Mock(side_effect=[hud('（视线遮挡）'),
                                 '[PBZBossControl] target verified: target乙\n' + hud()])
        result = ensure_visible_target(path, 20, SESSION, wait, click, lambda: 100)
        click.assert_called_once_with(0, 0, 2560, 1600, 'control_target')
        self.assertTrue(result['cycle_sent'])
        self.assertEqual(wait.call_args.args[1], 1000)
        self.assertFalse(wait.call_args.args[2](hud()))

    def test_failed_cycle_does_not_retry(self):
        path, click = Mock(), Mock()
        path.read_text.return_value = 'current'
        wait = Mock(side_effect=[hud('（视线遮挡）'),
                                 '[PBZBossControl] target success=false no alternate hostile target\n' + hud('（视线遮挡）')])
        with self.assertRaisesRegex(RuntimeError, 'Target cycle'):
            ensure_visible_target(path, 0, SESSION, wait, click, lambda: 100)
        click.assert_called_once()

    def test_rejects_stale_foreign_expired_or_off_hud(self):
        for changes in ({'at': 96}, {'at': 102}, {'at': True}, {'session': 'old'},
                        {'expires_at': 100}, {'player': ''}, {'text': '新娘阿花 | OFF'}):
            with self.subTest(changes=changes):
                self.assertIsNone(latest_target_status(hud(**changes), SESSION, 100))

    def test_latest_status_wins_even_if_older_status_was_visible(self):
        self.assertIsNone(latest_target_status(hud() + hud(text='新娘阿花 | OFF'), SESSION, 100))
        self.assertIsNone(latest_target_status(hud() + 'PBZ_PLAYER_UI:STATUS={broken', SESSION, 100))

    def test_unknown_or_inconsistent_target_never_causes_input(self):
        for text in (hud('（视线待核对）'), hud('（已死亡）'),
                     hud(text='新娘阿花 | ACTIVE\n目标：无法读取')):
            path, click = Mock(), Mock()
            with self.subTest(text=text), self.assertRaises(RuntimeError):
                ensure_visible_target(path, 0, SESSION, Mock(return_value=text), click, lambda: 100)
            click.assert_not_called()

    def test_confirmed_dead_or_empty_target_cycles_once_but_still_needs_living_readback(self):
        for before in (hud(text='新娘阿花 | ACTIVE\n目标：无有效锁定'),
                       hud(text='新娘阿花 | ACTIVE\n目标：甲（已死亡） | 生命 0')):
            path,click=Mock(),Mock();path.read_text.return_value='before-input'
            wait=Mock(side_effect=[before,'[PBZBossControl] target verified: living\n'+hud()])
            result=ensure_visible_target(path,0,SESSION,wait,click,lambda:100)
            self.assertTrue(result['cycle_sent']);self.assertEqual(result['before']['visibility'],'unavailable')
            self.assertEqual(result['after']['visibility'],'visible');click.assert_called_once()

    def test_dead_target_cycle_without_living_visible_readback_is_rejected(self):
        path,click=Mock(),Mock();path.read_text.return_value='before-input'
        before=hud(text='新娘阿花 | ACTIVE\n目标：甲（已死亡） | 生命 0')
        wait=Mock(side_effect=[before,'[PBZBossControl] target verified: dead\n'+before])
        with self.assertRaisesRegex(RuntimeError,'Target cycle'):
            ensure_visible_target(path,0,SESSION,wait,click,lambda:100)
        click.assert_called_once()


if __name__ == '__main__':
    unittest.main()
