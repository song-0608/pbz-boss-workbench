"""用途：研究箱限时会话的只读进程接口；调用方只解析明确的 UE 对象结构。"""
import ctypes
from ctypes import wintypes as w
import json
import struct
import time
import official_validation as v
from capture_runtime_observation import Module


class GameRead:
    def __init__(self):
        self.state=json.loads(v.state_path().read_text(encoding='utf-8'))
        if self.state.get('restored') or not self.state.get('offline_validation') or self.state.get('network_active'):
            raise RuntimeError('Strict offline research session required')
        c=v.c;c.isolation.select_box('PBZSteamLab');dll=c.isolation.api()
        c.isolation.check_policy(dll,allow_offline_validation=True)
        if c.host_steam_pids(dll):raise RuntimeError('Preserve host Steam')
        v.verify_build(self.state.get('ue4ss_loader_manifest'))
        query=dll.SbieApi_QueryProcess
        query.argtypes=[w.HANDLE,w.LPWSTR,w.LPWSTR,w.LPWSTR,ctypes.POINTER(w.ULONG)];query.restype=w.LONG
        k=ctypes.WinDLL('kernel32',use_last_error=True);self.k=k
        k.CreateToolhelp32Snapshot.argtypes=[w.DWORD,w.DWORD];k.CreateToolhelp32Snapshot.restype=w.HANDLE
        for name in ('Module32FirstW','Module32NextW'):
            f=getattr(k,name);f.argtypes=[w.HANDLE,ctypes.POINTER(Module)];f.restype=w.BOOL
        k.CloseHandle.argtypes=[w.HANDLE]
        choices=[]
        for p in c.preflight.games_running():
            pid=p['ProcessId'];box=ctypes.create_unicode_buffer(64);im=ctypes.create_unicode_buffer(96);sid=ctypes.create_unicode_buffer(96);session=w.ULONG()
            if query(pid,box,im,sid,ctypes.byref(session))!=0 or box.value!='PBZSteamLab':continue
            snap=k.CreateToolhelp32Snapshot(0x18,pid)
            if snap==ctypes.c_void_p(-1).value:continue
            m=Module();m.size=ctypes.sizeof(m);more=k.Module32FirstW(snap,ctypes.byref(m))
            while more:
                if m.name.casefold()=='pbz.exe' and m.bytes>300_000_000:
                    choices.append((pid,m.base,m.bytes));break
                more=k.Module32NextW(snap,ctypes.byref(m))
            k.CloseHandle(snap)
        if len(choices)!=1:raise RuntimeError('Need exactly one verified research game body')
        self.pid,self.base,self.size=choices[0]
        k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];k.OpenProcess.restype=w.HANDLE
        k.ReadProcessMemory.argtypes=[w.HANDLE,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)];k.ReadProcessMemory.restype=w.BOOL
        self.handle=k.OpenProcess(0x1010,False,self.pid)
        if not self.handle:raise ctypes.WinError(ctypes.get_last_error())
        self.name_cache={};self.block_cache={};self.header_cache={}
        self.chunks=self.u64(self.base+0xde28c68);self.count=self.u32(self.base+0xde28c70)
        if not 100<=self.count<=8_388_608:self.close();raise RuntimeError('Object array not ready')

    def close(self):
        if self.handle:self.k.CloseHandle(self.handle);self.handle=None

    def __enter__(self):return self
    def __exit__(self,*unused):self.close()

    def read(self,address,length):
        # 用途：从不申请写权限、创建线程或执行游戏函数；读数量受限且到期即停止。
        if time.time()>=self.state['deadline_unix']:raise RuntimeError('Research lease expired')
        if not 0<length<=65536 or not 0x10000<=address<0x7fffffffffff:raise ValueError('Invalid bounded read')
        buf=ctypes.create_string_buffer(length);got=ctypes.c_size_t()
        if not self.k.ReadProcessMemory(self.handle,address,buf,length,ctypes.byref(got)) or got.value!=length:
            raise ctypes.WinError(ctypes.get_last_error())
        return buf.raw

    def u64(self,address):return struct.unpack('<Q',self.read(address,8))[0]
    def u32(self,address):return struct.unpack('<I',self.read(address,4))[0]

    def object(self,index):
        if not 0<=index<self.count:raise ValueError('Object index outside array')
        chunk=self.u64(self.chunks+(index>>16)*8)
        return self.u64(chunk+(index&0xffff)*24+8)

    def name(self,comparison,number=0):
        # 用途：依据本机 ToString→EntryLookup 反汇编解析 FName 元数据，不扫描任意进程字符串。
        if comparison not in self.name_cache:
            block_index=comparison>>16
            if block_index>8191:raise ValueError('Invalid FName block')
            if block_index not in self.block_cache:self.block_cache[block_index]=self.u64(self.base+0xdd86ac0+0x10+block_index*8)
            entry=self.block_cache[block_index]+(comparison&0xffff)*2
            header=struct.unpack('<H',self.read(entry,2))[0];length=header>>6;wide=header&1
            if not 0<length<=1023:raise ValueError('Invalid FName entry length')
            self.name_cache[comparison]=self.read(entry+2,length*(2 if wide else 1)).decode('utf-16le' if wide else 'utf-8')
        value=self.name_cache[comparison]
        return value+('_'+str(number-1) if number else '')

    def header(self,address):
        if address not in self.header_cache:
            data=self.read(address,40);index=struct.unpack_from('<i',data,12)[0]
            if self.object(index)!=address:raise ValueError('Pointer is not an indexed UObject')
            comp,num=struct.unpack_from('<II',data,24)
            self.header_cache[address]={'index':index,'class':struct.unpack_from('<Q',data,16)[0],
                'outer':struct.unpack_from('<Q',data,32)[0],'flags':struct.unpack_from('<I',data,8)[0],
                'name':self.name(comp,num),'address':hex(address)}
        return self.header_cache[address]

    def path(self,address,depth=0):
        if not address:return ''
        if depth>=8:raise ValueError('Outer chain too deep')
        h=self.header(address)
        return (self.path(h['outer'],depth+1)+'.' if h['outer'] else '')+h['name']

    def find_native(self,names,prefixes=None):
        # 用途：只输出指定名称的引擎元对象；迭代范围限定原生注册区，防止生成无关对象转储。
        result=[];limit=min(self.u32(self.base+0xde28c50)+1024,self.count,75000)
        for index in range(limit):
            try:
                obj=self.object(index)
                if not obj:continue
                raw=self.read(obj,40);comparison,number=struct.unpack_from('<II',raw,24)
                name=self.name(comparison,number)
                if name in names:
                    full=self.path(obj)
                    allowed=prefixes or('/Script/Engine.','/Script/CoreUObject.','/Script/AIModule.','/Script/ProjectPBZ.','/Script/SGameAI.')
                    if full.startswith(allowed):
                        result.append({'path':full,**self.header(obj)})
            except (OSError,ValueError,UnicodeError):continue
        return result
