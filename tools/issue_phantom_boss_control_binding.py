"""Atomically activate verified control declarations in one existing research role.

This never starts a process, sends input, changes network rules or writes a save.
The current game process and its unexpired session must already match a fresh
declaration report. UI and remote animation bindings still need separate proof.
"""
import argparse
import json
import os
from pathlib import Path
import re
import time
import uuid

from build_phantom_boss_candidate import ROOT, SOURCES, sha, verify_candidate
from check_phantom_boss_isolation import GAME,virtual
import phantom_boss_control_abi as abi
from phantom_boss_online_readonly import validate_receipt

# Expected Pawn class in the accepted four-Boss release's World/ownership proof.
# Startup independently reads back the actual local controller, Pawn and World.
PLAYER_CLASS='/Game/RenewalContent/Actors/Players/BP_Renewal_Hun.BP_Renewal_Hun_C'


def process_token(identity):
    abi.require(type(identity)is dict,'original process identity required')
    for key in ('pid','created'):
        abi.require(type(identity[key])is int and identity[key]>0,'positive original process '+key+' required')
    return str(identity['pid'])+':'+str(identity['created'])


def lua_value(value):
    """Encode data only; fixed-width decimal byte escapes avoid Lua/JSON drift."""
    if type(value)is bool:return 'true' if value else 'false'
    if type(value)is int:return str(value)
    if type(value)is str:
        return '"'+''.join(chr(b) if 32<=b<=126 and b not in (34,92) else '\\'+format(b,'03d')
            for b in value.encode('utf-8'))+'"'
    if type(value)is dict:
        abi.require(all(type(k)is str for k in value),'string binding keys required')
        return '{'+','.join('['+lua_value(k)+']='+lua_value(v) for k,v in sorted(value.items()))+'}'
    raise ValueError('unsupported binding data type')


def launch_data(session,role,checked):
    instance=session['instances'][role]
    abi.require(checked['abi_verified']is True and checked['runtime_acceptance_current']is False,
        'current control ABI verification required')
    for key,value in dict(session=session['session'],role=role,pid=instance['game_pid'],
            activation=instance['activation'],game_identity=instance['game_identity']).items():
        abi.require(checked[key]==value,'binding belongs to another '+key)
    abi.require(set(checked['bindings'])=={'camera','combat','remote','barrier','protection','arena','visibility'},
        'unproven optional binding cannot be included')
    return dict(activation=instance['activation'],session=session['session'],role=role,
        issued_at=session['issued_at'],expires_at=session['expires_at'],boss_id=session['bosses'][role],
        native_player_class=PLAYER_CLASS,process_identity=process_token(instance['game_identity']),
        exe_sha256=session['exe_sha256'],catalog_sha256=session['catalog_sha256'],
        upstream_commit=session['upstream_commit'],assembly=dict(bindings=checked['bindings']))


def owned_files(receipt,session,role,*,resolver=None):
    """Resolve cleanup responsibility without depending on a still-live process."""
    receipt=Path(receipt)
    target=(resolver or virtual)(role,GAME/'platform/steam/ue4ss/Mods/PBZCoop/Scripts/bwb_current_bindings.lua')
    journal=receipt.parent/(role+'-control-binding.json')
    if not journal.exists():
        abi.require(not target.exists(),'preserve unrecognized current binding file')
        return []
    record=json.loads(journal.read_bytes())
    for key,value in dict(schema=1,kind='owned-control-binding',session=session['session'],role=role,
            activation=session['instances'][role]['activation'],target=str(target)).items():
        abi.require(record.get(key)==value,'unrecognized binding journal '+key)
    abi.require(record['status']in ('prepared','published'),'unrecognized binding publication state')
    abi.require(re.fullmatch('[0-9a-f]{64}',record['payload_sha256'])is not None,'invalid binding ownership digest')
    pending=Path(record['pending'])
    abi.require(pending.parent==target.parent and re.fullmatch(r'bwb_current_bindings\.[0-9a-f]{32}\.pending',pending.name)is not None,
        'binding pending path escaped its role')
    for file in (target,pending):
        if file.exists():abi.require(sha(file.read_bytes())==record['payload_sha256'],'preserve changed owned binding payload')
    return [target,pending]


