"""Role-bound, read-only native declarations for a live same-PC research session."""
import ctypes
from ctypes import wintypes as w
import json
from pathlib import Path
import re
import time

from build_phantom_boss_candidate import ROOT, verify_release
from capture_runtime_observation import Module
from check_phantom_boss_isolation import BOXES, GAME, api, pids, verify_policy
from pbz_readonly import GameRead
from stage_phantom_boss_pair import digest


def validate_receipt(path,role,now):
    path=Path(path).resolve()
    assert path.parent.parent==(ROOT/'runtime/online-runs').resolve() and path.name=='session.json'
    assert re.fullmatch('[0-9a-f]{32}',path.parent.name)
    value=json.loads(path.read_bytes())
    assert value['schema']==1 and value['mode']=='two-player-online-research'
    assert value['session']==path.parent.name
    assert value['status'] in ('active','partial-active') and role in BOXES
    assert type(value['issued_at']) is int and type(value['expires_at']) is int
    assert 0<value['issued_at']<=now<value['expires_at'] and value['expires_at']-value['issued_at']<=1200
    row=value['instances'][role]
    assert row['box']==BOXES[role] and type(row['game_pid']) is int and row['game_pid']>0
    return value,row


class OnlineGameRead(GameRead):
    def __init__(self,receipt,role,require_initialized=True):
        self.handle=None
        self.session,self.instance=validate_receipt(receipt,role,time.time())
        self.state={'deadline_unix':self.session['expires_at']}
        self.pid=self.instance['game_pid']
        from phantom_boss_pair_session import process_identity
        assert self.instance.get('game_identity')==process_identity(self.pid),'Original role game process changed'
        dll=api();verify_policy(dll,role,False,self.session.get('official_steam_online',False),
            self.session.get('official_game_auth',False),compatible=self.session.get('compatibility_requested',False))
        assert self.pid in pids(dll,BOXES[role]),'Requested game is outside its role container'
        query=dll.SbieApi_QueryProcess
        query.argtypes=[w.HANDLE,w.LPWSTR,w.LPWSTR,w.LPWSTR,ctypes.POINTER(w.ULONG)];query.restype=w.LONG
        box,image,sid=ctypes.create_unicode_buffer(64),ctypes.create_unicode_buffer(96),ctypes.create_unicode_buffer(96)
        session=w.ULONG()
        assert query(self.pid,box,image,sid,ctypes.byref(session))==0 and box.value==BOXES[role]
        k=ctypes.WinDLL('kernel32',use_last_error=True);self.k=k
        k.CreateToolhelp32Snapshot.argtypes=[w.DWORD,w.DWORD];k.CreateToolhelp32Snapshot.restype=w.HANDLE
        k.CloseHandle.argtypes=[w.HANDLE]
        for name in ('Module32FirstW','Module32NextW'):
            f=getattr(k,name);f.argtypes=[w.HANDLE,ctypes.POINTER(Module)];f.restype=w.BOOL
        snapshot=k.CreateToolhelp32Snapshot(0x18,self.pid)
        assert snapshot!=ctypes.c_void_p(-1).value,'Unable to inspect role game module'
        found=[]
        try:
            m=Module();m.size=ctypes.sizeof(m);more=k.Module32FirstW(snapshot,ctypes.byref(m))
            while more:
                if m.name.casefold()=='pbz.exe' and m.bytes>300_000_000:
                    found.append((m.base,m.bytes,Path(m.path)))
                more=k.Module32NextW(snapshot,ctypes.byref(m))
        finally:k.CloseHandle(snapshot)
        assert len(found)==1,'Exactly one real PBZ module required'
        self.base,self.size,executable=found[0]
        _,release=verify_release(ROOT)
        assert executable.resolve()==(GAME/'platform/steam/PBZ.exe').resolve(),'Unexpected role game image'
        assert digest(executable)==release['exe_sha256']==self.session['exe_sha256']
        k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];k.OpenProcess.restype=w.HANDLE
        k.ReadProcessMemory.argtypes=[w.HANDLE,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)]
        k.ReadProcessMemory.restype=w.BOOL
        # PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ only.
        self.handle=k.OpenProcess(0x1010,False,self.pid)
        if not self.handle:raise ctypes.WinError(ctypes.get_last_error())
        try:
            self.name_cache={};self.block_cache={};self.header_cache={}
            self.chunks=self.u64(self.base+0xde28c68);self.count=self.u32(self.base+0xde28c70)
            assert 0<=self.count<=8_388_608,'Invalid object array size'
            if require_initialized:assert self.count>=100,'Object array is not ready'
        except Exception:self.close();raise
