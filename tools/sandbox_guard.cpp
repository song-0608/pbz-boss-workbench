// 用途：仅在已验证的PBZBossLab中启动一次限时、无渲染的原版PBZ基线。
// 不加载UE4SS、不操作键盘、不连接Steam、不修改游戏文件；子进程退出或超时后记录证据。
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdio>
#include <string>
#include <sstream>
using QueryProcess = LONG (*)(HANDLE, WCHAR*, WCHAR*, WCHAR*, ULONG*);

static bool in_box(QueryProcess query, DWORD pid) {
    wchar_t box[64]{}, image[96]{}, sid[96]{}; ULONG session=0;
    return query && query(reinterpret_cast<HANDLE>(static_cast<ULONG_PTR>(pid)),
                          box,image,sid,&session)==0 && _wcsicmp(box,L"PBZBossLab")==0;
}

int wmain(int argc, wchar_t** argv) {
    // 用途：限定目标和参数数目，禁止把入口当作任意程序启动器。
    if(argc!=4) return 70;
    const wchar_t* runtime=L"E:\\SteamLibrary\\steamapps\\common\\PBZ\\platform\\steam\\PBZ.exe";
    const wchar_t* launcher=L"E:\\SteamLibrary\\steamapps\\common\\PBZ\\steam\\PBZ.exe";
    if(_wcsicmp(argv[1],runtime)!=0 && _wcsicmp(argv[1],launcher)!=0) return 71;
    const wchar_t* exe=argv[1];
    HMODULE dll=GetModuleHandleW(L"SbieDll.dll");
    auto query=dll ? reinterpret_cast<QueryProcess>(GetProcAddress(dll,"SbieApi_QueryProcess")) : nullptr;
    if(!in_box(query,GetCurrentProcessId())) return 72;
    HANDLE report=CreateFileW(argv[2],GENERIC_WRITE,FILE_SHARE_READ,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(report==INVALID_HANDLE_VALUE) return 73;
    // 用途：所有额外参数都是UE常规诊断参数，不关闭验证、不跳过授权或改写Steam身份。
    std::wstring command=L"\""+std::wstring(exe)+L"\" -nullrhi -unattended -nosound -nosplash -windowed -ResX=640 -ResY=360 -log -abslog=\""+argv[3]+L"\"";
    HANDLE job=CreateJobObjectW(nullptr,nullptr);
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limit{};limit.BasicLimitInformation.LimitFlags=JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    bool job_ok=job && SetInformationJobObject(job,JobObjectExtendedLimitInformation,&limit,sizeof(limit));
    STARTUPINFOW start{};start.cb=sizeof(start);start.dwFlags=STARTF_USESHOWWINDOW;start.wShowWindow=SW_HIDE;
    PROCESS_INFORMATION process{};DWORD error=0,exit_code=0;bool created=false,child_box=false,resumed=false,timed_out=false,kill_requested=false,kill_accepted=false;
    if(job_ok){
        created=CreateProcessW(exe,command.data(),nullptr,nullptr,FALSE,CREATE_SUSPENDED|CREATE_NO_WINDOW,
                              nullptr,L"E:\\SteamLibrary\\steamapps\\common\\PBZ",&start,&process)!=FALSE;
        if(created){
            child_box=in_box(query,process.dwProcessId);
            if(!child_box || !AssignProcessToJobObject(job,process.hProcess)){
                error=GetLastError();TerminateProcess(process.hProcess,74);
            }else{
                resumed=ResumeThread(process.hThread)!=static_cast<DWORD>(-1);
                if(!resumed){error=GetLastError();TerminateJobObject(job,75);}
                else if(WaitForSingleObject(process.hProcess,45000)==WAIT_TIMEOUT){
                    timed_out=true;kill_requested=true;kill_accepted=TerminateJobObject(job,76)!=FALSE;
                }
            }
            WaitForSingleObject(process.hProcess,5000);GetExitCodeProcess(process.hProcess,&exit_code);
            CloseHandle(process.hThread);CloseHandle(process.hProcess);
        }else error=GetLastError();
    }else error=GetLastError();
    if(job)CloseHandle(job); // 关闭只包含本次子进程的作业，不触碰其他游戏进程。
    std::ostringstream out;
    out << "{\"guard_pid\":" << GetCurrentProcessId() << ",\"guard_box_verified\":true,\"game_pid\":" << process.dwProcessId
        << ",\"created\":" << (created?"true":"false") << ",\"child_box_verified\":" << (child_box?"true":"false")
        << ",\"resumed\":" << (resumed?"true":"false") << ",\"timed_out\":" << (timed_out?"true":"false")
        << ",\"job_kill_requested\":" << (kill_requested?"true":"false") << ",\"job_kill_accepted\":" << (kill_accepted?"true":"false")
        << ",\"game_exit_code\":" << exit_code << ",\"win32_error\":" << error << ",\"loader_deployed\":false}";
    auto json=out.str();DWORD written=0;WriteFile(report,json.data(),static_cast<DWORD>(json.size()),&written,nullptr);CloseHandle(report);
    return created && child_box && resumed && !timed_out && exit_code==0 ? 0 : 77;
}
