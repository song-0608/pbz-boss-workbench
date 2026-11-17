import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import release_boss_skill_workbench as release


class SkillReleaseInheritanceTests(unittest.TestCase):
    def fixture(self):
        source=release.ROOT/'releases'/release.builder.BASE
        manifest=copy.deepcopy(release.validate_package(source))
        manifest['previous_release_manifest_sha256']=release.sha(source/release.MANIFEST)
        names={'PBZBossControl/Scripts/boss_catalog.lua',*(
            'PBZBossControl/Scripts/profiles/'+name+suffix+'.lua'
            for name in release.builder.PROFILES.values() for suffix in ('','_bindings'))}
        for name in names:manifest['files'][name]='0'*64
        return manifest

    def test_exact_profile_expansion_preserves_shared_runtime(self):
        result=release.inherited(self.fixture())
        self.assertTrue(result['unchanged_runtime_camera_input_restoration'])

    def test_changed_execution_or_forged_base_breaks_inheritance(self):
        manifest=self.fixture();manifest['files']['PBZBossControl/Scripts/runtime.lua']='0'*64
        with self.assertRaises(AssertionError):release.inherited(manifest)
        manifest=self.fixture();manifest['previous_release_manifest_sha256']='0'*64
        with self.assertRaises(AssertionError):release.inherited(manifest)


if __name__=='__main__':unittest.main()
