// Same-PC-only research relay. Reuses the pinned upstream wire/mailbox/Lua
// bridge; never starts Steam, pad routing, cursor clicks or display helpers.
#include "relay.hpp"
#include "lua_link.hpp"

// Keep FILETIME as decimal text: its 64 bits cannot round-trip through a Lua
// double. The launch gate compares this original process identity before it
// loads any native gameplay assembly, including after a process/PID restart.
std::string bwb_process_identity_text() {
    FILETIME created{},exited{},kernel{},user{};
    if (!GetProcessTimes(GetCurrentProcess(),&created,&exited,&kernel,&user))
        throw std::runtime_error("research process identity unavailable");
    const auto ticks=(static_cast<unsigned long long>(created.dwHighDateTime)<<32)|created.dwLowDateTime;
    return std::to_string(GetCurrentProcessId())+":"+std::to_string(ticks);
}

extern "C" __declspec(dllexport) int bwb_process_identity(void* lua) {
    const auto* api=lua_link::api();
    if (!api) return 0;
    try {return lua_link::push_text(api,lua_link::State{lua},bwb_process_identity_text());}
    catch (...) {return 0;}
}

namespace {
HMODULE module_handle=nullptr;
LONG started=0;
std::wstring directory;

bool hex_token(const std::string& value,size_t size) {
    return value.size()==size && std::all_of(value.begin(),value.end(),[](unsigned char c){
        return (c>='0' && c<='9') || (c>='a' && c<='f');
    });
}

double timestamp(const std::string& text) {
    size_t consumed=0;
    const double value=std::stod(text,&consumed);
    if (consumed!=text.size() || !std::isfinite(value) || value<=0)
        throw std::runtime_error("invalid research lease timestamp");
    return value;
}

relay::Options validate_request(const std::wstring& request) {
    const auto start=relay::read_ini(request);
    DeleteFileW(request.c_str());
    const auto lease=relay::read_ini(directory+L"\\bwb_native_lease.ini");
    const auto ini=relay::read_ini(directory+L"\\PhantomPact.ini");
    auto field=[](const auto& values,const char* key)->std::string {
        auto it=values.find(key);return it==values.end()?std::string():it->second;
    };
    const auto role=field(start,"role");
    const auto expected_role=role=="host"?"host":"guest";
    const double now=static_cast<double>(std::time(nullptr));
    const double issued=timestamp(field(lease,"issued_at"));
    const double expires=timestamp(field(lease,"expires_at"));
    const auto port_text=field(start,"port");
    if (!std::isfinite(issued) || !std::isfinite(expires) || issued>now || expires<=now
        || expires-issued>1200 || expires<=issued || field(lease,"mode")!="two-player-online-research"
        || field(lease,"role")!=expected_role || !hex_token(field(lease,"session"),32)
        || (role!="host" && role!="client") || field(start,"transport")!="udp"
        || field(start,"version")!="1.7.3" || relay::lower(field(ini,"thispconly"))!="on"
        || relay::lower(field(ini,"allowanyaddress"))!="off" || field(ini,"partysize")!="2"
        || relay::lower(field(ini,"role"))!=expected_role || !hex_token(field(ini,"secret"),64)
        || port_text.empty() || !std::all_of(port_text.begin(),port_text.end(),[](unsigned char c){return c>='0' && c<='9';})
        || (role=="client" && (field(start,"peer")!="127.0.0.1" || field(ini,"hostaddress")!="127.0.0.1")))
        throw std::runtime_error("same-PC research relay scope/settings rejected");
    const int port=std::stoi(port_text);
    if (port<1024 || port>65535 || field(ini,"port")!=port_text)
        throw std::runtime_error("same-PC research relay port mismatch");
    relay::Options options;
    options.role=role;options.peer=role=="client"?"127.0.0.1":"";
    options.transport="udp";options.this_pc_only=true;options.allow_any=false;
    options.port=port;options.dir=directory;options.ini=directory+L"\\PhantomPact.ini";
    options.version="1.7.3";options.seconds=expires-now;
    options.bwb_research=true;options.bwb_secret=field(ini,"secret");
    options.bwb_expires=expires;
    return options;
}

void run_relay(const relay::Options& options) {
    relay::mail.stop=false;
    const auto log_path=directory+L"\\relay_log.txt";
    relay::write_atomic(log_path,"");
    relay::run(options,[&](const std::string& line){relay::append_lines(log_path,{line});});
    relay::mail.reset();relay::mail.set_party(0,0);
    relay::mail.set_status("role="+options.role+" connected=no stopped=yes");
    SetThreadPriority(GetCurrentThread(),THREAD_PRIORITY_NORMAL);
}

void start_relay(const std::wstring& request) {
    run_relay(validate_request(request));
}

DWORD WINAPI watch(void*) {
    const auto request=directory+L"\\net_start.txt";
    while (true) {
        if (GetFileAttributesW(request.c_str())!=INVALID_FILE_ATTRIBUTES) {
            try {start_relay(request);}
            catch (const std::exception& error) {
                relay::write_atomic(directory+L"\\relay_error.txt",std::string(error.what())+"\n");
                relay::mail.set_status("connected=no stopped=yes error=research relay rejected");
            }
        }
        Sleep(250);
    }
}
}

std::unique_ptr<relay::Link> relay::make_steam_link(const std::string&,const std::string&) {
    throw std::runtime_error("this research relay supports loopback UDP only");
}
extern "C" __declspec(dllexport) void* start_mod() {
    if (InterlockedExchange(&started,1)==0) {
        wchar_t path[4096];const DWORD count=GetModuleFileNameW(module_handle,path,4096);
        if (!count || count>=4096) return nullptr;
        std::wstring file(path,count);const auto dlls=file.substr(0,file.find_last_of(L'\\'));
        directory=dlls.substr(0,dlls.find_last_of(L'\\'));
        const HANDLE thread=CreateThread(nullptr,0,watch,nullptr,0,nullptr);
        if (thread) CloseHandle(thread);
    }
    return nullptr;
}
extern "C" __declspec(dllexport) void uninstall_mod(void*) {}
BOOL WINAPI DllMain(HINSTANCE instance,DWORD reason,LPVOID) {
    if (reason==DLL_PROCESS_ATTACH) {module_handle=instance;DisableThreadLibraryCalls(instance);}
    return TRUE;
}
