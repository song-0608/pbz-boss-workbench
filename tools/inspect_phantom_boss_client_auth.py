"""Diagnose this lease's official Steam readiness without opening credential stores.

Read only bounded connection-log status lines and Valve's existing BLoggedOn
query. Do not log in, launch games, retry clients or change network policy.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import time
import uuid

from build_phantom_boss_candidate import ROOT,canonical,sha
from check_phantom_boss_isolation import BOXES,virtual
from prepare_phantom_boss_clients import LOGICAL
from phantom_boss_pair_session import load_run,bootstrap

MAX_BYTES=131072
TIMESTAMP=re.compile(r'^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]')


def status_events(text,issued_at,now):
    """Return known status facts only; never return raw log lines or identifiers."""
    if type(issued_at)is not int or type(now)not in (int,float) or not 0<issued_at<=now:
        raise ValueError('bounded current lease required')
    result=dict(session_replaced_events=0,last_session_replaced_at=None,last_official_logon_ok_at=None,
        failed_logon_responses=0,unparsed_replacement_timestamps=0)
    for line in text.splitlines():
        replaced="RecvMsgClientLoggedOff('Session Replaced')"in line
        response='RecvMsgClientLogOnResponse()'in line and 'processing complete'not in line
        if not replaced and not response:continue
        match=TIMESTAMP.match(line)
        if not match:
            if replaced:result['unparsed_replacement_timestamps']+=1
            continue
        try:at=int(datetime.strptime(match[1],'%Y-%m-%d %H:%M:%S').timestamp())
        except ValueError:
            if replaced:result['unparsed_replacement_timestamps']+=1
            continue
        if not issued_at<=at<=now:continue
        if replaced:
            result['session_replaced_events']+=1;result['last_session_replaced_at']=at
        elif "'OK'"in line:result['last_official_logon_ok_at']=at
        else:result['failed_logon_responses']+=1
    return result


def read_status(path,issued_at,now):
    path=Path(path)
    if not path.is_file():return dict(log_present=False,**status_events('',issued_at,now))
    with path.open('rb')as stream:
        stream.seek(0,2);size=stream.tell();offset=max(0,size-MAX_BYTES);stream.seek(offset)
        raw=stream.read(MAX_BYTES)
    if offset:raw=raw.partition(b'\n')[2] # discard the leading partial line
    return dict(log_present=True,**status_events(raw.decode('utf-8',errors='replace'),issued_at,now))


def verdict(roles):
    if set(roles)!=set(BOXES):raise ValueError('both independent roles required')
    if all(r.get('official_existing_user')is True and r.get('official_logged_on')is True for r in roles.values()):
        return 'both-clients-officially-logged-on-at-observation'
    if any(r['session_replaced_events'] for r in roles.values()):return 'official-login-session-conflict'
    return 'official-login-not-ready'


def exit_code(status):
    return {'both-clients-officially-logged-on-at-observation':0,
        'official-login-not-ready':2,'official-login-session-conflict':3}[status]


def inspect(receipt):
    path,session=load_run(receipt);original=path.read_bytes();now=time.time()
    assert session['status']in ('clients-running','clients-ready')
    assert type(session['issued_at'])is int and session['issued_at']<=now<session['expires_at']
    roles={}
    for role in BOXES:
        data=bootstrap(path,role,'inspect')
        roles[role]=dict(official_existing_user=data['official_existing_user'],official_logged_on=data['official_logged_on'],
            **read_status(virtual(role,LOGICAL)/'logs/connection_log.txt',session['issued_at'],time.time()))
    assert path.read_bytes()==original and time.time()<session['expires_at'],'session changed during login inspection'
    report=dict(schema=1,status=verdict(roles),session=session['session'],at=int(time.time()),roles=roles,
        session_sha256=sha(original),game_started_by_tool=False,login_automated=False,
        account_identifiers_published=False,credential_stores_opened=False,raw_log_lines_published=False,
        bounded_log_tail_only=True,maximum_log_bytes=MAX_BYTES,
        runtime_acceptance_current=False,
        source_sha256={name:sha((ROOT/name).read_bytes()) for name in (
            'tools/inspect_phantom_boss_client_auth.py','tools/phantom_boss_pair_session.py')})
    target=path.parent/('client-auth-'+uuid.uuid4().hex+'.json')
    with target.open('xb')as stream:stream.write(canonical(report)+b'\n')
    print(json.dumps(dict(report=str(target),status=report['status'],roles=roles,game_started_by_tool=False),ensure_ascii=True))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('receipt',type=Path)
    raise SystemExit(exit_code(inspect(parser.parse_args().receipt)['status']))
