import copy
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import phantom_boss_control_abi as abi
import collect_phantom_boss_control_contract as control
from build_phantom_boss_candidate import canonical,sha


def valid_report():
    expected=abi.load_schema()
    def field(row):
        return {**{k:v for k,v in row.items() if k!='parameter_flags'},
            'property_flags':hex(row['parameter_flags']),'descriptor':'0x1234'}
    return dict(schema=1,status='declarations-only',functions=[dict(path=f['path'],
        parameter_bytes=f['parameter_bytes'],parameter_count=len(f['parameters']),
        return_offset=next((int(p['offset'],16) for p in f['parameters'] if p['parameter_flags']&0x400),65535),
        parameters=[field(p) for p in f['parameters']])
        for f in expected['functions']],properties=[field(p) for p in expected['properties']],
        classes=[dict(path=path,size=expected['struct_sizes'].get(path,128)) for path in control.PROPERTIES],
        enums=[dict(path=path,rows=[dict(name=name,value=value) for name,value in values.items()])
            for path,values in expected['enum_values'].items()],binding_verified=False,
        game_functions_called=False,inventory_inspected=False,memory_written=False,runtime_acceptance_current=False)


class LiveReader:
    def __init__(self,instance):self.instance=instance;self.pid=instance['game_pid']
    def __enter__(self):return self
    def __exit__(self,*args):pass


