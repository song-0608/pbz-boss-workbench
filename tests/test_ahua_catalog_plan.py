"""缺项编排不能重复已验收能力、遗失另一批或省略独立鼠标绑定。"""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from ahua_catalog_plan import ORDER, make_plan


class CatalogPlanTests(unittest.TestCase):
    def fixture(self):
        bindings=[{'slot':s if s!='skill_01' else 'slot1','skill':s,'key':s}for s in ORDER]
        bindings.append({'slot':'primary_attack','skill':'skill_01','key':'LEFT_MOUSE_BUTTON'})
        return {'expected_bindings':bindings,'missing_natural':list(ORDER),
            'missing_cancel':list(ORDER),'missing_bindings':deepcopy(bindings),
            'release_id':'ahua-test','candidate_manifest_sha256':'manifest',
            'module_source_sha256':{'player_entry.lua':'source'},'exact_source_closed_sessions':['closed']}

    def test_full_catalog_is_covered_once_per_phase(self):
        report=self.fixture();plans=[make_plan(report,b)for b in ('a','b')]
        for i in (0,1):
            skills=[a['binding']['skill']for p in plans for a in p['phases'][i]['actions']]
            self.assertEqual(len(skills),28);self.assertEqual(set(skills),set(ORDER))
        slots={a['binding']['slot']for p in plans for phase in p['phases']for a in phase['actions']}
        self.assertEqual(slots,{r['slot']for r in report['expected_bindings']})

    def test_passed_evidence_is_not_scheduled_again(self):
        report=self.fixture();report.update(missing_natural=['dash'],missing_cancel=['attack_01'],missing_bindings=[])
        plans=[make_plan(report,b)for b in ('a','b')]
        actions=[a for p in plans for phase in p['phases']for a in phase['actions']]
        self.assertEqual({a['request']for a in actions},{'dash','attack_01'})
        self.assertEqual(len(actions),2)

    def test_batch_membership_survives_other_batch_completion(self):
        report=self.fixture();before=make_plan(report,'b')
        group_a=set(ORDER[::2])
        report['missing_natural']=[s for s in ORDER if s not in group_a]
        report['missing_cancel']=[s for s in ORDER if s not in group_a]
        report['missing_bindings']=[r for r in report['missing_bindings']if r['skill']not in group_a]
        self.assertEqual(before['phases'],make_plan(report,'b')['phases'])

    def test_mouse_binding_uses_cancel_without_duplicate_natural(self):
        plan=make_plan(self.fixture(),'a')
        self.assertEqual([a['request']for a in plan['phases'][0]['actions']if a['binding']['skill']=='skill_01'],['primary_attack'])
        self.assertEqual([a['request']for a in plan['phases'][1]['actions']if a['binding']['skill']=='skill_01'],['skill_01'])

    def test_only_missing_shortcut_still_has_real_input(self):
        report=self.fixture();report.update(missing_natural=[],missing_cancel=[],missing_bindings=[report['expected_bindings'][-1]])
        plan=make_plan(report,'a')
        self.assertEqual(plan['action_count'],1)
        self.assertEqual(plan['phases'][1]['actions'][0]['request'],'primary_attack')

    def test_cancel_first_and_long_combo_last(self):
        plan=make_plan(self.fixture(),'b')
        self.assertTrue(plan['phases'][0]['interrupt']);self.assertFalse(plan['phases'][1]['interrupt'])
        skills=[a['request']for a in plan['phases'][1]['actions']]
        self.assertGreater(skills.index('attack_01'),skills.index('homing_flower'))

    def test_unknown_source_catalog_or_binding_is_rejected(self):
        for field,value in (('missing_natural',['unknown']),('missing_bindings',[{'slot':'slot1','skill':'skill_01','key':'foreign'}])):
            report=self.fixture();report[field]=value
            with self.subTest(field=field),self.assertRaises(RuntimeError):make_plan(report,'a')
        report=self.fixture();report['expected_bindings'].pop()
        with self.assertRaises(RuntimeError):make_plan(report,'a')

    def test_complete_batch_has_no_work(self):
        report=self.fixture();report.update(missing_natural=[],missing_cancel=[],missing_bindings=[])
        self.assertEqual(make_plan(report,'a')['action_count'],0)


if __name__=='__main__':unittest.main()
