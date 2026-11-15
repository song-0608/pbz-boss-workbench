import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import youlong_metadata as metadata


class YouLongMetadataTests(unittest.TestCase):
    def test_real_plan_reuses_harpoon_identity_and_32_names(self):
        requests, sources = metadata.definition()
        self.assertEqual(len(requests), 32)
        self.assertEqual(len({r['lookup_path'] for r in requests}), 32)
        self.assertEqual(set(sources), {metadata.IDENTITY, metadata.DOSSIER})
        self.assertTrue(all(r['role'] == 'ability' and r['id'] == '056_youlong'
                            and r['playable'] is False and r['granted_to_actor'] is False for r in requests))

    def fixture(self, root):
        for name in metadata.SOURCES:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((metadata.ROOT / name).read_bytes())
        proof = root / 'closed-identity.json'
        proof.write_text('{}')
        requests = [{'id': metadata.IDENTIFIER, 'role': 'ability', 'package': '/Fixture/GA_Action',
                     'lookup_path': '/Fixture/GA_Action.GA_Action_C', 'playable': False, 'granted_to_actor': False}]
        return requests, {'closed-identity.json': metadata.sha(proof)}

    def test_frozen_batch_deterministic_and_tamper_rejected(self):
        for changed in ('payload', 'source', 'identity', 'scope', 'extra'):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                definition = self.fixture(root)
                with patch.object(metadata, 'definition', return_value=definition):
                    target = metadata.build(root)
                    self.assertEqual(target, metadata.build(root))
                    probe = metadata.verify(target, root)
                    self.assertEqual(probe['requests'], [])
                    if changed == 'payload':
                        (target / 'identity-probe.lua').write_text('changed')
                    elif changed == 'source':
                        (root / metadata.SOURCES[0]).write_text('changed')
                    elif changed == 'identity':
                        (root / 'closed-identity.json').write_text('changed')
                    elif changed == 'extra':
                        (target / 'undeclared.lua').write_text('changed')
                    else:
                        path = target / 'manifest.json'
                        manifest = json.loads(path.read_text())
                        manifest['ability_activation_allowed'] = True
                        path.write_text(json.dumps(manifest))
                    with self.assertRaises(AssertionError):
                        metadata.verify(target, root)

    def test_every_request_requires_one_exact_outcome(self):
        probe = {'batch_fingerprint': 'fixture', 'ability_requests': [
            {'id': metadata.IDENTIFIER, 'lookup_path': '/Fixture/GA_Action.GA_Action_C'}]}
        start, end = 'PBZ_BOSS_META:START=fixture', 'PBZ_BOSS_META:END=fixture'
        outcome = 'PBZ_BOSS_META:ABILITY=056_youlong|/Fixture/GA_Action.GA_Action_C|leaf'
        valid = metadata.analyze([start, outcome, end], probe)
        self.assertTrue(valid[0]['metadata_verified'])
        self.assertFalse(valid[0]['live_grant_verified'])
        self.assertFalse(valid[0]['playable'])
        for rows in ([start, end], [start, outcome, outcome, end], [start, outcome],
                     [start, outcome.replace('056_youlong', '073_yanqiansui'), end]):
            with self.subTest(rows=rows), self.assertRaises(AssertionError):
                metadata.analyze(rows, probe)


if __name__ == '__main__':
    unittest.main()
