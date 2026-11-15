// 用途：仅在PBZSteamLab中启动独立Steam或通过其官方-applaunch入口启动PBZ。
// 所有注册表操作都在箱内虚拟化；绝不改主机Steam路径、不伪造登录信息或应用身份。
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <string>
#include <sstream>
#include <cstdio>
using Query=LONG(*)(HANDLE,WCHAR*,WCHAR*,WCHAR*,ULONG*);
// 用途：只声明Valve公开ISteamClient接口的前三个稳定方法，查询既有用户，绝不创建本地身份。
class SteamClientReadOnly {
public:
    virtual int CreateSteamPipe()=0;
    virtual bool BReleaseSteamPipe(int pipe)=0;
    virtual int ConnectToGlobalUser(int pipe)=0;
};

// 用途：用Windows调试事件记录客户端早退位置；只读事件，不改代码或认证状态。
// 不读取调试字符串，避免把登录资料写入诊断证据。
static std::string trace_startup(DWORD pid){
    std::ostringstream out;out<<"[";bool comma=false;DWORD start=GetTickCount();
    auto separator=[&](){if(comma)out<<",";comma=true;};
    while(GetTickCount()-start<8000){
        DEBUG_EVENT event{};if(!WaitForDebugEvent(&event,250))continue;
        DWORD continuation=DBG_CONTINUE;bool done=false;
        if(event.dwDebugEventCode==CREATE_PROCESS_DEBUG_EVENT){
            if(event.u.CreateProcessInfo.hFile)CloseHandle(event.u.CreateProcessInfo.hFile);
            if(event.u.CreateProcessInfo.hProcess)CloseHandle(event.u.CreateProcessInfo.hProcess);
            if(event.u.CreateProcessInfo.hThread)CloseHandle(event.u.CreateProcessInfo.hThread);
        }else if(event.dwDebugEventCode==CREATE_THREAD_DEBUG_EVENT){
            if(event.u.CreateThread.hThread)CloseHandle(event.u.CreateThread.hThread);
        }else if(event.dwDebugEventCode==LOAD_DLL_DEBUG_EVENT){
            WCHAR path[2048]{};DWORD size=event.u.LoadDll.hFile?GetFinalPathNameByHandleW(event.u.LoadDll.hFile,path,2048,FILE_NAME_NORMALIZED):0;
            std::wstring full=size&&size<2048?path:L"unknown";auto offset=full.find_last_of(L"\\/");
            std::wstring name=offset==std::wstring::npos?full:full.substr(offset+1);std::string ascii;
            for(wchar_t ch:name)ascii+=(ch>=32&&ch<127&&ch!='"'&&ch!='\\')?static_cast<char>(ch):'?';
            separator();out<<"{\"event\":\"module\",\"name\":\""<<ascii<<"\"}";
            if(event.u.LoadDll.hFile)CloseHandle(event.u.LoadDll.hFile);
        }else if(event.dwDebugEventCode==EXCEPTION_DEBUG_EVENT){
            auto code=event.u.Exception.ExceptionRecord.ExceptionCode;
            separator();out<<"{\"event\":\"exception\",\"code\":"<<code<<",\"first_chance\":"<<event.u.Exception.dwFirstChance<<"}";
            if(code!=EXCEPTION_BREAKPOINT && code!=0x4000001f)continuation=DBG_EXCEPTION_NOT_HANDLED;
        }else if(event.dwDebugEventCode==EXIT_PROCESS_DEBUG_EVENT){
            separator();out<<"{\"event\":\"exit\",\"code\":"<<event.u.ExitProcess.dwExitCode<<"}";done=true;
        }
        ContinueDebugEvent(event.dwProcessId,event.dwThreadId,continuation);
        if(done){out<<"]";return out.str();}
    }
    DebugSetProcessKillOnExit(FALSE);DebugActiveProcessStop(pid);out<<"]";return out.str();
}

static bool boxed(Query q,DWORD pid){
    WCHAR box[64]{},image[96]{},sid[96]{};ULONG session=0;
    return q && !q(reinterpret_cast<HANDLE>(static_cast<ULONG_PTR>(pid)),box,image,sid,&session)
        && _wcsicmp(box,L"PBZSteamLab")==0;
}

