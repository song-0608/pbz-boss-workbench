import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import prepare_phantom_boss_pair as pair
from build_phantom_boss_candidate import COMMIT, ROOT, build, canonical, sha


class PairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candidate = build()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.parent = Path(self.tmp.name)

    def prepared(self):
        return pair.prepare(self.candidate, output_parent=self.parent)

    def rewrite(self, target, name, data):
        (target / name).write_bytes(data)
        manifest = json.loads((target / 'pair.json').read_bytes())
        manifest['files'][name] = sha(data)
        (target / 'pair.json').write_bytes(canonical(manifest))

    def test_roles_share_protocol_identity_but_keep_independent_save_roots(self):
        target = self.prepared()
        h = json.loads((target / 'host/launch-request.json').read_bytes())
        g = json.loads((target / 'guest/launch-request.json').read_bytes())
        self.assertEqual(h['session'], g['session'])
        self.assertEqual(h['catalog_sha256'], g['catalog_sha256'])
        self.assertEqual((h['role'], g['role']), ('host', 'guest'))
        self.assertNotEqual(h['boss_id'], g['boss_id'])
        self.assertNotEqual((target / 'host/Saved').resolve(), (target / 'guest/Saved').resolve())
        self.assertTrue(pair.verify(target, self.candidate)['passed'])

    def test_repeated_preparation_uses_new_session_and_secret_without_overwriting(self):
        first, second = self.prepared(), self.prepared()
        self.assertNotEqual(first, second)
        self.assertNotEqual((first / 'host/Mods/PBZCoop/PhantomPact.ini').read_bytes(),
                            (second / 'host/Mods/PBZCoop/PhantomPact.ini').read_bytes())
        for target in (first, second):
            host = (target / 'host/Mods/PBZCoop/PhantomPact.ini').read_bytes()
            guest = (target / 'guest/Mods/PBZCoop/PhantomPact.ini').read_bytes()
            self.assertEqual(re.search(rb'Secret = (\w+)', host)[1], re.search(rb'Secret = (\w+)', guest)[1])

    def test_invalid_duration_port_or_boss_does_not_create_a_pair(self):
        for kwargs in ({'port': True}, {'port': 0}, {'port': 65536}, {'duration': 59},
                       {'duration': 1201}, {'host_boss': '../arbitrary'}, {'guest_boss': 'unknown'}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                pair.prepare(self.candidate, output_parent=self.parent, **kwargs)
        self.assertEqual(list(self.parent.iterdir()), [])

    def test_rehashing_changed_transport_cannot_expand_listener_beyond_this_pc(self):
        target = self.prepared()
        name = 'host/Mods/PBZCoop/PhantomPact.ini'
        self.rewrite(target, name, (target / name).read_bytes().replace(b'ThisPCOnly = On', b'ThisPCOnly = Off'))
        with self.assertRaisesRegex(AssertionError, 'relay settings'):
            pair.verify(target, self.candidate)

    def test_unexpected_game_binary_or_save_is_rejected(self):
        target = self.prepared()
        for name in ('host/PBZ.exe', 'guest/Saved/Slot.sav'):
            path = target / name
            path.write_bytes(b'test marker only')
            with self.subTest(name=name), self.assertRaisesRegex(AssertionError, 'unexpected/missing'):
                pair.verify(target, self.candidate)
            path.unlink()

    def test_prepared_request_cannot_issue_a_lease_or_relabel_a_guest(self):
        target = self.prepared()
        name = 'guest/launch-request.json'
        original = (target / name).read_bytes()
        for field, value in (('lease_issued', True), ('role', 'host'), ('saved_directory', '../host/Saved')):
            request = json.loads(original)
            request[field] = value
            self.rewrite(target, name, canonical(request))
            with self.subTest(field=field), self.assertRaises(AssertionError):
                pair.verify(target, self.candidate)

    def test_full_executable_and_catalog_identity_cannot_be_relabelled(self):
        target = self.prepared()
        path = target / 'pair.json'
        original = json.loads(path.read_bytes())
        for key in ('exe_sha256', 'catalog_sha256', 'candidate_manifest_sha256'):
            changed = dict(original)
            changed[key] = 'f' * 64
            path.write_bytes(canonical(changed))
            with self.subTest(key=key), self.assertRaises(AssertionError):
                pair.verify(target, self.candidate)

    def test_generated_settings_use_pinned_native_loopback_and_guest_ephemeral_bind(self):
        source = (ROOT / 'runtime/integration-research/PhantomPact' / COMMIT / 'native/relay.hpp').read_text(encoding='utf-8')
        self.assertIn('lower(ini["thispconly"]) == "on"', source)
        self.assertIn('this_pc_only ? INADDR_LOOPBACK : INADDR_ANY', source)
        self.assertIn('role == "host" ? port : 0', source)
        self.assertIn(b'ThisPCOnly = On\n', pair.ini('guest', 47800, 'a' * 64))


if __name__ == '__main__':
    unittest.main()
