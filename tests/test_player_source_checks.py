"""Source regression fixtures must not manage packages or active research sessions."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import check_player_travel_repair as checks


class SourceCheckTests(unittest.TestCase):
    def test_source_only_never_builds_or_freezes_a_package(self):
        manifest = {'release_id': 'fixture'}
        files = {'PBZBossControl/Scripts/fixture.lua': b'return true\n',
                 'not-a-test.bin': b'not staged'}
        staged = []

        def run(package, actual, flow=None, *, source_only=False):
            staged.append(package)
            self.assertIs(actual, manifest)
            self.assertTrue(source_only)
            self.assertIsNone(flow)
            self.assertEqual((package / 'PBZBossControl/Scripts/fixture.lua').read_bytes(),
                             files['PBZBossControl/Scripts/fixture.lua'])
            self.assertEqual(len(list(package.rglob('*.*'))), 1)
            self.assertFalse((package / 'pbz-release.json').exists())
            return 0

        with patch.object(checks.candidate, 'expected', return_value=(manifest, files)), \
                patch.object(checks.candidate, 'build', side_effect=AssertionError('package build forbidden')), \
                patch.object(checks.candidate, 'verify', side_effect=AssertionError('package verification forbidden')), \
                patch.object(checks.workflow, 'build', side_effect=AssertionError('workflow freeze forbidden')), \
                patch.object(checks, 'check', side_effect=run):
            self.assertEqual(checks.main(source_only=True), 0)
        self.assertEqual(len(staged), 1)
        self.assertFalse(staged[0].exists(), 'disposable source fixture must be removed')

    def test_normal_mode_still_requires_the_guarded_package_path(self):
        package, flow, manifest = Path('guarded-package'), Path('guarded-flow'), {'fixture': True}
        with patch.object(checks.candidate, 'build', return_value=package) as build, \
                patch.object(checks.candidate, 'verify', return_value=manifest) as verify, \
                patch.object(checks.workflow, 'build', return_value=flow) as freeze, \
                patch.object(checks, 'check', return_value=0) as run:
            self.assertEqual(checks.main(), 0)
        build.assert_called_once_with()
        verify.assert_called_once_with(package)
        freeze.assert_called_once_with(package)
        run.assert_called_once_with(package, manifest, flow)


if __name__ == '__main__':
    unittest.main()
