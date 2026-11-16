"""Compare freshly captured declarations to a pinned, sanitized expected ABI.

Historical metadata supplies expected signatures only. A current report must be
bound again to its live role, original process, activation and unexpired session.
No game function is invoked and no installation or game launch happens here.
"""
import argparse
import json
from pathlib import Path
import re
import time

from build_phantom_boss_candidate import ROOT, canonical, sha, safe_file
import collect_phantom_boss_control_contract as control
import collect_phantom_boss_contract_bundle as bundle
from phantom_boss_online_readonly import OnlineGameRead, validate_receipt

SCHEMA='research/contracts/phantom-control-abi.json'
SCHEMA_SHA='d0d8d1980281fe6961ceffd312fe959509a226599ffed70b7b343df42f5a779f'
PARAMETER_FLAGS=0x8000582


def require(condition,message):
    if not condition:raise ValueError(message)


def load_schema():
    raw=safe_file(ROOT,SCHEMA).read_bytes()
    require(sha(raw)==SCHEMA_SHA,'expected control ABI changed; explicit review required')
    value=json.loads(raw)
    require(value['schema']==1 and value['status']=='expected-abi-only','unexpected control ABI schema')
    require({f['path'] for f in value['functions']}==control.FUNCTIONS,'incomplete expected functions')
    require({(p['owner'],p['name']) for p in value['properties']}=={
        (owner,name) for owner,names in control.PROPERTIES.items() for name in names},'incomplete expected properties')
    require(set(value['enum_values'])==control.ENUMS,'incomplete expected enums')
    return value


def rows_by(rows,keys,maximum,label):
    require(type(rows)is list and len(rows)<=maximum,'bounded '+label+' required')
    result={}
    for row in rows:
        require(type(row)is dict,'invalid '+label+' row')
        key=tuple(row[k] for k in keys)
        require(all(type(k)is str for k in key) and key not in result,'duplicate or invalid '+label)
        result[key]=row
    return result


def field_signature(row):
    require(type(row)is dict,'invalid reflected field')
    result={key:row[key] for key in ('name','type','array_dim','element_size','offset')}
    require(type(result['name'])is str and type(result['type'])is str,'invalid reflected field name/type')
    require(type(result['array_dim'])is int and result['array_dim']==1,'unexpected reflected array dimension')
    require(type(result['element_size'])is int and 0<result['element_size']<=65536,'invalid reflected element size')
    require(type(result['offset'])is str and re.fullmatch('0x[0-9a-f]+',result['offset'])is not None,'invalid field offset')
    flags=row['property_flags']
    require(type(flags)is str and re.fullmatch('0x[0-9a-f]+',flags)is not None,'invalid reflected field flags')
    result['parameter_flags']=int(flags,16)&PARAMETER_FLAGS
    return result