static LONG set_string(HKEY root,const wchar_t* path,const wchar_t* name,const wchar_t* value,REGSAM extra=0){
    HKEY key{};LONG result=RegCreateKeyExW(root,path,0,nullptr,0,KEY_SET_VALUE|extra,nullptr,&key,nullptr);
    if(result!=ERROR_SUCCESS)return result;
    result=RegSetValueExW(key,name,0,REG_SZ,reinterpret_cast<const BYTE*>(value),static_cast<DWORD>((wcslen(value)+1)*sizeof(wchar_t)));
    RegCloseKey(key);return result;
}

int wmain(int argc,wchar_t**argv){
    if(argc!=3 || (wcscmp(argv[1],L"client") && wcscmp(argv[1],L"client-visible") && wcscmp(argv[1],L"trace-client") && wcscmp(argv[1],L"game") && wcscmp(argv[1],L"direct-game") && wcscmp(argv[1],L"inspect")))return 64;
    HMODULE dll=GetModuleHandleW(L"SbieDll.dll");
    auto query=dll?reinterpret_cast<Query>(GetProcAddress(dll,"SbieApi_QueryProcess")):nullptr;
    if(!boxed(query,GetCurrentProcessId()))return 65;
    // 英文入口在主机上为空目录；真实客户端位于D盘研究容器的drive/E镜像，箱内才可见。
    bool direct_game=wcscmp(argv[1],L"direct-game")==0;
    const wchar_t* folder=direct_game?L"E:\\SteamLibrary\\steamapps\\common\\PBZ":L"E:\\PBZSteamLabClient";
    const wchar_t* exe=direct_game?L"E:\\SteamLibrary\\steamapps\\common\\PBZ\\steam\\PBZ.exe":L"E:\\PBZSteamLabClient\\steam.exe";
    bool visible=wcscmp(argv[1],L"client-visible")==0;
    bool tracing=wcscmp(argv[1],L"trace-client")==0;
    bool is_client=wcscmp(argv[1],L"client")==0 || visible || tracing,inspect=wcscmp(argv[1],L"inspect")==0;
    LONG setup=0;
    if(is_client){
        setup=set_string(HKEY_CURRENT_USER,L"Software\\Valve\\Steam",L"SteamPath",folder);
        if(!setup)setup=set_string(HKEY_CURRENT_USER,L"Software\\Valve\\Steam",L"SteamExe",exe);
        if(!setup)setup=set_string(HKEY_LOCAL_MACHINE,L"Software\\Valve\\Steam",L"InstallPath",folder,KEY_WOW64_32KEY);
        if(!setup)setup=set_string(HKEY_LOCAL_MACHINE,L"Software\\Valve\\Steam",L"InstallPath",folder,KEY_WOW64_64KEY);
        // 用途：删除箱内继承的主机活动PID，独立客户端随后自行建立自己的活动状态。
        if(!setup){
            HKEY key{};
            LONG opened=RegOpenKeyExW(HKEY_CURRENT_USER,L"Software\\Valve\\Steam\\ActiveProcess",0,KEY_SET_VALUE,&key);
            if(opened==ERROR_SUCCESS){
                RegDeleteValueW(key,L"pid");RegDeleteValueW(key,L"ActiveUser");RegCloseKey(key);
            }
        }
    }
    DWORD active_pid=0,active_user=0;HKEY active{};
    if(RegOpenKeyExW(HKEY_CURRENT_USER,L"Software\\Valve\\Steam\\ActiveProcess",0,KEY_QUERY_VALUE,&active)==ERROR_SUCCESS){
        DWORD bytes=sizeof(DWORD);RegQueryValueExW(active,L"pid",nullptr,nullptr,reinterpret_cast<BYTE*>(&active_pid),&bytes);
        bytes=sizeof(DWORD);RegQueryValueExW(active,L"ActiveUser",nullptr,nullptr,reinterpret_cast<BYTE*>(&active_user),&bytes);RegCloseKey(active);
    }
    bool steam_interface=false,steam_pipe=false,steam_global_user=false;
    DWORD steam_library_error=0;
    if(inspect && active_pid && boxed(query,active_pid)){
        // 用途：注册表ActiveUser在离线状态可能不足为据；改用官方客户端查询，输出只保留布尔值。
        HMODULE steam=LoadLibraryExW(L"E:\\PBZSteamLabClient\\steamclient64.dll",nullptr,LOAD_WITH_ALTERED_SEARCH_PATH);
        if(steam){
            using Factory=void*(*)(const char*,int*);
            auto factory=reinterpret_cast<Factory>(GetProcAddress(steam,"CreateInterface"));
            int status=0;
            auto api=factory?static_cast<SteamClientReadOnly*>(factory("SteamClient023",&status)):nullptr;
            steam_interface=api!=nullptr;
            if(api){
                int pipe=api->CreateSteamPipe();steam_pipe=pipe!=0;
                if(pipe){steam_global_user=api->ConnectToGlobalUser(pipe)!=0;api->BReleaseSteamPipe(pipe);}
            }
            FreeLibrary(steam);
        }else steam_library_error=GetLastError();
    }
    bool created=false,child_box=false,resumed=false;DWORD winerror=0,child_pid=0,exit_code=0;
    std::string events="[]";
    if(!inspect && !setup){
        // 离线能力由网络阻断和客户端真实结果验收，不仅依赖这个命令行选项。
        std::wstring command=L"\""+std::wstring(exe)+L"\"";
        command+=is_client?(visible?L"":L" -offline -silent"):(direct_game?L" -windowed -ResX=960 -ResY=540 -nosplash -nosound -log":L" -applaunch 4115450 -windowed -ResX=960 -ResY=540 -nosplash -log");
        STARTUPINFOW start{};start.cb=sizeof(start);start.dwFlags=STARTF_USESHOWWINDOW;start.wShowWindow=is_client&&!visible?SW_HIDE:SW_SHOW;
        PROCESS_INFORMATION process{};
        created=CreateProcessW(exe,command.data(),nullptr,nullptr,FALSE,CREATE_SUSPENDED|(tracing?DEBUG_ONLY_THIS_PROCESS:0),nullptr,folder,&start,&process)!=FALSE;
        if(created){
            child_pid=process.dwProcessId;child_box=boxed(query,child_pid);
            if(child_box)resumed=ResumeThread(process.hThread)!=static_cast<DWORD>(-1);
            if(!child_box || !resumed){winerror=GetLastError();TerminateProcess(process.hProcess,66);}
            if(resumed){if(tracing)events=trace_startup(child_pid);WaitForSingleObject(process.hProcess,1000);GetExitCodeProcess(process.hProcess,&exit_code);}
            CloseHandle(process.hThread);CloseHandle(process.hProcess);
        }else winerror=GetLastError();
    }
    std::ostringstream out;
    out<<"{\"bootstrap_box_verified\":true,\"registry_setup_error\":"<<setup
       <<",\"created\":"<<(created?"true":"false")<<",\"child_pid\":"<<child_pid
       <<",\"child_box_verified\":"<<(child_box?"true":"false")<<",\"resumed\":"<<(resumed?"true":"false")
       <<",\"win32_error\":"<<winerror<<",\"active_client_pid\":"<<active_pid
       <<",\"child_exit_after_one_second\":"<<exit_code
       <<",\"diagnostic_debugger_used\":"<<(tracing?"true":"false")<<",\"startup_events\":"<<events
       <<",\"active_client_in_same_box\":"<<(active_pid && boxed(query,active_pid)?"true":"false")
       <<",\"client_has_active_user\":"<<(active_user?"true":"false")<<"}";
    std::string payload=out.str();payload.pop_back();
    payload+=",\"official_steam_interface_available\":"+std::string(steam_interface?"true":"false")
        +",\"official_steam_pipe_created\":"+std::string(steam_pipe?"true":"false")
        +",\"official_existing_global_user_available\":"+std::string(steam_global_user?"true":"false")
        +",\"steam_library_load_error\":"+std::to_string(steam_library_error)+"}";
    HANDLE file=CreateFileW(argv[2],GENERIC_WRITE,FILE_SHARE_READ,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(file==INVALID_HANDLE_VALUE)return 67;
    std::string json=payload;DWORD written=0;bool saved=WriteFile(file,json.data(),static_cast<DWORD>(json.size()),&written,nullptr)!=FALSE;CloseHandle(file);
    return saved && !setup && (inspect || (created && child_box && resumed)) ? 0 : 68;
}
