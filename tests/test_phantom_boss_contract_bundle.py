"""Exercise one-pass declaration sampling without starting or writing to a game."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import collect_phantom_boss_contract_bundle as bundle
import collect_phantom_boss_control_contract as control
import collect_phantom_boss_visual_contract as visual
import collect_phantom_boss_workbench_contract as workbench
from test_phantom_boss_control_contract import MetadataGame


class BundleGame(MetadataGame):
    def __init__(self):
        super().__init__()
        self.paths=sorted(bundle.FUNCTIONS|bundle.PROPERTIES.keys()|bundle.ENUMS)
        self.addresses={path:0x10000+index*0x1000 for index,path in enumerate(self.paths)}
        self.owners={address:path for path,address in self.addresses.items()}
    def reflected_fields(self,game,address,maximum):
        path=self.owners[address]
        if path in bundle.FUNCTIONS:
            assert maximum==33
            return [dict(name='ReturnValue',property_flags='0x580',type='BoolProperty',
                offset='0x0',element_size=1,array_dim=1)]
        assert maximum==513
        return [dict(name=name,property_flags='0x0',type='IntProperty',offset='0x20',element_size=4,array_dim=1)
            for name in sorted(bundle.PROPERTIES[path])]


class BundleTests(unittest.TestCase):
    def capture(self,game):
        with patch.object(control,'fields',side_effect=game.reflected_fields):return bundle.capture(game)

    def test_every_control_visual_and_umg_function_is_sampled_in_one_pass(self):
        game=BundleGame();result=self.capture(game)
        self.assertEqual(len(game.find_calls),1)
        self.assertEqual({r['path'] for r in result['functions']},control.FUNCTIONS|visual.FUNCTIONS|workbench.FUNCTIONS)
        self.assertTrue(result['complete_requested_declarations'])
        self.assertIn('/Script/UMG.',game.find_calls[0][1])
        self.assertEqual(len(result['enums']),8)

    def test_property_union_does_not_drop_control_or_visual_fields(self):
        before=copy.deepcopy(control.PROPERTIES)
        result=self.capture(BundleGame())
        self.assertEqual(control.PROPERTIES,before)
        found={(p['owner'],p['name']) for p in result['properties']}
        for requested in (control.PROPERTIES,visual.PROPERTIES,workbench.PROPERTIES):
            for owner,names in requested.items():
                for name in names:self.assertIn((owner,name),found)
        self.assertEqual(len(found),len(result['properties']))

    def test_complete_bundle_does_not_accept_bindings_widgets_or_manual_animation(self):
        result=self.capture(BundleGame())
        for name in ('binding_verified','widget_created','manual_pose_no_notifies_accepted','blueprint_image_component_verified',
                'game_functions_called','inventory_inspected','memory_written','runtime_acceptance_current'):
            self.assertIs(result[name],False)
        self.assertEqual(result['domains'],['control','workbench','visual'])

    def test_request_fingerprint_changes_when_requested_interface_changes(self):
        initial=self.capture(BundleGame())['request_sha256']
        self.assertEqual(initial,self.capture(BundleGame())['request_sha256'])
        with patch.object(bundle,'FUNCTIONS',bundle.FUNCTIONS|{'/Script/UMG.Widget.Nonexistent'}):
            self.assertNotEqual(initial,self.capture(BundleGame())['request_sha256'])

    def test_missing_visual_function_and_umg_enum_remain_missing(self):
        game=BundleGame();game.removed={'/Script/UMG.ESlateVisibility','/Script/Engine.SkeletalMeshComponent.SetPosition'}
        result=self.capture(game)
        self.assertFalse(result['complete_requested_declarations'])
        self.assertEqual(result['missing_functions'],['/Script/Engine.SkeletalMeshComponent.SetPosition'])
        self.assertEqual(result['missing_enums'],['/Script/UMG.ESlateVisibility'])

    def test_duplicate_metadata_path_rejects_entire_bundle(self):
        game=BundleGame();game.duplicate=True
        with self.assertRaisesRegex(ValueError,'ambiguous'):self.capture(game)

    def test_bundle_publication_is_unique_bound_to_role_and_never_writes_activation(self):
        with tempfile.TemporaryDirectory() as name:
            receipt=Path(name)/'session.json';receipt.write_bytes(b'{}');game=BundleGame()
            with patch.object(control,'OnlineGameRead',return_value=game),\
                    patch.object(control,'fields',side_effect=game.reflected_fields),\
                    patch.object(control,'validate_receipt',return_value=(dict(session='b'*32),game.instance)),\
                    patch('phantom_boss_pair_session.process_identity',return_value=game.instance['game_identity']):
                first=bundle.collect(receipt,'host');second=bundle.collect(receipt,'host')
            reports=list(receipt.parent.glob('host-native-bundle-declarations-*.json'))
            self.assertEqual(len(reports),2)
            self.assertEqual({p.name for p in receipt.parent.iterdir()},{receipt.name,*[p.name for p in reports]})
            self.assertEqual(first['activation'],second['activation'])
            self.assertEqual(first['role'],'host')
            self.assertEqual(set(first['source_sha256']),set(bundle.SOURCES))
            self.assertFalse(json.loads(reports[0].read_bytes())['binding_verified'])

    def test_source_changes_during_collection_prevent_publication(self):
        with tempfile.TemporaryDirectory() as name:
            receipt=Path(name)/'session.json';receipt.write_bytes(b'{}');game=BundleGame()
            real_sha=control.sha;counter=0
            def sha(data):
                nonlocal counter
                counter+=1
                return real_sha(data) if counter<=len(bundle.SOURCES) else 'changed'
            with patch.object(control,'OnlineGameRead',return_value=game),\
                    patch.object(control,'sha',side_effect=sha),patch.object(bundle,'capture',return_value={}),\
                    patch.object(control,'validate_receipt',return_value=(dict(session='b'*32),game.instance)),\
                    patch('phantom_boss_pair_session.process_identity',return_value=game.instance['game_identity']),\
                    self.assertRaisesRegex(AssertionError,'collector sources changed'):
                bundle.collect(receipt,'guest')
            self.assertEqual(list(receipt.parent.iterdir()),[receipt])


if __name__=='__main__':unittest.main()
