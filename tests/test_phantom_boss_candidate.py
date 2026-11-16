import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import build_phantom_boss_candidate as candidate
import player_keymap


class CandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = candidate.ROOT
        cls.source = cls.root / 'runtime/integration-research/PhantomPact' / candidate.COMMIT
        cls.target = candidate.build()
        cls.manifest = candidate.verify_candidate(cls.target)

    def test_all_19_pinned_upstream_sources_verified(self):
        self.assertEqual(len(candidate.verify_upstream(self.source)), 19)

    def test_source_drift_rejected_even_with_same_commit_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / 'upstream'
            shutil.copytree(self.source, dest)
            path = dest / candidate.SCRIPTS / 'coop.lua'
            path.write_bytes(path.read_bytes() + b'\n-- drift\n')
            with self.assertRaisesRegex(ValueError, 'source drift'):
                candidate.verify_upstream(dest)

    def test_receipt_rewrite_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            receipt = json.loads((self.source / 'source-receipt.json').read_bytes())
            receipt['files'][0]['sha256'] = 'f' * 64
            (dest / 'source-receipt.json').write_text(json.dumps(receipt), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'receipt changed'):
                candidate.verify_upstream(dest)

    def test_path_traversal_absolute_and_windows_paths_rejected(self):
        for name in ('../outside', '/absolute', 'C:/outside', 'a\\b', './file', 'a/../b'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                candidate.safe_file(self.root, name)

    def test_accepted_release_and_40_ability_catalog_are_hash_verified(self):
        release, data = candidate.verify_release(self.root)
        self.assertEqual(data['ability_count'], 40)
        bosses = json.loads((self.target / 'catalog.json').read_bytes())
        self.assertEqual(sum(len(row['actions']) for row in bosses.values()), 40)
        self.assertEqual(candidate.sha(candidate.canonical(bosses)), self.manifest['catalog_sha256'])
        self.assertEqual(data['exe_sha256'], '4415933ce33476f14c837abb61a1b60af8b78cd81783896501913a7aac69e423')
        self.assertTrue(release.is_dir())

    def test_payload_drift_in_singleplayer_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            release = root / 'releases' / candidate.RELEASE
            shutil.copytree(self.root / 'releases' / candidate.RELEASE, release)
            (release / 'PBZBossControl/Scripts/main.lua').write_text('-- drift\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'payload changed'):
                candidate.verify_release(root)

    def test_build_is_deterministic_and_does_not_inherit_offline_acceptance(self):
        self.assertEqual(candidate.build(), self.target)
        for key in ('complete_mod', 'runtime_acceptance_current', 'installed', 'game_started',
                    'native_relay_executed', 'runtime_tests_inherited'):
            self.assertIs(self.manifest[key], False)
        self.assertTrue(self.manifest['source_only'])
        self.assertEqual(len(self.manifest['pending']), 5)

    def test_all_patches_are_exact_unique_reversible_edits(self):
        for name, replacements in candidate.patches().items():
            with self.subTest(name=name):
                original = (self.source / candidate.SCRIPTS / name).read_text(encoding='utf-8')
                patched = candidate.patch_source(name, original)
                self.assertEqual(patched, (self.target / 'upstream-local-patches' / name).read_text(encoding='utf-8'))
                for old, new in reversed(replacements):
                    self.assertEqual(patched.count(new), 1)
                    patched = patched.replace(new, old, 1)
                self.assertEqual(patched, original)
                with self.assertRaisesRegex(ValueError, 'anchor'):
                    candidate.patch_source(name, '')
                with self.assertRaisesRegex(ValueError, 'anchor'):
                    candidate.patch_source(name, original + original)

    def test_polling_key_conflicts_removed_and_home_end_not_boss_bindings(self):
        patched = self.target / 'upstream-local-patches'
        self.assertIn('kit.key("Home")', (patched / 'onlinepanel.lua').read_text(encoding='utf-8'))
        self.assertIn('kit.key("End")', (patched / 'partner.lua').read_text(encoding='utf-8'))
        for key in ('HOME', 'END'):
            self.assertNotIn(key, player_keymap.ALLOWED)
        for name, bad in [('onlinepanel.lua', 'kit.key("F5")'), ('partner.lua', 'kit.key("F3")'),
                          ('pvppanel.lua', 'kit.key("F6")'), ('panel.lua', 'IsInputKeyDown(key("F4"))')]:
            self.assertNotIn(bad, (patched / name).read_text(encoding='utf-8'))
        self.assertIn('local DEV_KEYS = false', (patched / 'main.lua').read_text(encoding='utf-8'))

    def test_missing_launcher_exits_before_native_module_initialization(self):
        main = (self.target / 'upstream-local-patches/main.lua').read_text(encoding='utf-8')
        self.assertLess(main.index('PBZBossOnlineResearchLaunch'), main.index('local VERSION'))
        self.assertLess(main.index('bwb_entry.lua'), main.index('autostart.lua'))
        self.assertNotIn('enabled.txt', self.manifest['files'])
        self.assertFalse(any(Path(name).suffix.lower() in ('.dll', '.exe', '.sav', '.pak') for name in self.manifest['files']))

    def test_candidate_tamper_or_unlisted_binary_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / 'candidate'
            shutil.copytree(self.target, dest)
            rogue = dest / 'enabled.txt'
            rogue.write_text('1', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Unexpected/missing'):
                candidate.verify_candidate(dest)
            rogue.unlink()
            (dest / 'PBZCoop/Scripts/bwb_protocol.lua').write_text('-- drift', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'payload drift'):
                candidate.verify_candidate(dest)

    def test_source_only_manifest_cannot_claim_runtime_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            data = copy.deepcopy(self.manifest)
            data['runtime_acceptance_current'] = True
            (dest / 'candidate.json').write_text(json.dumps(data), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'unaccepted'):
                candidate.verify_candidate(dest)

    def test_fingerprint_prevents_rehashing_modified_payload_under_same_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            data = copy.deepcopy(self.manifest)
            data['files']['PBZCoop/Scripts/bwb_protocol.lua'] = 'f' * 64
            (dest / 'candidate.json').write_text(json.dumps(data), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'fingerprint'):
                candidate.verify_candidate(dest)

    def test_manifest_cannot_relabel_itself_as_installed_or_live_verified(self):
        for key in ('installed', 'game_started', 'native_relay_executed', 'runtime_tests_inherited'):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as tmp:
                dest = Path(tmp)
                data = copy.deepcopy(self.manifest); data[key] = True
                (dest / 'candidate.json').write_text(json.dumps(data), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'unaccepted'):
                    candidate.verify_candidate(dest)


if __name__ == '__main__':
    unittest.main()
