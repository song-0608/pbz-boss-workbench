import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import collect_phantom_boss_control_contract as control
import collect_phantom_boss_workbench_contract as workbench


class MetadataGame:
    """Synthetic reflected metadata only; deliberately no write or gameplay API."""
    def __init__(self):
        self.pid=42
        self.instance=dict(activation='a'*32,game_identity=dict(pid=42,created=1))
        self.paths=sorted(control.FUNCTIONS|control.PROPERTIES.keys()|control.ENUMS)
        self.addresses={path:0x10000+index*0x1000 for index,path in enumerate(self.paths)}
        self.owners={address:path for path,address in self.addresses.items()}
        self.find_calls=[];self.duplicate=False;self.removed=set();self.missing_property=False
        self.enum_count=2;self.wrong_kind=False;self.duplicate_name=False
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def find_native(self,names,prefixes):
        self.find_calls.append((names,prefixes))
        rows=[dict(path=path,address=hex(address),**{'class':1})
            for path,address in self.addresses.items()
            if path.rsplit('.',1)[1] in names and path.startswith(prefixes) and path not in self.removed]
        if self.duplicate:rows.append(rows[0])
        return rows
    def reflected_fields(self,game,address,maximum):
        path=self.owners[address]
        if path in control.FUNCTIONS:
            self.assert_maximum=maximum
            return [dict(name='ReturnValue',property_flags='0x480',type='BoolProperty',offset='0x0',element_size=1,array_dim=1),
                dict(name='NonParameter',property_flags='0x0')]
        assert maximum==513
        names=sorted(control.PROPERTIES[path])
        if self.missing_property:names=[]
        return [dict(name=name,property_flags='0x0',type='IntProperty',offset='0x20',element_size=4,array_dim=1) for name in names]
    def read(self,address,length):
        for base in self.owners:
            if address==base+0x106:return struct.pack('<H',1)
            if address==base+0x104:return bytes([1])
            if address==base+0x108:return struct.pack('<H',0)
            if address==base+0x40:return struct.pack('<QQi4x',0x100000,0x200000,self.enum_count)
        if 0x100000<=address<0x101000:return struct.pack('<II',(address-0x100000)//8,0)
        if 0x200000<=address<0x201000:return struct.pack('<q',-1+(address-0x200000)//8)
        raise AssertionError('unexpected metadata read')
    def u32(self,address):
        assert address-0xa8 in self.owners
        return 128
    def header(self,address):
        assert address==1
        return dict(name='Function' if self.wrong_kind else 'Enum')
    def name(self,index,number):return 'Value' if self.duplicate_name else 'Value'+str(index)


class ControlContractTests(unittest.TestCase):
    def test_one_metadata_pass_includes_every_requested_namespace_without_verifying_bindings(self):
        game=MetadataGame()
        with patch.object(control,'fields',side_effect=game.reflected_fields):result=control.capture(game)
        self.assertTrue(result['complete_requested_declarations'])
        self.assertEqual(len(game.find_calls),1)
        for path in game.paths:self.assertTrue(path.startswith(game.find_calls[0][1]),path)
        for key in ('binding_verified','game_functions_called','inventory_inspected','memory_written','runtime_acceptance_current'):
            self.assertIs(result[key],False)

    def test_function_parameters_exclude_non_parameter_properties(self):
        game=MetadataGame()
        with patch.object(control,'fields',side_effect=game.reflected_fields):result=control.capture(game)
        self.assertEqual(game.assert_maximum,33)
        self.assertTrue(all([p['name'] for p in row['parameters']]==['ReturnValue'] for row in result['functions']))

    def test_ambiguous_native_path_rejects_instead_of_accepting_first_object(self):
        game=MetadataGame();game.duplicate=True
        with patch.object(control,'fields',side_effect=game.reflected_fields),self.assertRaisesRegex(ValueError,'ambiguous'):
            control.capture(game)

    def test_missing_function_cannot_become_a_complete_contract(self):
        game=MetadataGame();path=next(iter(control.ARENA_FUNCTIONS));game.removed={path}
        with patch.object(control,'fields',side_effect=game.reflected_fields):result=control.capture(game)
        self.assertEqual(result['missing_functions'],[path]);self.assertFalse(result['complete_requested_declarations'])

    def test_absent_properties_classes_and_enums_are_all_reported(self):
        game=MetadataGame();game.missing_property=True
        game.removed={'/Script/Engine.InputComponent','/Script/AIModule.ETeamAttitude'}
        with patch.object(control,'fields',side_effect=game.reflected_fields):result=control.capture(game)
        self.assertIn('/Script/Engine.InputComponent',result['missing_classes'])
        self.assertIn('/Script/Engine.Actor:bBlockInput',result['missing_properties'])
        self.assertEqual(result['missing_enums'],['/Script/AIModule.ETeamAttitude'])
        self.assertFalse(result['complete_requested_declarations'])

    def test_wrong_reflection_kind_cannot_supply_enum_values(self):
        game=MetadataGame();game.wrong_kind=True
        with patch.object(control,'fields',side_effect=game.reflected_fields),self.assertRaisesRegex(ValueError,'enum kind'):
            control.capture(game)

    def test_enum_count_is_bounded_before_following_name_and_value_arrays(self):
        for count in (0,-1,513):
            game=MetadataGame();game.enum_count=count
            with self.subTest(count=count),self.assertRaisesRegex(ValueError,'bounded control enum'):
                control.enum_rows(game,next(iter(game.owners)))

    def test_duplicate_enum_names_reject_and_signed_values_are_preserved(self):
        game=MetadataGame();address=next(iter(game.owners))
        self.assertEqual([r['value'] for r in control.enum_rows(game,address)],[-1,0])
        game.duplicate_name=True
        with self.assertRaisesRegex(ValueError,'duplicate control enum'):control.enum_rows(game,address)

    def test_parameter_chain_truncation_cannot_be_reported_as_complete(self):
        game=MetadataGame()
        with patch.object(control,'fields',return_value=[{}]*33),self.assertRaisesRegex(ValueError,'parameter chain exceeds bound'):
            control.capture(game)

    def test_property_chain_truncation_cannot_hide_a_required_field(self):
        game=MetadataGame()
        def fields(g,address,maximum):
            if game.owners[address]in control.PROPERTIES:return [{}]*513
            return game.reflected_fields(g,address,maximum)
        with patch.object(control,'fields',side_effect=fields),self.assertRaisesRegex(ValueError,'property chain exceeds bound'):
            control.capture(game)

    def test_published_report_belongs_to_exact_role_process_and_activation_and_leaves_gate_untouched(self):
        with tempfile.TemporaryDirectory() as name:
            receipt=Path(name)/'session.json';receipt.write_bytes(b'{}')
            game=MetadataGame();session=dict(session='b'*32)
            with patch.object(control,'OnlineGameRead',return_value=game),\
                    patch.object(control,'fields',side_effect=game.reflected_fields),\
                    patch.object(control,'validate_receipt',return_value=(session,game.instance)),\
                    patch('phantom_boss_pair_session.process_identity',return_value=game.instance['game_identity']):
                result=control.collect(receipt,'guest')
            reports=list(receipt.parent.glob('guest-control-declarations-*.json'))
            self.assertEqual(len(reports),1);self.assertEqual(json.loads(reports[0].read_bytes()),result)
            self.assertEqual(result['role'],'guest');self.assertEqual(result['pid'],42)
            self.assertEqual(result['activation'],'a'*32);self.assertFalse(result['binding_verified'])
            self.assertEqual(len(list(receipt.parent.iterdir())),2)

    def test_expired_lease_or_replaced_receipt_prevents_report_publication(self):
        for replaced in (False,True):
            with tempfile.TemporaryDirectory() as name,self.subTest(replaced=replaced):
                receipt=Path(name)/'session.json';receipt.write_bytes(b'{}');game=MetadataGame()
                def validate(*args):
                    if replaced:
                        receipt.write_bytes(b'{"changed":true}')
                        return dict(session='b'*32),game.instance
                    raise AssertionError('expired lease')
                with patch.object(control,'OnlineGameRead',return_value=game),patch.object(control,'capture',return_value={}),\
                        patch.object(control,'validate_receipt',side_effect=validate),self.assertRaises(AssertionError):
                    control.collect(receipt,'guest')
                self.assertEqual(list(receipt.parent.glob('*declarations*')),[])

    def test_reused_pid_cannot_publish_a_previous_process_contract(self):
        with tempfile.TemporaryDirectory() as name:
            receipt=Path(name)/'session.json';receipt.write_bytes(b'{}');game=MetadataGame()
            with patch.object(control,'OnlineGameRead',return_value=game),patch.object(control,'capture',return_value={}),\
                    patch.object(control,'validate_receipt',return_value=(dict(session='b'*32),game.instance)),\
                    patch('phantom_boss_pair_session.process_identity',return_value=dict(pid=42,created=2)),\
                    self.assertRaisesRegex(AssertionError,'process changed'):
                control.collect(receipt,'host')
            self.assertEqual(list(receipt.parent.glob('*declarations*')),[])

    def test_umg_collector_explicitly_includes_umg_namespace(self):
        with tempfile.TemporaryDirectory() as name:
            receipt=Path(name)/'session.json';receipt.write_bytes(b'{}');game=MetadataGame()
            game.addresses={path:0x10000+index*0x1000 for index,path in enumerate(sorted(workbench.FUNCTIONS))}
            game.owners={address:path for path,address in game.addresses.items()}
            with patch.object(workbench,'OnlineGameRead',return_value=game),patch.object(workbench,'fields',return_value=[]):
                result=workbench.collect(receipt,'host')
            self.assertIn('/Script/UMG.',game.find_calls[0][1])
            self.assertEqual(result['missing_functions'],[])
            self.assertEqual(len(result['functions']),len(workbench.FUNCTIONS))
            self.assertFalse(result['widget_created']);self.assertFalse(result['binding_verified'])


if __name__=='__main__':unittest.main()