def validate_declarations(report,exe_sha256):
    expected=load_schema()
    require(exe_sha256==expected['exe_sha256'],'control ABI executable mismatch')
    require(report.get('schema')==1 and report.get('status')=='declarations-only','fresh declarations-only report required')
    for flag in ('binding_verified','game_functions_called','inventory_inspected','memory_written','runtime_acceptance_current'):
        require(report.get(flag)is False,'declaration report must not assert '+flag)
    functions=rows_by(report['functions'],('path',),128,'function declarations')
    properties=rows_by(report['properties'],('owner','name'),128,'property declarations')
    classes=rows_by(report['classes'],('path',),32,'class declarations')
    enums=rows_by(report['enums'],('path',),16,'enum declarations')
    for fn in expected['functions']:
        actual=functions.get((fn['path'],))
        require(actual is not None,'missing control function: '+fn['path'])
        require(type(actual['parameter_bytes'])is int and actual['parameter_bytes']==fn['parameter_bytes'],
            'control parameter size mismatch: '+fn['path'])
        require(type(actual['parameters'])is list and len(actual['parameters'])<=32,'bounded control parameters required')
        require(type(actual['parameter_count'])is int and actual['parameter_count']==len(fn['parameters']),
            'control parameter count mismatch: '+fn['path'])
        returned=[int(p['offset'],16) for p in fn['parameters'] if p['parameter_flags']&0x400]
        require(type(actual['return_offset'])is int and actual['return_offset']==(returned[0] if returned else 65535),
            'control return offset mismatch: '+fn['path'])
        require([field_signature(p) for p in actual['parameters']]==fn['parameters'],
            'control parameter ABI mismatch: '+fn['path'])
    for prop in expected['properties']:
        actual=properties.get((prop['owner'],prop['name']))
        require(actual is not None,'missing control property: '+prop['owner']+':'+prop['name'])
        require(field_signature(actual)=={k:v for k,v in prop.items() if k!='owner'},
            'control property ABI mismatch: '+prop['owner']+':'+prop['name'])
    for path in control.PROPERTIES:
        require((path,)in classes,'missing control class: '+path)
        size=classes[path,]['size']
        require(type(size)is int and 0<size<=1048576,'invalid control class size: '+path)
    for path,size in expected['struct_sizes'].items():
        require(classes[path,]['size']==size,'control struct size mismatch: '+path)
    for path,values in expected['enum_values'].items():
        require((path,)in enums,'missing control enum: '+path)
        entries=rows_by(enums[path,]['rows'],('name',),512,'control enum values')
        for row in entries.values():
            require(type(row['value'])is int and -(2**63)<=row['value']<2**63,'invalid control enum value')
        for name,value in values.items():
            require((name,)in entries and entries[name,]['value']==value,'control enum value mismatch: '+name)
    bindings={name:dict(binding_verified=True) for name in ('remote','barrier','protection','arena','visibility')}
    bindings['camera']=dict(binding_verified=True,keep_relative=0,keep_world=1,snap=2,camera_channel=4,
        spawn_collision=3,spawn_scale=0)
    bindings['combat']=dict(binding_verified=True,friendly=0,hostile=2,ai_focus_bridge=True)
    return dict(status='control-abi-matched-only',abi_verified=True,bindings=bindings,
        expected_abi_sha256=SCHEMA_SHA,functions=len(expected['functions']),properties=len(expected['properties']),
        enums=len(expected['enum_values']),runtime_acceptance_current=False,
        workbench_ui_verified=False,visual_pose_verified=False)


def validate_current(receipt,report_path,role):
    """Recheck immutable report identity and live container immediately before use."""
    receipt=Path(receipt).resolve();report_path=Path(report_path).resolve()
    require(report_path.parent==receipt.parent,'control declarations outside current session')
    match=re.fullmatch(re.escape(role)+r'-(control|native-bundle)-declarations-[0-9a-f]{32}\.json',report_path.name)
    require(match is not None,'unexpected current declaration report name')
    original=receipt.read_bytes();raw=report_path.read_bytes();report=json.loads(raw)
    sources=bundle.SOURCES if match[1]=='native-bundle' else control.SOURCES
    require(report.get('source_sha256')=={name:sha(safe_file(ROOT,name).read_bytes()) for name in sources},
        'current control collector source drift')
    with OnlineGameRead(receipt,role) as game:
        session,instance=validate_receipt(receipt,role,time.time())
        for key,value in dict(role=role,pid=game.pid,session=session['session'],activation=instance['activation'],
                game_identity=instance['game_identity'],session_sha256=sha(original)).items():
            require(report.get(key)==value,'current declaration identity mismatch: '+key)
        at=report.get('collected_at')
        require(type(at)is int and session['issued_at']<=at<=time.time()<session['expires_at'],
            'control declaration collection outside current lease')
        result=validate_declarations(report,session['exe_sha256'])
        from phantom_boss_pair_session import process_identity
        require(instance==game.instance and instance['game_identity']==process_identity(game.pid),'current role process changed')
        require(receipt.read_bytes()==original and report_path.read_bytes()==raw,'current declaration or session changed')
    result.update(role=role,pid=report['pid'],session=report['session'],activation=report['activation'],
        session_sha256=sha(original),declarations_sha256=sha(raw),game_identity=report['game_identity'])
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('receipt',type=Path);parser.add_argument('declarations',type=Path)
    parser.add_argument('--role',choices=('host','guest'),required=True)
    args=parser.parse_args();print(json.dumps(validate_current(args.receipt,args.declarations,args.role),indent=2))
