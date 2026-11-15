import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import build_selection_candidate as builder
import selection_skill_reuse as reuse
from mod_installation import validate_package
from collect_clearance_rejection import proof


class SelectionCandidateTests(unittest.TestCase):
    def test_rebuild_and_exact_skill_reuse_reject_other_changes(self):
        target=builder.build();self.assertEqual(target,builder.build())
        manifest=validate_package(target)
        current={n.removeprefix('PBZBossControl/Scripts/'):v for n,v in manifest['files'].items()
            if n.startswith('PBZBossControl/Scripts/')and n!='PBZBossControl/Scripts/main.lua'}
        skills,_=reuse.verify(current)
        self.assertEqual(len(skills),8)
        for key in ('runtime.lua','profiles/yanqiansui.lua','owned_arena.lua','boss_workbench.lua',
                    'boss_selection_preflight.lua','yanqiansui_arena_clearance.lua'):
            altered=copy.copy(current);altered[key]='0'*64
            with self.subTest(key=key),self.assertRaises(AssertionError):reuse.verify(altered)
        with self.assertRaises(AssertionError):reuse.verify(dict(current,foreign='0'*64))

    def test_actual_refusal_is_failure_and_tampering_cannot_promote(self):
        import json
        work=builder.ROOT/'evidence/official-validation/20261116-070127'
        action=json.loads((work/'yanqiansui-missing-actions.json').read_text(encoding='utf-8'))
        raw=(work/'UE4SS.log').read_text(encoding='utf-8',errors='replace')
        segment=raw[action['log_offset']:action['log_end']]
        result=proof(segment)
        self.assertTrue(result['clearance_refusal_verified'])
        self.assertFalse(result['playable'])
        for extra in ('PLAYER_ENTRY_READY=073_yanqiansui','KEY_SKILL_BEGIN=skill_01',
                      'SPAWNED=Unexpected','ISSUE_CLEANUP=failed','enter success=true'):
            with self.subTest(extra=extra),self.assertRaises(AssertionError):proof(segment+extra)
        with self.assertRaises(AssertionError):proof(segment.replace('PREREQUISITE_RETRY_SAFE=true',''))


if __name__=='__main__':unittest.main()
