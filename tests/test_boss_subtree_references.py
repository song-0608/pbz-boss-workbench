import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import prepare_boss_subtree_references as references


class SubtreeReferenceTests(unittest.TestCase):
    def grant(self):
        base = '/PBZCombatAsset/ActorData/Mobs/Fixture/'
        return dict(actor=base + 'BP_Fixture.BP_Fixture_C', config=base + 'ActorC_Fixture.ActorC_Fixture',
            session='20261119-000001', grant_count_line=10, count=1, identity_source='explicit_candidate_identity')

    def fixture(self):
        base = '/PBZCombatAsset/ActorData/Mobs/Fixture/Ability/'
        paths = [base + f'GA_Move_{i}.GA_Move_{i}_C' for i in range(4)]
        characters = [dict(id='fixture', folder='Fixture', abilities=[
            dict(path=paths[0], metadata='verified', kind='leaf'),
            dict(path=paths[1], metadata='verified', kind='subtree'),
            dict(path=paths[2], metadata='unqueried', kind=None)])]
        row = dict(key='a' * 20, parent_class=base + 'GA_Parent.GA_Parent_C', mapping_observed=True,
            trees=[dict(path='/Game/Tree.Tree')], activation_verified=False,
            native_grant_verified=False, referenced_ability_classes=list(paths))
        audit = dict(session='20261119-000000', metadata_only=True, playable=False,
                     outcomes=[row], sources={})
        return characters, audit, paths

    def test_exact_references_skip_verified_types_without_inventing_grants(self):
        characters, audit, paths = self.fixture()
        jobs, deferred, verified = references.plan(characters, [audit])
        self.assertEqual([j['lookup_path'] for j in jobs], paths[2:])
        self.assertEqual(len(verified), 2); self.assertFalse(deferred)
        for job in jobs:
            self.assertFalse(job['native_grant_verified']); self.assertFalse(job['activation_allowed'])
            self.assertTrue(job['reference_only']); self.assertEqual(job['origins'][0]['parent_key'], 'a' * 20)

    def test_rejected_partial_graphs_and_activated_results_cannot_supply_paths(self):
        characters, audit, _ = self.fixture()
        for mutation in ('rejected', 'activated', 'playable'):
            invalid = copy.deepcopy(audit)
            if mutation == 'rejected': invalid['outcomes'][0]['mapping_observed'] = False
            elif mutation == 'activated': invalid['outcomes'][0]['activation_verified'] = True
            else: invalid['playable'] = True
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                references.plan(characters, [invalid])

    def test_player_context_foreign_folders_and_conflicts_are_deferred(self):
        characters, audit, paths = self.fixture()
        characters[0]['abilities'][2]['metadata'] = 'conflict'
        audit['outcomes'][0]['referenced_ability_classes'] += [
            '/PBZCombatAsset/ActorData/Players/Hun/GA_Test.GA_Test_C',
            '/PBZCombatAsset/ActorData/Mobs/Unobserved/GA_Test.GA_Test_C']
        jobs, deferred, _ = references.plan(characters, [audit])
        self.assertEqual([j['lookup_path'] for j in jobs], paths[3:])
        self.assertEqual(len(deferred), 3)

    def test_duplicate_references_merge_origins_not_jobs(self):
        characters, audit, _ = self.fixture()
        second = copy.deepcopy(audit); second['session'] = '20261119-000001'
        jobs, _, _ = references.plan(characters, [audit, second])
        self.assertEqual(len(jobs), 2)
        self.assertTrue(all(len(j['origins']) == 2 for j in jobs))

    def test_rejected_exact_type_is_not_automatically_requeried(self):
        characters, audit, paths = self.fixture()
        characters[0]['abilities'][2]['metadata'] = 'rejected'
        jobs, deferred, _ = references.plan(characters, [audit])
        self.assertEqual([job['lookup_path'] for job in jobs], paths[3:])
        self.assertEqual(deferred, [dict(path=paths[2],
            reason='exact type lookup already rejected; review before an explicit retry')])

    def test_batch_bounds_preserve_order_and_never_mix_more_than_three_folders(self):
        jobs = [dict(key=str(i), id='role_' + str(i // 70)) for i in range(290)]
        batches = references.chunks(jobs)
        self.assertEqual([j for batch in batches for j in batch], jobs)
        self.assertTrue(all(len(b) <= 64 and len({j['id'] for j in b}) <= 3 for b in batches))
        self.assertTrue(all(len({j['id'] for j in b}) <= 3 for b in references.chunks(
            [dict(key=str(i), id='role_' + str(i)) for i in range(10)])))

    def test_native_grant_followups_merge_exact_overlap_without_extra_loads_or_authority(self):
        characters, audit, paths = self.fixture()
        jobs, _, _ = references.plan(characters, [audit]); saved = copy.deepcopy(jobs)
        characters[0]['abilities'][2].update(route='exact_grant_needs_metadata', grants=[self.grant()])
        extra = paths[3].replace('GA_Move_3', 'GA_Grant_Only')
        characters[0]['abilities'].append(dict(path=extra, metadata='unqueried', kind=None,
            route='exact_grant_needs_metadata', grants=[self.grant()]))
        merged, deferred = references.merge_grant_followups(jobs, characters)
        self.assertFalse(deferred); self.assertEqual(jobs, saved)
        self.assertEqual(references.request_counts(merged), dict(tree_references=2,
            historical_grants=2, shared=1, grant_only=1, unique_queries=3))
        self.assertEqual(len({job['lookup_path'] for job in merged}), 3)
        for job in merged:
            self.assertFalse(job['native_grant_verified']); self.assertFalse(job['activation_allowed'])
            unsigned = {k: v for k, v in job.items() if k != 'key'}
            import hashlib
            self.assertEqual(job['key'], hashlib.sha256(references.metadata.canonical(unsigned)).hexdigest()[:20])

    def test_grant_followups_refuse_foreign_folders_and_missing_unique_provenance(self):
        for mutation in ('foreign', 'duplicate', 'empty'):
            characters, _, paths = self.fixture()
            ability = characters[0]['abilities'][2]
            ability.update(route='exact_grant_needs_metadata', grants=[self.grant()])
            if mutation == 'foreign': ability['path'] = paths[2].replace('/Fixture/', '/Foreign/')
            elif mutation == 'duplicate': ability['grants'][0]['count'] = 2
            else: ability['grants'] = []
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                references.merge_grant_followups([], characters)

    def test_rejected_grant_type_is_deferred_without_an_automatic_retry(self):
        characters, _, paths = self.fixture()
        characters[0]['abilities'][2].update(metadata='rejected', route='exact_grant_needs_metadata', grants=[self.grant()])
        jobs, deferred = references.merge_grant_followups([], characters)
        self.assertFalse(jobs); self.assertEqual(deferred[0]['path'], paths[2])

    def test_grant_only_query_freezes_closed_source_evidence(self):
        characters, audit, paths = self.fixture()
        grant = self.grant()
        extra = paths[3].replace('GA_Move_3', 'GA_Grant_Only')
        characters[0]['abilities'].append(dict(path=extra, metadata='unqueried', kind=None,
            route='exact_grant_needs_metadata', grants=[grant]))
        with tempfile.TemporaryDirectory(dir=references.ROOT / 'runtime') as temporary:
            root = Path(temporary).resolve()
            for name in references.SOURCES:
                target = root / name; target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((references.ROOT / name).read_bytes())
            state = root / ('runtime/official-validation-' + grant['session']) / 'state.json'
            work = root / 'evidence/official-validation' / grant['session']
            references.write_json(state, dict(restored=True, work=str(work)))
            references.write_json(work / 'postcheck.json', dict(validation_state=str(state), validation_restored=True,
                research_box_empty=True, research_loader_removed=True, host_registry_unchanged=True,
                formal_files_changed=[], host_config_files_changed=[]))
            (work / 'UE4SS.log').write_bytes(b'offline closed grant fixture\n')
            source_paths = (state, work / 'postcheck.json', work / 'UE4SS.log')
            snapshot = dict(characters=characters, sources={p.relative_to(root).as_posix(): references.sha(p) for p in source_paths})
            with patch.object(references, 'history', return_value=[audit]), \
                 patch.object(references, 'inputs', return_value=(snapshot,)):
                directory, manifest = references.build(root)
                self.assertEqual(manifest['request_counts']['grant_only'], 1)
                references.frozen(directory, root)
                self.assertTrue(set(snapshot['sources']) <= set(manifest['evidence_sha256']))
                (work / 'UE4SS.log').write_bytes(b'changed historical grant log')
                with self.assertRaisesRegex(AssertionError, 'origin evidence changed'):
                    references.frozen(directory, root)

    def test_frozen_plan_rebuilds_sources_and_compiles_every_generated_lua(self):
        characters, audit, _ = self.fixture()
        snapshot = dict(characters=characters)
        with tempfile.TemporaryDirectory(dir=references.ROOT / 'runtime') as temporary:
            root = Path(temporary).resolve()
            for name in references.SOURCES:
                target = root / name; target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((references.ROOT / name).read_bytes())
            with patch.object(references, 'history', return_value=[audit]), \
                 patch.object(references, 'inputs', return_value=(snapshot,)):
                directory, manifest = references.build(root)
                self.assertEqual(len(manifest['jobs']), 2); self.assertTrue(manifest['stage_supported'])
                self.assertEqual(references.frozen(directory, root), (manifest,
                    {p.name: p.read_bytes() for p in directory.glob('*.lua')}))
                for path in directory.glob('*.lua'):
                    checker = root / 'syntax.lua'
                    checker.write_text('assert(loadfile(' + json.dumps(path.relative_to(references.ROOT).as_posix()) + '))', encoding='utf-8')
                    result = subprocess.run([str(references.ROOT.parent / 'build/lua-harness/Release/lua-lab.exe'),
                        checker.relative_to(references.ROOT).as_posix()], cwd=references.ROOT, capture_output=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
                probe = directory / manifest['batches'][0]['script']; probe.write_bytes(b'changed')
                with self.assertRaises(AssertionError): references.verify(directory, root)


if __name__ == '__main__':
    unittest.main()