class ControlAbiTests(unittest.TestCase):
    def setUp(self):self.report=valid_report();self.exe=abi.load_schema()['exe_sha256']
    def validate(self):return abi.validate_declarations(self.report,self.exe)

    def test_complete_signatures_allow_only_control_bindings_and_preserve_runtime_pending(self):
        result=self.validate()
        self.assertTrue(result['abi_verified'])
        self.assertEqual(set(result['bindings']),{'camera','combat','remote','barrier','protection','arena','visibility'})
        for name in ('runtime_acceptance_current','workbench_ui_verified','visual_pose_verified'):self.assertFalse(result[name])
        self.assertEqual((result['functions'],result['properties'],result['enums']),(57,29,5))

    def test_wrong_executable_cannot_reuse_expected_signatures(self):
        with self.assertRaisesRegex(ValueError,'executable'):abi.validate_declarations(self.report,'0'*64)

    def test_each_missing_function_rejects_even_when_all_other_declarations_match(self):
        original=copy.deepcopy(self.report['functions'])
        for index,row in enumerate(original):
            with self.subTest(function=row['path']):
                self.report['functions']=original[:index]+original[index+1:]
                with self.assertRaisesRegex(ValueError,'missing control function'):self.validate()

    def test_same_parameter_size_with_wrong_order_type_offset_or_flags_is_rejected(self):
        original=copy.deepcopy(self.report)
        for key,value in [('name','Wrong'),('type','StrProperty'),('offset','0xff'),('array_dim',2),
                ('element_size',7),('property_flags','0x0')]:
            with self.subTest(key=key):
                self.report=copy.deepcopy(original);self.report['functions'][0]['parameters'][0][key]=value
                with self.assertRaises(ValueError):self.validate()

    def test_parameter_return_and_out_semantics_cannot_be_dropped(self):
        fn=next(f for f in self.report['functions'] if f['path'].endswith('.K2_ProjectPointToNavigation'))
        p=next(p for p in fn['parameters'] if p['name']=='ProjectedLocation')
        p['property_flags']=hex(int(p['property_flags'],16)&~0x100)
        with self.assertRaisesRegex(ValueError,'ABI mismatch'):self.validate()

    def test_metadata_parameter_count_and_return_offset_are_independently_checked(self):
        for key,value in [('parameter_count',99),('return_offset',123),('parameter_bytes',False)]:
            with self.subTest(key=key):
                self.report=valid_report();self.report['functions'][0][key]=value
                with self.assertRaises(ValueError):self.validate()

    def test_each_control_property_is_checked_for_exact_layout(self):
        original=copy.deepcopy(self.report)
        for index,p in enumerate(original['properties']):
            with self.subTest(owner=p['owner'],name=p['name']):
                self.report=copy.deepcopy(original);self.report['properties'][index]['offset']='0xffff'
                with self.assertRaisesRegex(ValueError,'property ABI mismatch'):self.validate()

    def test_control_struct_size_and_presence_are_required(self):
        for remove in (False,True):
            with self.subTest(remove=remove):
                self.report=valid_report()
                row=next(r for r in self.report['classes'] if r['path']=='/Script/GameplayTags.GameplayTag')
                if remove:self.report['classes'].remove(row)
                else:row['size']=16
                with self.assertRaises(ValueError):self.validate()

    def test_all_pinned_enum_values_must_be_captured_and_match(self):
        original=copy.deepcopy(self.report)
        for index,enum in enumerate(original['enums']):
            with self.subTest(enum=enum['path']):
                self.report=copy.deepcopy(original);self.report['enums'][index]['rows'][0]['value']=999
                with self.assertRaisesRegex(ValueError,'enum value mismatch'):self.validate()

    def test_duplicate_function_property_class_or_enum_is_rejected(self):
        for key in ('functions','properties','classes','enums'):
            with self.subTest(key=key):
                self.report=valid_report();self.report[key].append(copy.deepcopy(self.report[key][0]))
                with self.assertRaisesRegex(ValueError,'duplicate'):self.validate()

    def test_duplicate_enum_name_and_boolean_numeric_values_are_rejected(self):
        enum=self.report['enums'][0];enum['rows'].append(copy.deepcopy(enum['rows'][0]))
        with self.assertRaisesRegex(ValueError,'duplicate'):self.validate()
        self.report=valid_report();self.report['enums'][0]['rows'][0]['value']=True
        with self.assertRaisesRegex(ValueError,'invalid control enum value'):self.validate()

    def test_oversized_rows_and_claimed_runtime_success_cannot_pass(self):
        self.report['functions']*=3
        with self.assertRaisesRegex(ValueError,'bounded'):self.validate()
        for flag in ('binding_verified','game_functions_called','inventory_inspected','memory_written','runtime_acceptance_current'):
            self.report=valid_report();self.report[flag]=True
            with self.subTest(flag=flag),self.assertRaisesRegex(ValueError,'must not assert'):self.validate()

    def test_process_addresses_do_not_enter_expected_or_comparison_schema(self):
        for f in self.report['functions']:
            for p in f['parameters']:p['descriptor']='0xdeadbeef'
        self.assertTrue(self.validate()['abi_verified'])
        self.assertNotIn('descriptor',json.dumps(abi.load_schema()))

    def test_pinned_expected_schema_cannot_be_silently_replaced(self):
        with patch.object(abi,'SCHEMA_SHA','0'*64),self.assertRaisesRegex(ValueError,'explicit review'):self.validate()

    def live(self,directory,role='host'):
        root=Path(directory);receipt=root/'session.json';receipt.write_bytes(b'{}');now=int(time.time())
        instance=dict(game_pid=42,activation='a'*32,game_identity=dict(pid=42,created=3))
        session=dict(session='b'*32,issued_at=now-10,expires_at=now+600,exe_sha256=self.exe)
        self.report.update(role=role,pid=42,session=session['session'],activation=instance['activation'],
            game_identity=instance['game_identity'],session_sha256=sha(receipt.read_bytes()),collected_at=now,
            source_sha256={name:sha((abi.ROOT/name).read_bytes()) for name in control.SOURCES})
        path=root/(role+'-control-declarations-'+'c'*32+'.json');path.write_bytes(canonical(self.report))
        return receipt,path,session,instance

    def test_current_role_and_original_process_are_rechecked_without_writing_files(self):
        with tempfile.TemporaryDirectory() as name:
            receipt,path,session,instance=self.live(name)
            with patch.object(abi,'OnlineGameRead',return_value=LiveReader(instance)),\
                    patch.object(abi,'validate_receipt',return_value=(session,instance)),\
                    patch('phantom_boss_pair_session.process_identity',return_value=instance['game_identity']):
                result=abi.validate_current(receipt,path,'host')
            self.assertTrue(result['abi_verified']);self.assertEqual(result['activation'],'a'*32)
            self.assertEqual(len(list(Path(name).iterdir())),2)

    def test_cross_role_or_previous_activation_report_is_rejected(self):
        for key,value in [('role','guest'),('activation','d'*32),('session','d'*32),('pid',99),('session_sha256','0'*64)]:
            with tempfile.TemporaryDirectory() as name,self.subTest(key=key):
                self.report=valid_report();receipt,path,session,instance=self.live(name)
                report=json.loads(path.read_bytes());report[key]=value;path.write_bytes(canonical(report))
                with patch.object(abi,'OnlineGameRead',return_value=LiveReader(instance)),\
                        patch.object(abi,'validate_receipt',return_value=(session,instance)),\
                        self.assertRaisesRegex(ValueError,'identity mismatch'):
                    abi.validate_current(receipt,path,'host')

    def test_source_drift_and_report_outside_current_session_are_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            receipt,path,session,instance=self.live(name)
            self.report['source_sha256'][control.SOURCES[0]]='0'*64;path.write_bytes(canonical(self.report))
            with self.assertRaisesRegex(ValueError,'source drift'):abi.validate_current(receipt,path,'host')
            with self.assertRaisesRegex(ValueError,'outside current session'):abi.validate_current(receipt,path.parent.parent/path.name,'host')

    def test_process_replacement_or_expiry_during_validation_is_rejected(self):
        for expired in (False,True):
            with tempfile.TemporaryDirectory() as name,self.subTest(expired=expired):
                self.report=valid_report();receipt,path,session,instance=self.live(name)
                if expired:session['expires_at']=int(time.time())-1
                with patch.object(abi,'OnlineGameRead',return_value=LiveReader(instance)),\
                        patch.object(abi,'validate_receipt',return_value=(session,instance)),\
                        patch('phantom_boss_pair_session.process_identity',return_value=dict(pid=42,created=4)),\
                        self.assertRaises(ValueError):abi.validate_current(receipt,path,'host')


if __name__=='__main__':unittest.main()
