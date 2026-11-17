"""Use historical closed assemblies to exercise the cleanup handoff, never the game."""
from pathlib import Path
import copy
import json
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from boss_adaptation_workflow import ROOT
from collect_boss_candidate_acceptance import candidate_interval
from boss_skill_session import complete_assembly,OWNED,evaluate


class SkillSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw=(ROOT/'evidence/official-validation/20261116-073449/UE4SS.log').read_text(encoding='utf-8',errors='replace')
        start,_=candidate_interval(raw,'056_youlong');cls.segment=raw[start:]
        cls.raw=raw;cls.start=raw.index('PBZ_CONTROL_LIFECYCLE:SPAWN_ATTEMPT=1')
        cls.actions=json.loads((ROOT/'evidence/official-validation/20261116-073449/player-extra-skill-actions.json').read_text(encoding='utf-8'))
        report=json.loads((ROOT/'evidence/official-validation/20261116-073449/boss-candidate-acceptance.json').read_text(encoding='utf-8'))
        cls.bindings={k:v['class_path'] for k,v in report['skills'].items()}
        cls.display_name=report['metadata_identity']['display_name']

    def evaluate(self,actions=None,expected=None):
        return evaluate(self.raw,self.start,len(self.raw),'056_youlong','20261116-073449',
            expected or self.bindings,actions if actions is not None else self.actions,self.display_name)

    def test_closed_restored_assembly_can_advance_without_restart(self):
        self.assertTrue(complete_assembly(self.segment))

    def test_missing_owned_cleanup_cannot_advance(self):
        for name in OWNED:
            with self.subTest(name=name):
                self.assertFalse(complete_assembly(self.segment.replace(
                    'OWNED_DESTROY_VERIFIED='+name+'|engine_unusable=true','REMOVED')))

    def test_missing_restore_or_end_cannot_advance(self):
        for marker in ('PBZ_CONTROL_LIFECYCLE:INTERACTIVE_END=',
                       'CAMERA_CLEANUP_ENGINE_VERIFIED=true',
                       '[PBZBossControl] enter success=true state=ACTIVE'):
            with self.subTest(marker=marker):
                self.assertFalse(complete_assembly(self.segment.replace(marker,'REMOVED')))

    def test_faults_and_multiple_assemblies_are_rejected(self):
        for token in ('state=FAULTED','PBZ_CONTROL_LIFECYCLE:ISSUE_',
                      'PBZ_CONTROL_RESTORE:FAILED=','DESTROY_SKIPPED','[Lua::execute_file]',
                      'PBZ_CONTROL_LIFECYCLE:INTERACTIVE_READY=',
                      'PBZ_CONTROL_LIFECYCLE:INTERACTIVE_END='):
            with self.subTest(token=token):self.assertFalse(complete_assembly(self.segment+token))

    def test_historical_four_action_assembly_replays_full_evidence(self):
        result=self.evaluate()
        self.assertTrue(result['all_four_accepted'])
        self.assertEqual(len(result['accepted_skills']),4)
        self.assertFalse(result['playable'])

    def test_action_log_subset_cannot_replace_exact_interval(self):
        actions=copy.deepcopy(self.actions)
        relevant=next(a for a in actions if a['log_offset']>=self.start)
        relevant['lines']=relevant['lines'][:1]
        with self.assertRaises(AssertionError):self.evaluate(actions)

    def test_missing_or_duplicate_action_is_not_full_acceptance(self):
        actions=[a for a in self.actions if a['log_offset']>=self.start]
        self.assertFalse(self.evaluate(actions[:-1])['all_four_accepted'])
        with self.assertRaises(AssertionError):self.evaluate(actions+[actions[-1]])

    def test_cross_assembly_action_and_wrong_grant_are_rejected(self):
        actions=copy.deepcopy(self.actions)
        row=next(a for a in actions if a['log_offset']>=self.start);row['log_offset']=self.start-1
        with self.assertRaises(AssertionError):self.evaluate(actions)
        expected=dict(self.bindings);expected['skill_01']='/Wrong.Class_C'
        with self.assertRaises(AssertionError):self.evaluate(expected=expected)


if __name__=='__main__':unittest.main()
