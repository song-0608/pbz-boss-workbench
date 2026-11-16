// Same-PC research entry. All registry writes occur only after the actual
// Sandboxie role is verified. The game starts solely via Steam -applaunch.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <string>
#include <map>
#include <fstream>
#include <filesystem>
#include <sstream>
#include <ctime>
#include <cmath>
#include <algorithm>

using Query=LONG(*)(HANDLE,WCHAR*,WCHAR*,WCHAR*,ULONG*);
class SteamClientReadOnly {
public:
    virtual int CreateSteamPipe()=0;
    virtual bool BReleaseSteamPipe(int)=0;
    virtual int ConnectToGlobalUser(int)=0;
};
static bool boxed(Query query,DWORD pid,const wchar_t* expected) {
    WCHAR box[64]{},image[96]{},sid[96]{};ULONG session=0;
    return query && !query(reinterpret_cast<HANDLE>(static_cast<ULONG_PTR>(pid)),box,image,sid,&session)
        && _wcsicmp(box,expected)==0;
}
static bool lease_ok(const wchar_t* path,const std::string& role) {
    std::ifstream input{std::filesystem::path(path)};
    std::map<std::string,std::string> fields;std::string line;
    while(std::getline(input,line)) {
        if(!line.empty() && line.back()=='\r')line.pop_back();
        const auto at=line.find('=');
        if(at==std::string::npos || !fields.emplace(line.substr(0,at),line.substr(at+1)).second)return false;
    }
    if(!input.eof() || fields.size()!=5 || fields["mode"]!="two-player-online-research" || fields["role"]!=role)return false;
    const auto& session=fields["session"];
    if(session.size()!=32 || !std::all_of(session.begin(),session.end(),[](char c){return (c>='0'&&c<='9')||(c>='a'&&c<='f');}))return false;
    try {
        size_t a=0,b=0;const double issued=std::stod(fields["issued_at"],&a),expires=std::stod(fields["expires_at"],&b);
        const double now=static_cast<double>(std::time(nullptr));
        return a==fields["issued_at"].size() && b==fields["expires_at"].size()
            && std::isfinite(issued) && std::isfinite(expires) && issued>0 && issued<=now
            && expires>now && expires>issued && expires-issued<=1200;
    }catch(...){return false;}
}
static LONG set_string(HKEY root,const wchar_t* name,const wchar_t* value,REGSAM view=0) {
    HKEY key{};LONG result=RegCreateKeyExW(root,L"Software\\Valve\\Steam",0,nullptr,0,KEY_SET_VALUE|view,nullptr,&key,nullptr);
    if(result)return result;
    result=RegSetValueExW(key,name,0,REG_SZ,reinterpret_cast<const BYTE*>(value),static_cast<DWORD>((wcslen(value)+1)*sizeof(wchar_t)));
    RegCloseKey(key);return result;
}
static DWORD active_client() {
    HKEY key{};DWORD pid=0,size=sizeof(pid),type=0;
    if(RegOpenKeyExW(HKEY_CURRENT_USER,L"Software\\Valve\\Steam\\ActiveProcess",0,KEY_QUERY_VALUE,&key)==ERROR_SUCCESS) {
        if(RegQueryValueExW(key,L"pid",nullptr,&type,reinterpret_cast<BYTE*>(&pid),&size)!=ERROR_SUCCESS || type!=REG_DWORD)pid=0;
        RegCloseKey(key);
    }
    return pid;
}
static bool official_user() {
    // Query an existing global user through Valve's public interface. No local
    // user creation, app-id override, authentication patch or license emulation.
    HMODULE module=LoadLibraryExW(L"E:\\PBZSteamLabClient\\steamclient64.dll",nullptr,LOAD_WITH_ALTERED_SEARCH_PATH);
    if(!module)return false;
    using Factory=void*(*)(const char*,int*);
    const auto factory=reinterpret_cast<Factory>(GetProcAddress(module,"CreateInterface"));int status=0;bool found=false;
    auto api=factory?static_cast<SteamClientReadOnly*>(factory("SteamClient023",&status)):nullptr;
    if(api){const int pipe=api->CreateSteamPipe();if(pipe){found=api->ConnectToGlobalUser(pipe)!=0;api->BReleaseSteamPipe(pipe);}}
    FreeLibrary(module);return found;
}
int wmain(int argc,wchar_t**argv) {
    if(argc!=5)return 64;
    const std::wstring action=argv[1],role=argv[2];
    if((role!=L"host" && role!=L"guest") || (action!=L"leasecheck" && action!=L"probe" && action!=L"client" && action!=L"inspect" && action!=L"game"))return 64;
    // Pure parser regression entry: no registry/client/game operation or output.
    if(action==L"leasecheck")return lease_ok(argv[3],role==L"host"?"host":"guest")?0:66;
    const wchar_t* box=role==L"host"?L"PBZOnlineHost":L"PBZOnlineGuest";
    HMODULE module=GetModuleHandleW(L"SbieDll.dll");
    const auto query=module?reinterpret_cast<Query>(GetProcAddress(module,"SbieApi_QueryProcess")):nullptr;
    if(!boxed(query,GetCurrentProcessId(),box))return 65;
    if(!lease_ok(argv[3],role==L"host"?"host":"guest"))return 66;
    bool created=false,child_box=false,resumed=false,authorized=false;DWORD child_pid=0,error=0;LONG setup=0;
    const auto current=active_client();
    const bool same_client=current && boxed(query,current,box);
    if((action==L"inspect" || action==L"game") && same_client)authorized=official_user();
    if(action==L"game" && !authorized)return 67;
    if(action==L"client") {
        if(same_client)return 68; // never replace an active independent Steam
        setup=set_string(HKEY_CURRENT_USER,L"SteamPath",L"E:\\PBZSteamLabClient");
        if(!setup)setup=set_string(HKEY_CURRENT_USER,L"SteamExe",L"E:\\PBZSteamLabClient\\steam.exe");
        if(!setup)setup=set_string(HKEY_LOCAL_MACHINE,L"InstallPath",L"E:\\PBZSteamLabClient",KEY_WOW64_32KEY);
        if(!setup)setup=set_string(HKEY_LOCAL_MACHINE,L"InstallPath",L"E:\\PBZSteamLabClient",KEY_WOW64_64KEY);
        if(!setup) {
            HKEY key{};
            if(RegOpenKeyExW(HKEY_CURRENT_USER,L"Software\\Valve\\Steam\\ActiveProcess",0,KEY_SET_VALUE,&key)==ERROR_SUCCESS) {
                RegDeleteValueW(key,L"pid");RegDeleteValueW(key,L"ActiveUser");RegCloseKey(key);
            }
        }
    }
    if(!setup && (action==L"client" || action==L"game")) {
        const wchar_t* exe=L"E:\\PBZSteamLabClient\\steam.exe";
        std::wstring command=L"\""+std::wstring(exe)+L"\"";
        command+=action==L"client"?L" -offline -silent":L" -applaunch 4115450 -windowed -ResX=960 -ResY=540 -nosplash -log";
        STARTUPINFOW start{};start.cb=sizeof(start);start.dwFlags=STARTF_USESHOWWINDOW;start.wShowWindow=action==L"client"?SW_HIDE:SW_SHOW;
        PROCESS_INFORMATION process{};
        created=CreateProcessW(exe,command.data(),nullptr,nullptr,FALSE,CREATE_SUSPENDED,nullptr,L"E:\\PBZSteamLabClient",&start,&process)!=FALSE;
        if(created) {
            child_pid=process.dwProcessId;child_box=boxed(query,child_pid,box);
            if(child_box)resumed=ResumeThread(process.hThread)!=static_cast<DWORD>(-1);
            if(!child_box || !resumed){error=GetLastError();TerminateProcess(process.hProcess,69);}
            CloseHandle(process.hThread);CloseHandle(process.hProcess);
        }else error=GetLastError();
    }
    std::ostringstream json;
    json<<"{\"box_verified\":true,\"lease_verified\":true,\"role\":\""<<(role==L"host"?"host":"guest")
        <<"\",\"probe_only\":"<<(action==L"probe"?"true":"false")
        <<",\"active_client_in_same_box\":"<<(same_client?"true":"false")
        <<",\"official_existing_user\":"<<(authorized?"true":"false")
        <<",\"registry_error\":"<<setup<<",\"created\":"<<(created?"true":"false")
        <<",\"child_pid\":"<<child_pid<<",\"child_box_verified\":"<<(child_box?"true":"false")
        <<",\"resumed\":"<<(resumed?"true":"false")<<",\"win32_error\":"<<error<<"}";
    HANDLE file=CreateFileW(argv[4],GENERIC_WRITE,FILE_SHARE_READ,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(file==INVALID_HANDLE_VALUE)return 70;
    const auto payload=json.str();DWORD written=0;
    const bool saved=WriteFile(file,payload.data(),static_cast<DWORD>(payload.size()),&written,nullptr) && written==payload.size();
    CloseHandle(file);
    return saved && !setup && (action==L"probe" || action==L"inspect" || (created && child_box && resumed))?0:71;
}
