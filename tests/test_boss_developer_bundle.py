import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import build_boss_developer_bundle as bundle
from boss_candidate_gate import validate as candidate_gate


class DeveloperBundleTests(unittest.TestCase):
    def test_real_metadata_pool_excludes_dependencies_story_and_failed_asset(self):
        definition, evidence = bundle.definition()
        pool = definition['ability_pool']
        self.assertEqual(len(pool), 19)
        self.assertTrue(pool[0].endswith('GA_YanQianSui_MiddleAttack_01_C'))
        self.assertTrue(all('/Story/' not in p and 'GA_Hun_' not in p and '_CA_' not in p for p in pool))
        self.assertFalse(any(p.endswith('.GA_YanQianSui_Skill_C') for p in pool))
        self.assertEqual(len(evidence), 3)

    def fixture(self, root):
        for name in bundle.SOURCES:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((bundle.ROOT / name).read_bytes())
        base = root / 'mod/PBZBossControl/Scripts'
        base.mkdir(parents=True)
        (base / 'boss_candidate.lua').write_bytes(b'-- public candidate sentinel\n')
        (base / 'boss_catalog.lua').write_bytes(b'-- public player registry sentinel\n')
        definition = {'id': bundle.IDENTIFIER, 'class_path': '/Fixture.Actor_C',
            'config_path': '/Fixture.Config', 'display_name': 'fixture',
            'identity_receipt_sha256': 'a' * 64, 'ability_metadata_receipt_sha256': 'b' * 64,
            'ability_pool': ['/Fixture.Ability_C']}
        return definition

    def test_deterministic_build_keeps_base_and_exact_override(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            definition = self.fixture(root)
            with patch.object(bundle, 'definition', return_value=(definition, {})):
                target = bundle.build(root)
                self.assertEqual(target, bundle.build(root))
                grant = candidate_gate(bundle.IDENTIFIER, root=root, bundle=target)
                self.assertEqual(grant['ability_metadata_receipt_sha256'], 'b' * 64)
                self.assertEqual((root / 'mod/PBZBossControl/Scripts/boss_candidate.lua').read_bytes(),
                    b'-- public candidate sentinel\n')

    def test_tampered_payload_source_base_or_scope_rejected(self):
        for changed in ('payload', 'source', 'base', 'scope', 'definition', 'extra'):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                definition = self.fixture(root)
                with patch.object(bundle, 'definition', return_value=(definition, {})):
                    target = bundle.build(root)
                    if changed == 'payload':
                        (target / 'boss_candidate.lua').write_text('return {}')
                    elif changed == 'source':
                        (root / bundle.SOURCES[0]).write_text('changed')
                    elif changed == 'base':
                        (root / 'mod/PBZBossControl/Scripts/boss_catalog.lua').write_text('changed')
                    elif changed == 'extra':
                        (target / 'undeclared.lua').write_text('changed')
                    else:
                        manifest = json.loads((target / 'manifest.json').read_text(encoding='utf-8'))
                        if changed == 'scope':
                            manifest['playable'] = True
                        else:
                            manifest['definition']['ability_pool'].append('/Foreign.Ability_C')
                        (target / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
                    with self.assertRaises(AssertionError):
                        bundle.validate(bundle.IDENTIFIER, target, root=root)

    def test_no_bundle_no_promotion_and_foreign_candidate_rejected(self):
        with self.assertRaises(RuntimeError):
            candidate_gate(bundle.IDENTIFIER)
        with self.assertRaises(AssertionError):
            bundle.validate('056_youlong', Path('unused'))

    def test_transitive_evidence_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'proof.json').write_bytes(b'original')
            receipt = {'sources': {'proof.json': bundle.sha(root / 'proof.json')}}
            bundle.validate_sources(receipt, root)
            (root / 'proof.json').write_bytes(b'changed')
            with self.assertRaises(AssertionError):
                bundle.validate_sources(receipt, root)


if __name__ == '__main__':
    unittest.main()
