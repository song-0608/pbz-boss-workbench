"""用途：仅在已隔离、断网、限时研究会话中只读验证 GUObjectArray 候选；不写进程内存。"""
import ctypes
from ctypes import wintypes as w
import json
from pathlib import Path
import struct
import sys
import time
import official_validation as v
from capture_runtime_observation import Module


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    state=json.loads(v.state_path().read_text(encoding='utf-8'))
    if state.get('restored') or time.time()>=state['deadline_unix'] or not state.get('offline_validation') or state.get('network_active'):
        raise RuntimeError('Active strictly offline research lease required')
    c=v.c;c.isolation.select_box('PBZSteamLab');dll=c.isolation.api()
    c.isolation.check_policy(dll,allow_offline_validation=True)
    if c.host_steam_pids(dll):raise RuntimeError('Host Steam present; preserve existing session')
    query=dll.SbieApi_QueryProcess
    query.argtypes=[w.HANDLE,w.LPWSTR,w.LPWSTR,w.LPWSTR,ctypes.POINTER(w.ULONG)];query.restype=w.LONG
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes=[w.DWORD,w.DWORD];kernel.CreateToolhelp32Snapshot.restype=w.HANDLE
    for name in ('Module32FirstW','Module32NextW'):
        f=getattr(kernel,name);f.argtypes=[w.HANDLE,ctypes.POINTER(Module)];f.restype=w.BOOL
    kernel.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];kernel.OpenProcess.restype=w.HANDLE
    kernel.ReadProcessMemory.argtypes=[w.HANDLE,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)];kernel.ReadProcessMemory.restype=w.BOOL
    kernel.CloseHandle.argtypes=[w.HANDLE]
    rows=[]
    for p in c.preflight.games_running():
        pid=p['ProcessId'];box=ctypes.create_unicode_buffer(64);image=ctypes.create_unicode_buffer(96);sid=ctypes.create_unicode_buffer(96);session=w.ULONG()
        if query(pid,box,image,sid,ctypes.byref(session))!=0 or box.value!='PBZSteamLab':continue
        snap=kernel.CreateToolhelp32Snapshot(0x18,pid)
        if snap==ctypes.c_void_p(-1).value:continue
        module=Module();module.size=ctypes.sizeof(module);more=kernel.Module32FirstW(snap,ctypes.byref(module));base=None
        while more:
            if module.name.casefold()=='pbz.exe' and module.bytes>300_000_000:base=module.base;break
            more=kernel.Module32NextW(snap,ctypes.byref(module))
        kernel.CloseHandle(snap)
        if base is None:continue
        # 用途：权限仅限查询/读取，不申请 VM_WRITE、VM_OPERATION 或创建远程线程。
        process=kernel.OpenProcess(0x1000|0x10,False,pid)
        if not process:raise ctypes.WinError(ctypes.get_last_error())
        def read(address,length):
            if not 0<length<=256:raise ValueError('Only bounded structural reads allowed')
            data=ctypes.create_string_buffer(length);got=ctypes.c_size_t()
            if not kernel.ReadProcessMemory(process,address,data,length,ctypes.byref(got)) or got.value!=length:
                raise ctypes.WinError(ctypes.get_last_error())
            return data.raw
        try:
            block=read(base+0xde28c50,0xc0)
            row={'pid':pid,'verified_box':box.value,'image_base':hex(base),'global_rva':'0xde28c50',
                 'struct_dwords':{hex(i):struct.unpack_from('<I',block,i)[0] for i in range(0,len(block),4)},'samples':[]}
            # 用途：地址、索引、对象头之间交叉核对；只看代码已证明的分块、24字节条目及 Object+8。
            chunks=struct.unpack_from('<Q',block,0x18)[0];num=struct.unpack_from('<i',block,0x20)[0]
            if not 100<=num<=8_388_608:
                row.update({'passed':False,'reason':'Candidate count not ready or layout differs'})
                rows.append(row)
                continue
            for index in (0,1,2,31,64,127,1024,65536):
                if index>=num:continue
                try:
                    chunk=struct.unpack('<Q',read(chunks+(index>>16)*8,8))[0]
                    item=read(chunk+(index&0xffff)*24,24);obj=struct.unpack_from('<Q',item,8)[0]
                    if not obj:continue
                    header=read(obj,40);internal=struct.unpack_from('<i',header,12)[0]
                    vtable=struct.unpack_from('<Q',header,0)[0];cls=struct.unpack_from('<Q',header,16)[0]
                    row['samples'].append({'index':index,'object':hex(obj),'internal_index':internal,'index_matches':internal==index,
                       'vtable_in_main_image':base<=vtable<base+module.bytes,'class':hex(cls),
                       'class_self_index':struct.unpack_from('<i',read(cls,40),12)[0],
                       'name_comparison_id':struct.unpack_from('<I',header,24)[0]})
                except OSError as error:row['samples'].append({'index':index,'read_error':error.winerror})
            row['passed']=len(row['samples'])>=6 and all(s.get('index_matches') and s.get('vtable_in_main_image') for s in row['samples'])
            rows.append(row)
        finally:kernel.CloseHandle(process)
    report={'at':v.utc8(),'scope':'bounded read-only object structure; no string/memory dumps; no gameplay',
            'passed':len(rows)==1 and rows[0]['passed'],'results':rows}
    work=Path(state['work']);v.save(work/'object-array-probe.json',report)
    v.save(v.ROOT/'evidence/adaptation/latest-object-array-probe.json',report)
    print(json.dumps({'passed':report['passed'],'processes':len(rows),'samples':[len(r['samples']) for r in rows],
                     'report':str(work/'object-array-probe.json')},ensure_ascii=False))


if __name__=='__main__':main()
