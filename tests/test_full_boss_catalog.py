import copy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from tests.test_boss_metadata_jobs import candidate
import boss_metadata_jobs as metadata
from prepare_full_boss_catalog import select
import stage_full_boss_catalog as collector
from boss_adaptation_workflow import write_json


class FullCatalogTests(unittest.TestCase):
    def fixture(self):
        value = candidate('fixture', characters=2, abilities=5)
        jobs = metadata.jobs_for(value)
        variants = [dict(path=row['lookup_path'], metadata='unqueried', spawn_configs=[])
                    for row in jobs if row['role'] == 'character']
        abilities = [dict(path=row['lookup_path'], metadata='unqueried', v5_skill=False, route='needs_variant_grant')
                     for row in jobs if row['role'] == 'ability']
        inventory = dict(characters=[dict(id='fixture', variants=variants, abilities=abilities)])
        return dict(candidates=[value]), inventory

    def test_all_missing_requests_are_prepared_without_first_variant_selection(self):
        catalog, inventory = self.fixture()
        batches, counts = select(catalog, inventory)
        self.assertEqual(sum(map(len, batches)), 7)
        self.assertEqual(counts['pending_character'], 2)
        self.assertEqual(counts['pending_ability'], 5)
        self.assertEqual(len({job['key'] for batch in batches for job in batch}), 7)

    def test_success_conflict_profile_and_dedicated_grant_are_not_repeated(self):
        catalog, inventory = self.fixture()
        row = inventory['characters'][0]
        row['abilities'][0]['metadata'] = 'verified'
        row['abilities'][1]['metadata'] = 'conflict'
        row['abilities'][2]['v5_skill'] = True
        row['abilities'][3]['route'] = 'exact_grant_needs_metadata'
        row['variants'][0]['spawn_configs'] = ['/Fixture.Config']
        batches, counts = select(catalog, inventory)
        self.assertEqual(sum(map(len, batches)), 2)
        self.assertEqual(counts['verified_or_conflicting_metadata'], 2)
        self.assertEqual(counts['existing_spawn_or_v5_mapping'], 2)
        self.assertEqual(counts['dedicated_exact_grant_batch'], 1)

    def test_reference_and_common_assets_are_excluded(self):
        catalog, inventory = self.fixture()
        common = copy.deepcopy(catalog['candidates'][0])
        common.update(id='common', resource_folder='Common')
        reference = copy.deepcopy(common)
        reference.update(id='042_ahua', resource_folder='042_AHua', reference_only=True)
        catalog['candidates'] += [common, reference]
        batches, _ = select(catalog, inventory)
        self.assertEqual(sum(map(len, batches)), 7)

    def test_collection_preserves_capture_when_shutdown_appends_unrelated_logs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            directory = root / 'queue'; directory.mkdir()
            session = '20261118-211942'
            work = root / 'evidence/official-validation' / session
            state = root / 'runtime' / ('official-validation-' + session) / 'state.json'
            write_json(state, dict(restored=True, work=str(work)))
            report = dict(fingerprint='a'*20, script_sha256=hashlib.sha256(b'fixture').hexdigest(), batches=[])
            write_json(directory / 'manifest.json', report)
            def file(suffix):
                return work / f"{collector.LABEL}-{report['fingerprint']}-{suffix}"
            stage = dict(state_file=str(state), research_pid=12, script_sha256=report['script_sha256'],
                         manifest_sha256=collector.sha(directory/'manifest.json'), log_byte_offset=0,
                         log_prefix_sha256=hashlib.sha256(b'').hexdigest())
            write_json(file('staged.json'), stage)
            write_json(file('intent.json'), stage)
            file('metadata.lua').write_bytes(b'fixture')
            write_json(file('results.json'), dict(state_file=str(state), research_pid=12, outcomes=[],
                       lines=['query complete'], metadata_only=True, playable=False))
            (work/'UE4SS.log').write_bytes(b'query complete\nEvent loop end\n')
            with patch.object(collector, 'ROOT', root), patch.object(collector, 'verify', return_value=(report,b'fixture')), \
                 patch.object(collector, 'analyze', return_value=[]), patch.object(collector.core, 'QUERY_LABEL', collector.LABEL):
                self.assertFalse(collector.collect(directory,session)['playable'])
                (work/'UE4SS.log').write_bytes(b'changed capture\n')
                with self.assertRaises(AssertionError):
                    collector.collect(directory,session)


if __name__ == '__main__':
    unittest.main()
