import copy
import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import boss_native_combo_candidate as combo


def fixture():
    identifier='044_pengmeng';review=combo.REVIEWS[identifier]
    leaf=combo.PREFIX+'Ability/Axe/Abilities/GA_PengMeng_Special_05.GA_PengMeng_Special_05_C'
    row=dict(id=identifier,parent_class=review['parent'],declaration_closure_complete=True,
        issues=[],context_review=[],subtree_classes=[review['parent']],leaf_classes=[leaf],
        activation_allowed=False,playable=False,
        exact_parent_variants=[dict(actor=review['actor'],config=review['config'],
            parent_grant_snapshots=[dict(session='20261119-010735',grant_count_line=922)])],
        trees=[dict(path=combo.PREFIX+'BehaviorTree/Tree.Tree',weight=100.0,references=[leaf],declaration_sha256='closed')])
    character=dict(id=identifier,variants=[dict(path=review['actor'],metadata='verified',receipts=['closed'],
        observation=dict(observed_config=review['config'],display_name='fixture',
            lineage=[review['actor'],'/Script/ProjectPBZ.PBZCharacter_NPC']))])
    return dict(parents=[row]),[character]


class NativeComboCandidateTests(unittest.TestCase):
    def test_only_exact_reviewed_variant_and_parent_enter_the_candidate(self):
        report,characters=fixture();value=combo.select('044_pengmeng',report,characters)
        self.assertEqual(value['ability_pool'],[combo.REVIEWS['044_pengmeng']['parent']])
        self.assertEqual(value['class_path'],combo.REVIEWS['044_pengmeng']['actor'])
        self.assertNotIn('execution_order',value)
        self.assertEqual(list(value['contract']['trees'].values()),[100.0])
        self.assertEqual(len(value['contract']['leaves']),1)

    def test_missing_graph_nested_context_or_other_actor_cannot_be_promoted(self):
        mutations=[lambda r:r.update(declaration_closure_complete=False),
            lambda r:r.update(issues=[dict(reason='cycle')]),
            lambda r:r.update(context_review=[dict(reason='counter')]),
            lambda r:r['subtree_classes'].append('another scheduler'),
            lambda r:r['exact_parent_variants'][0].update(actor='foreign actor'),
            lambda r:r['exact_parent_variants'][0].update(config='foreign config'),
            lambda r:r['exact_parent_variants'][0].update(parent_grant_snapshots=[]),
            lambda r:r['leaf_classes'].append('/Foreign/Ability.Ability_C'),
            lambda r:r['trees'][0].update(references=[]),
            lambda r:r['trees'].append(copy.deepcopy(r['trees'][0]))]
        for mutation in mutations:
            report,characters=fixture();mutation(report['parents'][0])
            with self.subTest(mutation=mutation),self.assertRaises(AssertionError):
                combo.select('044_pengmeng',report,characters)

    def test_invalid_tree_weights_and_changed_variant_receipts_are_rejected(self):
        for weight in (0,-1,float('inf'),float('nan'),True):
            report,characters=fixture();report['parents'][0]['trees'][0]['weight']=weight
            with self.subTest(weight=weight),self.assertRaises(AssertionError):
                combo.select('044_pengmeng',report,characters)
        report,characters=fixture();characters[0]['variants'][0]['receipts']=[]
        with self.assertRaises(AssertionError):combo.select('044_pengmeng',report,characters)

    def test_real_payload_opens_only_the_exact_native_parent_and_preserves_base(self):
        report,characters=fixture();value=combo.select('044_pengmeng',report,characters)
        value['dependency_report_sha256']='closed'
        frozen=combo.ROOT/'releases'/combo.spawn.BASE
        original={n:combo.sha(frozen/'PBZBossControl/Scripts'/n) for n in ('combo_scheduler.lua','owned_arena.lua')}
        files=combo.modules(value)
        self.assertEqual(set(files),{'boss_candidate.lua','owned_arena.lua','combo_scheduler.lua','subtree_contracts.lua'})
        self.assertIn(b'profile.developer_native_combo==true',files['owned_arena.lua'])
        self.assertIn(b'combo Actor changed',files['combo_scheduler.lua'])
        self.assertIn(b'combo child already active',files['combo_scheduler.lua'])
        self.assertNotIn(b"id=='attack_01'and",files['combo_scheduler.lua'])
        for n,digest in original.items():self.assertEqual(combo.sha(frozen/'PBZBossControl/Scripts'/n),digest)
        self.assertIn(b'parent_class',files['boss_candidate.lua'])
        self.assertNotIn(b':GiveAbility(',b''.join(files.values()))


if __name__=='__main__':unittest.main()
