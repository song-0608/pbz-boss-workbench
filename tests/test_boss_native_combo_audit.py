from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import boss_native_combo_audit as audit
from tests import test_boss_skill_repeat_audit as repeat_fixtures
from tests.test_boss_skill_repeat_audit import entry, restore

PARENT = '/Fixture/GA_Parent.GA_Parent_C'
LEAF = '/Fixture/GA_Leaf.GA_Leaf_C'
DEFINITION = dict(parent_class=PARENT, contract={'class':PARENT, 'leaves':{LEAF:True}})
START = 'COMBO_SCHEDULER_BEGIN=skill_01|brain_tick=true|outer_ai=false|ai_tick=false|limit=25\n'
ACTIVE = (f'COMBO_OBSERVED_ACTIVE={PARENT}|active=1|baseline=0\n'
          f'COMBO_OBSERVED_ACTIVE={LEAF}|active=1|baseline=0\n')
CANCEL = 'COMBO_CANCEL_BEGIN=skill_01|parent_active=1|active_children=1\n'
STOP = 'COMBO_TREE_STOP=running_before=true\n'
NATURAL_END = 'COMBO_SCHEDULER_END=natural=true|all_grants_at_baseline=true|brain_tick=false\n'
CANCEL_END = 'COMBO_SCHEDULER_END=cancelled=true|all_grants_at_baseline=true|brain_tick=false\n'


def cast(before=1000, damage=100, cancel=False):
    begin = (f'KEY_SKILL_BEGIN=skill_01|target=Target0|health={before}|active=1\n'
        'SKILL_INSTANCE=skill_01|active=true|cancelable=true|object=GA_Parent_C Boss0.Instance0\n')
    if cancel: return START + begin + ACTIVE + CANCEL + STOP + CANCEL_END
    return (START + begin + ACTIVE + NATURAL_END +
        f'KEY_SKILL_END=skill_01|peak=1|active=0|natural=true|health_before={before}'
        f'|health_after={before-damage}|distance=12|sample_ticks=12|tail_ticks=15\n')


def cycle(count=5, damage=100, cancel=False):
    return entry() + ''.join(cast(1000-i*damage, damage, cancel) for i in range(count)) + restore()


