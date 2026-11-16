"""Regress standalone menu/visual samplers against the shared role-bound reader."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import collect_phantom_boss_control_contract as control
import collect_phantom_boss_workbench_contract as workbench
import collect_phantom_boss_visual_contract as visual
from test_phantom_boss_control_contract import MetadataGame

DOMAINS=(workbench,visual)


class OptionalGame(MetadataGame):
    def __init__(self,domain):
        super().__init__();self.domain=domain
        self.paths=sorted(domain.FUNCTIONS|domain.PROPERTIES.keys()|domain.ENUMS)
        self.addresses={path:0x10000+index*0x1000 for index,path in enumerate(self.paths)}
        self.owners={address:path for path,address in self.addresses.items()}
    def reflected_fields(self,game,address,maximum):
        path=self.owners[address]
        if path in self.domain.FUNCTIONS:
            assert maximum==33
            return [dict(name='ReturnValue',property_flags='0x580',type='BoolProperty',
                offset='0x0',element_size=1,array_dim=1)]
        assert maximum==513
        return [dict(name=name,property_flags='0x0',type='IntProperty',offset='0x20',element_size=4,array_dim=1)
            for name in sorted(self.domain.PROPERTIES[path])]


class OptionalContractTests(unittest.TestCase):
    def capture(self,domain,game):
        with patch.object(control,'fields',side_effect=game.reflected_fields):return domain.capture(game)

    def test_each_standalone_domain_uses_one_pass_with_all_required_namespaces(self):
        for domain in DOMAINS:
            with self.subTest(domain=domain.__name__):
                game=OptionalGame(domain);result=self.capture(domain,game)
                self.assertEqual(len(game.find_calls),1)
                self.assertTrue(result['complete_requested_declarations'])
                for path in game.paths:self.assertTrue(path.startswith(game.find_calls[0][1]))

    def test_menu_captures_widget_image_types_and_visibility_enum_without_loading_a_widget(self):
        result=self.capture(workbench,OptionalGame(workbench))
        self.assertEqual({r['path']for r in result['classes']},set(workbench.PROPERTIES))
        self.assertEqual({r['path']for r in result['enums']},workbench.ENUMS)
        self.assertFalse(result['widget_created']);self.assertFalse(result['blueprint_image_component_verified'])

    def test_visual_captures_animation_and_collision_enums_without_accepting_manual_pose(self):
        result=self.capture(visual,OptionalGame(visual))
        self.assertEqual({r['path']for r in result['enums']},visual.ENUMS)
        self.assertFalse(result['manual_pose_no_notifies_accepted'])

    def test_both_domains_capture_parameter_count_and_return_offset(self):
        for domain in DOMAINS:
            result=self.capture(domain,OptionalGame(domain))
            self.assertTrue(all(r['parameter_count']==1 and r['return_offset']==0 for r in result['functions']))

    def test_missing_class_property_enum_and_function_are_not_silently_complete(self):
        for domain in DOMAINS:
            game=OptionalGame(domain)
            game.removed={next(iter(domain.FUNCTIONS)),next(iter(domain.PROPERTIES)),next(iter(domain.ENUMS))}
            result=self.capture(domain,game)
            self.assertFalse(result['complete_requested_declarations'])
            for key in ('missing_functions','missing_classes','missing_enums'):self.assertTrue(result[key])
        game=OptionalGame(visual);original=game.reflected_fields
        def fields(g,address,maximum):
            return []if game.owners[address]in visual.PROPERTIES else original(g,address,maximum)
        game.reflected_fields=fields
        self.assertTrue(self.capture(visual,game)['missing_properties'])

    def test_duplicate_reflected_paths_are_rejected_instead_of_accepting_first(self):
        for domain in DOMAINS:
            game=OptionalGame(domain);game.duplicate=True
            with self.subTest(domain=domain.__name__),self.assertRaisesRegex(ValueError,'ambiguous'):
                self.capture(domain,game)

    def test_parameter_and_property_overflow_rejects_before_report_publication(self):
        for domain in DOMAINS:
            for parameter in (False,True):
                game=OptionalGame(domain);original=game.reflected_fields
                def fields(g,address,maximum):
                    if (game.owners[address]in domain.FUNCTIONS)==parameter:return [{}]*maximum
                    return original(g,address,maximum)
                game.reflected_fields=fields
                with self.subTest(domain=domain.__name__,parameter=parameter),self.assertRaisesRegex(ValueError,'chain exceeds bound'):
                    self.capture(domain,game)

    def test_complete_metadata_never_grants_runtime_or_native_bindings(self):
        for domain in DOMAINS:
            result=self.capture(domain,OptionalGame(domain))
            for name in ('binding_verified','game_functions_called','inventory_inspected','memory_written','runtime_acceptance_current'):
                self.assertIs(result[name],False)

    def publish(self,domain,path,game,validate=None,identity=None):
        with patch.object(control,'OnlineGameRead',return_value=game),\
                patch.object(control,'fields',side_effect=game.reflected_fields),\
                patch.object(control,'validate_receipt',side_effect=validate or(lambda *_:(dict(session='b'*32),game.instance))),\
                patch('phantom_boss_pair_session.process_identity',return_value=identity or game.instance['game_identity']):
            return domain.collect(path,'guest')

    def test_unique_reports_include_original_process_activation_source_hashes_and_role(self):
        for domain in DOMAINS:
            with tempfile.TemporaryDirectory()as name:
                path=Path(name)/'session.json';path.write_bytes(b'{}');game=OptionalGame(domain)
                a=self.publish(domain,path,game);b=self.publish(domain,path,game)
                self.assertEqual(len(list(path.parent.glob('guest-*-declarations-*.json'))),2)
                for result in (a,b):
                    self.assertEqual(result['role'],'guest');self.assertEqual(result['pid'],42)
                    self.assertEqual(result['activation'],game.instance['activation'])
                    self.assertEqual(result['game_identity'],game.instance['game_identity'])
                    self.assertEqual(set(result['source_sha256']),set(domain.SOURCES))
                self.assertEqual(path.read_bytes(),b'{}')

    def test_expired_receipt_prevents_publication_for_both_standalone_domains(self):
        def expired(*_):raise AssertionError('expired lease')
        for domain in DOMAINS:
            with tempfile.TemporaryDirectory()as name:
                path=Path(name)/'session.json';path.write_bytes(b'{}')
                with self.assertRaisesRegex(AssertionError,'expired lease'):
                    self.publish(domain,path,OptionalGame(domain),validate=expired)
                self.assertEqual(list(path.parent.iterdir()),[path])

    def test_reused_pid_or_replaced_activation_cannot_publish_old_role_metadata(self):
        for domain in DOMAINS:
            for change_activation in (False,True):
                with tempfile.TemporaryDirectory()as name:
                    path=Path(name)/'session.json';path.write_bytes(b'{}');game=OptionalGame(domain)
                    latest=copy.deepcopy(game.instance)
                    if change_activation:latest['activation']='c'*32
                    with self.assertRaises(AssertionError):
                        self.publish(domain,path,game,validate=lambda *_:(dict(session='b'*32),latest),
                            identity=dict(pid=42,created=2))
                    self.assertEqual(list(path.parent.iterdir()),[path])

    def test_receipt_changed_during_capture_prevents_either_domain_report(self):
        for domain in DOMAINS:
            with tempfile.TemporaryDirectory()as name:
                path=Path(name)/'session.json';path.write_bytes(b'{}');game=OptionalGame(domain)
                def changed(*_):path.write_bytes(b'changed');return dict(session='b'*32),game.instance
                with self.assertRaises(AssertionError):self.publish(domain,path,game,validate=changed)
                self.assertEqual(list(path.parent.iterdir()),[path])

    def test_sampler_never_modifies_an_existing_activation_file(self):
        for domain in DOMAINS:
            with tempfile.TemporaryDirectory()as name:
                path=Path(name)/'session.json';path.write_bytes(b'{}')
                gate=path.parent/'bwb_current_bindings.lua';gate.write_bytes(b'existing owned binding')
                self.publish(domain,path,OptionalGame(domain))
                self.assertEqual(gate.read_bytes(),b'existing owned binding')

    def test_source_change_while_sampling_prevents_either_domain_report(self):
        for domain in DOMAINS:
            with tempfile.TemporaryDirectory()as name:
                path=Path(name)/'session.json';path.write_bytes(b'{}');game=OptionalGame(domain)
                original=control.sha;calls=0
                def sha(data):
                    nonlocal calls
                    calls+=1;return original(data)if calls<=len(domain.SOURCES)else'changed'
                with patch.object(control,'sha',side_effect=sha),self.assertRaisesRegex(AssertionError,'collector sources changed'):
                    self.publish(domain,path,game)
                self.assertEqual(list(path.parent.iterdir()),[path])


if __name__=='__main__':unittest.main()