def publish(receipt,session,role,checked,payload):
    """Journal first; expose only a complete file using Windows exclusive rename."""
    from phantom_boss_pair_session import atomic,process_identity
    receipt=Path(receipt).resolve();original=receipt.read_bytes()
    abi.require(sha(original)==checked['session_sha256'],'binding session changed before publication')
    target=virtual(role,GAME/'platform/steam/ue4ss/Mods/PBZCoop/Scripts/bwb_current_bindings.lua')
    journal=receipt.parent/(role+'-control-binding.json')
    abi.require(not target.exists() and not journal.exists(),'current binding or publication journal already exists')
    abi.require(target.parent.is_dir(),'role payload has not been installed')
    pending=target.with_name('bwb_current_bindings.'+uuid.uuid4().hex+'.pending')
    record=dict(schema=1,kind='owned-control-binding',status='prepared',session=session['session'],role=role,
        activation=session['instances'][role]['activation'],target=str(target),pending=str(pending),
        payload_sha256=sha(payload),declarations_sha256=checked['declarations_sha256'],
        expected_abi_sha256=checked['expected_abi_sha256'],session_sha256=checked['session_sha256'],
        game_identity=checked['game_identity'],at=int(time.time()),runtime_acceptance_current=False)
    atomic(journal,record)
    with pending.open('xb') as stream:
        stream.write(payload);stream.flush();os.fsync(stream.fileno())
    latest,instance=validate_receipt(receipt,role,time.time())
    abi.require(latest==session and receipt.read_bytes()==original,'binding session changed during publication')
    abi.require(instance['game_identity']==checked['game_identity']==process_identity(instance['game_pid']),
        'original role process changed during publication')
    abi.require(os.name=='nt','exclusive Windows binding publication required')
    pending.rename(target) # Windows fails if target exists; never replace a binding.
    record['status']='published';atomic(journal,record)
    return record


def issue(receipt,declarations,role):
    from phantom_boss_pair_session import load_run,SOURCE_NAMES
    receipt,session=load_run(receipt)
    abi.require(session['source_sha256']=={name:sha((ROOT/name).read_bytes()) for name in SOURCE_NAMES},
        'online launcher source drift since this session was prepared')
    candidate=verify_candidate(ROOT/'runtime/online-candidates'/session['candidate'])
    abi.require(candidate['candidate_id']==session['candidate'],'binding candidate identity mismatch')
    abi.require(candidate['own_sources']=={name:sha((ROOT/name).read_bytes()) for name in SOURCES},'binding candidate source drift')
    from stage_phantom_boss_pair import verify as verify_stage
    stage=ROOT/session['stage'];staged=verify_stage(stage)
    abi.require(staged['candidate']==session['candidate'] and sha((stage/'stage.json').read_bytes())==session['stage_manifest_sha256'],
        'binding stage identity mismatch')
    for suffix in ('dlls/main.dll','Scripts/bwb_launch_gate.lua'):
        relative='platform/steam/ue4ss/Mods/PBZCoop/'+suffix
        abi.require(sha(virtual(role,GAME/relative).read_bytes())==staged['files'][role+'/game/'+relative],
            'role process identity provider or gate payload drift')
    checked=abi.validate_current(receipt,declarations,role)
    data=launch_data(session,role,checked)
    record=publish(receipt,session,role,checked,('return '+lua_value(data)+'\n').encode('ascii'))
    print(json.dumps(dict(role=role,status=record['status'],control_abi_verified=True,
        game_started=False,input_sent=False,runtime_acceptance_current=False,
        workbench_ui_verified=False,visual_pose_verified=False),ensure_ascii=False))
    return record


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('receipt',type=Path);parser.add_argument('declarations',type=Path)
    parser.add_argument('--role',choices=('host','guest'),required=True)
    args=parser.parse_args();issue(args.receipt,args.declarations,args.role)
