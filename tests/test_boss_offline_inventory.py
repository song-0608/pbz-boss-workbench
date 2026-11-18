from collections import defaultdict
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import boss_metadata_jobs as metadata
from boss_adaptation_workflow import write_json
from boss_offline_inventory import (QUERY_LABEL, captured_metadata, exact_payload, exact_requests,
                                    grant_snapshots, observation_state, special_ability)


ID = '071_xianzhe'
FOLDER = '071_XianZhe'
BASE = f'/PBZCombatAsset/ActorData/Mobs/{FOLDER}'
ACTOR = BASE + '/BP_Monster_XianZhe.BP_Monster_XianZhe_C'
CONFIG = BASE + '/ActorConfig/ActorC_XianZhe.ActorC_XianZhe'
DODGE = BASE + '/Ability/Dodge/GA_XianZhe_Dodge_F.GA_XianZhe_Dodge_F_C'
PROFILE = dict(actor=ACTOR, config=CONFIG, folder=ID)
SPAWN = 'SPAWN_ATTEMPT=1'
IDENTITY = f'CANDIDATE_IDENTITY_READY={ID}|{ACTOR}|{CONFIG}'
CDO = ('SPAWN_STATE=class_default|object=BP_Monster_XianZhe_C '
       + BASE + '/BP_Monster_XianZhe.Default__BP_Monster_XianZhe_C|authority=true')
GRANT = f'GRANTED_ABILITY=BlueprintGeneratedClass {DODGE}'
END = 'INTERACTIVE_READY=ready'


def parse(*payloads):
    return list(grant_snapshots((f'[Lua] PBZ_CONTROL_LIFECYCLE:{msg}' for msg in payloads),
                               {ID: FOLDER}, (PROFILE,)))


class InventoryTests(unittest.TestCase):
    def test_complete_grants_use_exact_identity_and_keep_instance_counts(self):
        explicit, = parse(SPAWN, IDENTITY, CDO, 'GRANTED_COUNT=2', GRANT, GRANT, END)
        self.assertEqual(explicit['grants'], {DODGE: 2})
        self.assertEqual(explicit['identity_source'], 'explicit_candidate_identity')
        published, = parse(SPAWN, CDO, 'GRANTED_COUNT=1', GRANT, END)
        self.assertEqual(published['actor'], ACTOR)
        self.assertEqual(published['identity_source'], 'spawn_cdo_and_v5_config')

    def test_no_cross_spawn_or_partial_grants(self):
        self.assertEqual(parse(SPAWN, IDENTITY, 'GRANTED_COUNT=2', GRANT, SPAWN, GRANT, END), [])
        self.assertEqual(parse(SPAWN, IDENTITY, 'GRANTED_COUNT=1', GRANT, GRANT, END), [])
        self.assertEqual(parse(SPAWN, IDENTITY, 'GRANTED_COUNT=1', GRANT), [])
        self.assertEqual(parse(SPAWN, IDENTITY, IDENTITY, 'GRANTED_COUNT=1', GRANT, END), [])
        wrong_package = CDO.replace('/BP_Monster_XianZhe.', '/AnotherPackage.')
        self.assertEqual(parse(SPAWN, wrong_package, 'GRANTED_COUNT=1', GRANT, END), [])
        self.assertEqual(parse(SPAWN, IDENTITY, wrong_package, 'GRANTED_COUNT=1', GRANT, END), [])

    def test_metadata_conflict_and_utility_are_review_items(self):
        leaf = dict(metadata_verified=True, ability_kind='leaf')
        subtree = dict(metadata_verified=True, ability_kind='subtree')
        self.assertEqual(observation_state([leaf, subtree], ('ability_kind',)), ('conflict', None))
        self.assertTrue(special_ability(BASE + '/Ability/GA_Skill_GroupResurrect.GA_Skill_GroupResurrect_C'))
        self.assertFalse(special_ability(DODGE))

    def test_closed_batch_replay_requires_matching_raw_outcomes_and_grants(self):
        session = '20261117-194042'
        snapshot, = parse(SPAWN, IDENTITY, 'GRANTED_COUNT=1', GRANT, END)
        snapshot['session'] = session
        grant = {key: snapshot[key] for key in ('actor', 'config', 'session', 'grant_count_line', 'identity_source')}
        grant['count'] = 1
        rows = [dict(id=ID, abilities=[dict(path=DODGE, grants=[grant], route='exact_grant_needs_metadata')])]
        jobs, = exact_requests(rows)
        manifest, script = exact_payload(jobs, 'example')
        fingerprint, job = manifest['fingerprint'], jobs[0]
        lines = [f'PBZ_ADAPTER_META:START={fingerprint}',
                 f"PBZ_ADAPTER_META:OUTCOME={job['key']}|ability|{DODGE}|leaf",
                 f'PBZ_ADAPTER_META:END={fingerprint}']
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            work = root / 'evidence/official-validation' / session
            state = root / 'runtime' / ('official-validation-' + session) / 'state.json'
            write_json(state, dict(restored=True, work=str(work)))
            write_json(work / 'postcheck.json', dict(validation_state=str(state), validation_restored=True,
                       research_box_empty=True, research_loader_removed=True, host_registry_unchanged=True,
                       formal_files_changed=[], host_config_files_changed=[]))
            def file(suffix):
                return work / f'{QUERY_LABEL}-{fingerprint}-{suffix}'
            write_json(file('manifest.json'), manifest)
            file('metadata.lua').write_bytes(script)
            stage = dict(state_file=str(state), research_pid=12, batch=fingerprint, script_sha256=manifest['script_sha256'],
                         log_byte_offset=0, log_prefix_sha256=hashlib.sha256(b'').hexdigest(), metadata_only=True,
                         input_sent=False)
            write_json(file('intent.json'), stage)
            write_json(file('staged.json'), stage)
            result = dict(state_file=str(state), research_pid=12, batch=fingerprint, metadata_only=True, playable=False,
                          lines=lines, outcomes=metadata.analyze(lines, dict(batch_fingerprint=fingerprint, jobs=jobs)))
            write_json(file('results.json'), result)
            (work / 'UE4SS.log').write_text('\n'.join(lines), encoding='utf-8')
            receipts = defaultdict(list)
            captured_metadata(root, {}, receipts, [snapshot])
            self.assertEqual(receipts[ID, DODGE][0]['ability_kind'], 'leaf')
            with self.assertRaisesRegex(AssertionError, 'grant evidence changed'):
                captured_metadata(root, {}, defaultdict(list), [])
            result['outcomes'][0]['ability_kind'] = 'subtree'
            write_json(file('results.json'), result)
            with self.assertRaises(AssertionError):
                captured_metadata(root, {}, defaultdict(list), [snapshot])


if __name__ == '__main__':
    unittest.main()
