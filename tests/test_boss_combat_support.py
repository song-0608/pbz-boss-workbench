import csv
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import boss_combat_support as support
import boss_disk_declarations as disk


class CombatSupportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.index = self.root/'index.csv'
        self.mapping = self.root/'exact.usmap'
        self.mapping.write_bytes(b'exact fixture mapping')

    def rows(self, paths):
        with self.index.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=['Filename', 'ChunkType', 'Hash'])
            writer.writeheader()
            for path in paths:
                writer.writerow(dict(Filename='../../../'+path, ChunkType='ExportBundleData', Hash='a'))

    def test_real_deflect_plugin_and_separate_input_context_are_in_scope(self):
        paths = [support.DEFLECT+'Abilities/BP_StanceAction_Base_NPC.uasset',
                 support.INPUT+'IMC_Deflect.uasset',
                 support.COMBAT+'Prototypes/Actions/GAAction_WeaponParticle_BlueRedEye.uasset',
                 support.COMBAT+'ActorData/Players/Hun/Abilities/LongBlade/GA_Hun_Long_Stance.uasset']
        self.rows(paths+[support.COMBAT+'Prototypes/GameplayEffects/GE_Resistance.uasset',
                         support.COMBAT+'ActorData/Players/Hun/Montage/Deflect/AM_Hit.uasset',
                         support.DEFLECT+'../Outside.uasset'])
        self.assertEqual({r['package'] for r in support.selected_packages(self.index)}, set(paths))

    def test_plan_remains_bounded_immutable_and_not_playable(self):
        self.rows([support.DEFLECT+f'Actions/GAA_Test_{i}.uasset' for i in range(65)])
        target = self.root/'support'
        result = support.plan(self.index, self.mapping, target)
        self.assertEqual([len(b['packages']) for b in result['batches']], [64, 1])
        self.assertEqual(disk.checked_plan(target)[1], result)
        self.assertEqual(disk.summarize(target)['pending'], 65)
        self.assertFalse(result['playable'])
        self.assertFalse(result['game_started'])
        with self.assertRaises(FileExistsError):
            support.plan(self.index, self.mapping, target)
        job = target/result['batches'][0]['job']
        job.write_text('{}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'job changed'):
            disk.checked_plan(target)

    def test_role_weapon_configs_and_shared_defense_config_are_selected_exactly(self):
        selected = [support.COMBAT+'ActorData/Mobs/056_YouLong/Config/Weapon_YouLong_Harpoon.uasset',
                    support.COMBAT+'ActorData/Mobs/038_AquaKiller/Config/Weapon_AquaKiller_YuCha.uasset',
                    *sorted(support.SHARED)]
        excluded = [support.COMBAT+'ActorData/Mobs/999_Unknown/Config/Weapon_Unknown.uasset',
                    support.COMBAT+'ActorData/Mobs/056_YouLong/Mesh/SM_Weapon.uasset',
                    support.COMBAT+'Prototypes/Config/Unrelated.uasset']
        self.rows(selected+excluded)
        self.assertEqual({r['package'] for r in support.selected_packages(self.index)}, set(selected))

    def test_conflicting_index_and_excessive_scope_are_rejected(self):
        self.rows([support.DEFLECT+f'Actions/GAA_Test_{i}.uasset' for i in range(257)])
        with self.assertRaisesRegex(ValueError, '1–256'):
            support.plan(self.index, self.mapping, self.root/'too-many')
        self.assertFalse((self.root/'too-many').exists())
        self.rows([support.INPUT+'IMC_Deflect.uasset'])
        with self.index.open('a', encoding='utf-8') as stream:
            stream.write('../../../'+support.INPUT+'IMC_Deflect.uasset,ExportBundleData,b\n')
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            support.selected_packages(self.index)


if __name__ == '__main__':
    unittest.main()
