"""Bounded reuse of the observed single-player startup configuration and Saved sentinel.

The pair session owns the lease/watchdog. This module never launches a game or
Steam, changes networking, opens host writes or restores an existing save.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import uuid

from build_phantom_boss_candidate import ROOT, canonical, safe_file, sha
from check_phantom_boss_isolation import BOXES, GAME, SBIE, change, settings, virtual


def policy(enabled,prior=None):
    if not enabled and prior is not None:
        assert set(prior)==set(BOXES)
        for role in BOXES:
            assert set(prior[role])=={'UnstrippedToken','ClosedFilePath'}
            assert prior[role]['UnstrippedToken'] in ([],['n'])
            assert prior[role]['ClosedFilePath']==settings(role)['ClosedFilePath']
    for role,box in BOXES.items():
        # These exact keys are journaled before the pair watchdog starts. All
        # file/IPC breakout switches and DropAdminRights retain their baseline.
        if enabled:change('set',box,'UnstrippedToken','y')
        else:
            change('delete',box,'UnstrippedToken','y')
            if prior and prior[role]['UnstrippedToken']==['n']:change('set',box,'UnstrippedToken','n')
        rules=settings(role,compatible=enabled)['ClosedFilePath']
        change('set',box,'ClosedFilePath',rules[0])
        for rule in rules[1:]:change('append',box,'ClosedFilePath',rule)


def probe_exe():
    summary=json.loads((ROOT/'evidence/adaptation/phantom-pact-isolation.json').read_bytes())
    receipt=safe_file(ROOT,summary['receipt'])
    assert sha(receipt.read_bytes())==summary['receipt_sha256']
    original=json.loads(receipt.read_bytes())
    source='tools/phantom_boss_isolation_probe.cpp'
    assert original['source_sha256'][source]==sha((ROOT/source).read_bytes())
    exe=receipt.parent/'isolation_probe.exe'
    assert sha(exe.read_bytes())==original['probe_sha256']==summary['probe_sha256']
    return exe


def probe(directory,exe):
    directory=Path(directory)
    marker_name='BWBOnlineProbe_'+uuid.uuid4().hex+'.tmp'
    markers=[Path(os.environ['LOCALAPPDATA'])/'ProjectPBZ/Saved'/marker_name,GAME/'ProjectPBZ/Saved'/marker_name]
    assert not any(p.exists() for p in markers)
    tokens={role:secrets.token_hex(16) for role in BOXES}
    checks=[]
    try:
        for mode in ('write','read'):
            for role,box in BOXES.items():
                logical=directory/(role+'-compatible-'+mode+'.json')
                result=subprocess.run([str(SBIE/'Start.exe'),'/box:'+box,'/silent','/hide_window','/wait',
                    str(exe),box,mode,*map(str,markers),tokens[role],str(logical)],
                    capture_output=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
                report=virtual(role,logical)
                assert result.returncode==0 and report.is_file(),'Compatible Saved sentinel did not complete'
                data=json.loads(report.read_bytes())
                assert data==dict(sandbox_verified=True,local_saved=True,installed_saved=True)
                for marker in markers:
                    assert not marker.exists(),'Host sentinel leaked outside the research box'
                    assert virtual(role,marker).read_bytes()==tokens[role].encode(),'Role Saved paths overlap'
                checks.append(dict(role=role,mode=mode,passed=True,report_sha256=sha(report.read_bytes())))
        return dict(passed=True,checks=checks,game_started=False,steam_started=False,
            saves_read_or_restored=False,probe_sha256=sha(exe.read_bytes()))
    finally:
        for role in BOXES:
            for marker in markers:
                physical=virtual(role,marker)
                if physical.is_file() and physical.read_bytes()==tokens[role].encode():physical.unlink()