class NativeComboAuditTests(unittest.TestCase):
    def test_pairs_five_parent_and_child_lifecycles_without_promoting_a_boss(self):
        row = audit.audit_cycle(cycle(), DEFINITION)
        self.assertTrue(row['lifecycle_observation_passed'])
        self.assertTrue(row['every_use_health_decrease_observed'])
        self.assertEqual(len(row['attempts']), 5)
        for key in ('runtime_bundle_identity_verified','exact_live_grants_verified',
                    'runtime_acceptance_current','playable','release_accepted','native_execution_order_inferred'):
            self.assertFalse(row[key])
        row = audit.audit_cycle(cycle(damage=0), DEFINITION)
        self.assertTrue(row['lifecycle_observation_passed'])
        self.assertFalse(row['every_use_health_decrease_observed'])

    def test_current_cancel_snapshot_and_full_recovery_are_required(self):
        row = audit.audit_cycle(cycle(1,cancel=True), DEFINITION, mode='cancel')
        self.assertTrue(row['active_native_cancellation_and_player_recovery_observed'])
        # Parent may have stopped naturally while its child still needs cancellation.
        text = cycle(1,cancel=True).replace('parent_active=1','parent_active=0')
        self.assertTrue(audit.audit_cycle(text, DEFINITION, mode='cancel')['lifecycle_observation_passed'])
        for before, after in ((CANCEL,''),('parent_active=1|active_children=1','parent_active=0|active_children=0'),
            (CANCEL_END,''),(STOP,''),('all_grants_at_baseline=true','all_grants_at_baseline=false'),
            ('CAMERA_CLEANUP_ENGINE_VERIFIED=true',''),('exit success=true','auto_exit success=true'),
            ('active_children=1','active_children=2')):
            with self.subTest(before=before,after=after):
                row = audit.audit_cycle(cycle(1,cancel=True).replace(before,after), DEFINITION, mode='cancel')
                self.assertFalse(row['lifecycle_observation_passed'])

    def test_no_borrowing_missing_parent_child_or_scheduler_events(self):
        original = cycle()
        for mode in ('parent','leaf','foreign','baseline','count','order','end','begin','duplicate',
                     'malformed','recovery','rejection','orphan','late','cancel_failure'):
            text = original
            if mode == 'parent': text = text.replace(ACTIVE.splitlines()[0]+'\n','',1)
            elif mode == 'leaf': text = text.replace(ACTIVE.splitlines()[1]+'\n','',1)
            elif mode == 'foreign': text = text.replace(LEAF,'/Foreign/GA_Attack.GA_Attack_C',1)
            elif mode == 'baseline': text = text.replace('baseline=0','baseline=1',1)
            elif mode == 'count': text = text.replace('active=1|baseline=0','active=256|baseline=0',1)
            elif mode == 'order': text = text.replace(ACTIVE+NATURAL_END,NATURAL_END+ACTIVE,1)
            elif mode == 'end': text = text.replace(NATURAL_END,'',1)
            elif mode == 'begin': text = text.replace(START,'',1)
            elif mode == 'duplicate': text = text.replace(ACTIVE,ACTIVE+ACTIVE,1)
            elif mode == 'malformed': text = text.replace(NATURAL_END,NATURAL_END+'COMBO_SCHEDULER_END=bad\n',1)
            elif mode == 'recovery': text = text.replace('CAMERA_CLEANUP_ENGINE_VERIFIED=true','')
            elif mode == 'rejection': text = text.replace(restore(),'SKILL_NATIVE_REJECTED=skill_01|consecutive=1\n'+restore())
            elif mode == 'orphan': text = text.replace(START,NATURAL_END+START,1)
            elif mode == 'late': text += ACTIVE
            else: text += 'PBZ_COMBO_CANCEL:FAILED=fixture\n'
            with self.subTest(mode=mode):
                self.assertFalse(audit.audit_cycle(text,DEFINITION)['lifecycle_observation_passed'])

    def test_cancel_cannot_borrow_natural_completion_or_different_takeover(self):
        self.assertFalse(audit.audit_cycle(cycle(),DEFINITION,mode='cancel')['lifecycle_observation_passed'])
        self.assertFalse(audit.audit_cycle(cycle(1,cancel=True),DEFINITION)['lifecycle_observation_passed'])
        for text in (cycle()+cycle(),cycle().replace(restore(),'SPAWN_ATTEMPT=2\n'+restore())):
            with self.assertRaises(AssertionError):audit.audit_cycle(text,DEFINITION)
        text=cycle().replace('CONTROL_PARTICIPANT=boss','MISSING=boss')
        self.assertFalse(audit.audit_cycle(text,DEFINITION)['lifecycle_observation_passed'])

    def test_cancellation_must_follow_the_same_observed_parent_and_leaf(self):
        original=cycle(1,cancel=True)
        for before,after in ((ACTIVE+CANCEL,CANCEL+ACTIVE),(CANCEL+STOP,STOP+CANCEL),
            (CANCEL,CANCEL+CANCEL),(STOP,STOP+'COMBO_TREE_STOP=bad\n'),
            ('COMBO_CANCEL_BEGIN=skill_01','COMBO_CANCEL_BEGIN=foreign'),
            (CANCEL_END,CANCEL_END+NATURAL_END)):
            with self.subTest(before=before):
                self.assertFalse(audit.audit_cycle(original.replace(before,after),DEFINITION,mode='cancel')['lifecycle_observation_passed'])

    def test_closed_session_rechecks_the_raw_log_and_preserves_scope(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            session,work,_,_=repeat_fixtures.RepeatAuditTests().fixture(root)
            (work/'UE4SS.log').write_text(cycle(),encoding='utf-8')
            bundle=root/'candidate';bundle.mkdir()
            definition=dict(DEFINITION,id='044_pengmeng')
            (bundle/'manifest.json').write_text(audit.json.dumps(dict(definition=definition)),encoding='utf-8')
            with patch.object(audit,'reviewed_definition',return_value=definition) as validate:
                result=audit.closed_audit(session,0,bundle,root=root)
                self.assertTrue(result['lifecycle_observation_passed'])
                self.assertTrue(result['historical_observation_only'])
                self.assertFalse(result['runtime_bundle_identity_verified'])
                validate.assert_called_once_with(bundle,root=root)
            with patch.object(audit,'reviewed_definition',return_value=definition),patch.object(audit.repeat,'closed_audit') as closed:
                closed.return_value=dict(sources={ (work/'UE4SS.log').relative_to(root).as_posix():'wrong'})
                with self.assertRaisesRegex(AssertionError,'log changed'):
                    audit.closed_audit(session,0,bundle,root=root)

    def test_historical_graph_uses_original_frozen_bundle_and_refuses_tampering(self):
        import tempfile
        from tests.test_boss_native_combo_candidate import fixture
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();graph,characters=fixture()
            definition=audit.candidate.select('044_pengmeng',graph,characters)
            graph_path=root/audit.candidate.dependencies.OUTPUT/'fixture/dependencies.json'
            graph_path.parent.mkdir(parents=True)
            graph_path.write_text(audit.json.dumps(graph),encoding='utf-8')
            definition['dependency_report_sha256']=audit.sha(graph_path)
            files={name:b'-- immutable fixture\n' for name in
                ('boss_candidate.lua','combo_scheduler.lua','subtree_contracts.lua','owned_arena.lua')}
            manifest=dict(schema=1,kind='isolated_native_combo_candidate',build=audit.candidate.BUILD,
                definition=definition,dependency_report=graph_path.relative_to(root).as_posix(),
                dependency_report_sha256=audit.sha(graph_path),
                overrides={name:audit.hashlib.sha256(raw).hexdigest() for name,raw in files.items()},
                module_sha256=audit.hashlib.sha256(files['boss_candidate.lua']).hexdigest(),
                developer_only=True,playable=False,installed=False,game_started=False,
                runtime_acceptance_current=False,execution_order='native_engine_only')
            key=audit.hashlib.sha256(audit.candidate.canonical(manifest)).hexdigest()[:20]
            bundle=root/audit.candidate.OUTPUT/('044_pengmeng-'+key);bundle.mkdir(parents=True)
            for name,raw in files.items():(bundle/name).write_bytes(raw)
            (bundle/'manifest.json').write_text(audit.json.dumps(manifest),encoding='utf-8')
            with patch.object(audit.candidate,'validate',side_effect=AssertionError('current inventory changed')):
                self.assertEqual(audit.reviewed_definition(bundle,root),definition)
            (bundle/'combo_scheduler.lua').write_bytes(b'changed')
            with self.assertRaisesRegex(AssertionError,'payload changed'):audit.reviewed_definition(bundle,root)
            (bundle/'combo_scheduler.lua').write_bytes(files['combo_scheduler.lua'])
            graph_path.write_bytes(b'{}')
            with self.assertRaises(AssertionError):audit.reviewed_definition(bundle,root)
            graph_path.write_text(audit.json.dumps(graph),encoding='utf-8')
            manifest['definition']['contract']['leaves']['/Foreign/GA_Test.GA_Test_C']=True
            (bundle/'manifest.json').write_text(audit.json.dumps(manifest),encoding='utf-8')
            with self.assertRaisesRegex(AssertionError,'identity changed'):audit.reviewed_definition(bundle,root)


if __name__=='__main__':unittest.main()
