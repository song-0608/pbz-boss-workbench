// 用途：验证本进程确实位于指定沙盒，再测试虚拟文件、注册表与网络隔离。
// 只接受外部创建的测试哨兵路径；绝不操作游戏存档，不启动游戏。
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <cstdio>
#include <string>
#include <sstream>
#include <iomanip>
#include <vector>

using QueryProcess = LONG (*)(HANDLE, WCHAR*, WCHAR*, WCHAR*, ULONG*);

static std::string utf8(const wchar_t* text) {
    int len=WideCharToMultiByte(CP_UTF8, 0, text, -1, nullptr, 0, nullptr, nullptr);
    std::string result(len, 0);
    WideCharToMultiByte(CP_UTF8, 0, text, -1, result.data(), len, nullptr, nullptr);
    if (!result.empty()) result.pop_back(); return result;
}

static bool replace_test_file(const wchar_t* path, DWORD& failure) {
    // 用途：打开已存在的测试文件；若错误地在主机运行，前面的沙盒身份检查会阻止执行。
    HANDLE h = CreateFileW(path, GENERIC_WRITE | GENERIC_READ, 0, nullptr,
                           OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (h == INVALID_HANDLE_VALUE) { failure = GetLastError(); return false; }
    const char marker[] = "SANDBOX_CHANGED_ONLY";
    DWORD written = 0;
    bool ok = WriteFile(h, marker, sizeof(marker)-1, &written, nullptr) && written == sizeof(marker)-1;
    ok = ok && SetEndOfFile(h);
    SetFilePointer(h, 0, nullptr, FILE_BEGIN);
    char readback[64]{}; DWORD count = 0;
    ok = ok && ReadFile(h, readback, sizeof(readback)-1, &count, nullptr)
            && std::string(readback, count) == marker;
    failure = ok ? 0 : GetLastError(); CloseHandle(h); return ok;
}

static int tcp_attempt(int family, const char* ip, unsigned short port) {
    // 用途：返回实际Winsock错误；只有明确的访问被拒绝才能证明阻断，超时不算通过。
    SOCKET s = socket(family, SOCK_STREAM, IPPROTO_TCP);
    if (s == INVALID_SOCKET) return WSAGetLastError();
    u_long nonblock = 1; ioctlsocket(s, FIONBIO, &nonblock);
    sockaddr_storage storage{}; int size;
    if (family == AF_INET) {
        auto* a = reinterpret_cast<sockaddr_in*>(&storage);
        a->sin_family = AF_INET; a->sin_port = htons(port); inet_pton(AF_INET, ip, &a->sin_addr);
        size = sizeof(*a);
    } else {
        auto* a = reinterpret_cast<sockaddr_in6*>(&storage);
        a->sin6_family = AF_INET6; a->sin6_port = htons(port); inet_pton(AF_INET6, ip, &a->sin6_addr);
        size = sizeof(*a);
    }
    int code = 0;
    if (connect(s, reinterpret_cast<sockaddr*>(&storage), size) == SOCKET_ERROR) {
        code = WSAGetLastError();
        if (code == WSAEWOULDBLOCK) {
            fd_set writefds, errors; FD_ZERO(&writefds); FD_ZERO(&errors);
            FD_SET(s, &writefds); FD_SET(s, &errors); timeval timeout{1,0};
            int selected = select(0, nullptr, &writefds, &errors, &timeout);
            if (selected <= 0) code = selected == 0 ? WSAETIMEDOUT : WSAGetLastError();
            else {int len = sizeof(code); getsockopt(s, SOL_SOCKET, SO_ERROR, reinterpret_cast<char*>(&code), &len);}
        }
    }
    closesocket(s); return code;
}

int wmain(int argc, wchar_t** argv) {
    if(argc==2 && wcscmp(argv[1],L"--hold-in-box")==0){
        // 用途：留出三秒供主机验证PID枚举/箱级清理，只在指定箱中等待，无文件读写。
        HMODULE mod=GetModuleHandleW(L"SbieDll.dll");
        auto q=mod?reinterpret_cast<QueryProcess>(GetProcAddress(mod,"SbieApi_QueryProcess")):nullptr;
        WCHAR b[64]{},im[96]{},sid[96]{};ULONG n=0;
        if(!q || q(reinterpret_cast<HANDLE>(static_cast<ULONG_PTR>(GetCurrentProcessId())),b,im,sid,&n)
           || _wcsicmp(b,L"PBZBossLab")!=0)return 65;
        Sleep(3000);return 0;
    }
    if(argc==3 && wcscmp(argv[1],L"--observe")==0){
        // 用途：主机只读核实测试文件真的存在，排除Python/AppData路径虚拟化造成的假测试。
        HANDLE h=CreateFileW(argv[2],GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,
                             nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
        if(h==INVALID_HANDLE_VALUE){printf("{\"readable\":false,\"error\":%lu}",GetLastError());return 68;}
        char data[128]{};DWORD bytes=0;bool ok=ReadFile(h,data,127,&bytes,nullptr);CloseHandle(h);
        printf("{\"readable\":%s,\"bytes\":%lu}",ok?"true":"false",bytes);return ok?0:68;
    }
    bool local_tcp=argc==13 && wcscmp(argv[12],L"--local-tcp")==0;
    if (argc != 12 && !local_tcp) return 64;
    // 用途：必须由Sandboxie注入其官方DLL，且驱动API确认箱名，才允许产生任何写入。
    HMODULE dll = GetModuleHandleW(L"SbieDll.dll");
    auto query = dll ? reinterpret_cast<QueryProcess>(GetProcAddress(dll, "SbieApi_QueryProcess")) : nullptr;
    WCHAR box[64]{}, image[96]{}, sid[96]{}; ULONG session = 0;
    LONG status = query ? query(reinterpret_cast<HANDLE>(static_cast<ULONG_PTR>(GetCurrentProcessId())),
                                box, image, sid, &session) : -1;
    if (status != 0 || _wcsicmp(box, argv[1]) != 0) {
        fwprintf(stderr, L"REFUSED: sandbox identity failed (status=%ld, box=%ls)\n", status, box);
        return 65;
    }
    DWORD error_d=0, error_e=0, error_c=0;
    bool file_d = replace_test_file(argv[3], error_d);
    bool file_e = replace_test_file(argv[4], error_e);
    bool file_c = replace_test_file(argv[5], error_c);
    HKEY key{}; const wchar_t regvalue[] = L"SANDBOX_ONLY";
    bool registry = RegCreateKeyExW(HKEY_CURRENT_USER, L"Software\\PBZBossLabProbe", 0, nullptr,
                                   0, KEY_READ | KEY_WRITE, nullptr, &key, nullptr) == ERROR_SUCCESS;
    if (registry) {
        registry = RegSetValueExW(key, argv[10], 0, REG_SZ,
                   reinterpret_cast<const BYTE*>(regvalue), sizeof(regvalue)) == ERROR_SUCCESS;
        wchar_t readback[64]{}; DWORD bytes = sizeof(readback);
        registry = registry && RegQueryValueExW(key, argv[10], nullptr, nullptr,
                    reinterpret_cast<BYTE*>(readback), &bytes) == ERROR_SUCCESS && wcscmp(readback, regvalue) == 0;
        RegCloseKey(key);
    }
    WSADATA data{}; int started = WSAStartup(MAKEWORD(2,2), &data);
    int tcp4 = -1, tcp6 = -1, external = -1, udp = -1;
    if (!started) {
        tcp4 = tcp_attempt(AF_INET, "127.0.0.1", static_cast<unsigned short>(_wtoi(argv[6])));
        tcp6 = tcp_attempt(AF_INET6, "::1", static_cast<unsigned short>(_wtoi(argv[7])));
        external = tcp_attempt(AF_INET, "1.1.1.1", 443);
        SOCKET s = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
        if (s == INVALID_SOCKET) udp = WSAGetLastError();
        else {
            sockaddr_in target{}; target.sin_family = AF_INET;
            target.sin_port = htons(static_cast<unsigned short>(_wtoi(argv[8])));
            inet_pton(AF_INET, "127.0.0.1", &target.sin_addr);
            udp = sendto(s, "probe", 5, 0, reinterpret_cast<sockaddr*>(&target), sizeof(target)) == SOCKET_ERROR ? WSAGetLastError() : 0;
            closesocket(s);
        }
        WSACleanup();
    }
    // 用途：连接专门创建的Steam样式哨兵管道，绝不连接真实Steam客户端。
    HANDLE pipe = CreateFileW(argv[9], GENERIC_READ | GENERIC_WRITE, 0, nullptr, OPEN_EXISTING, 0, nullptr);
    DWORD pipe_error = pipe == INVALID_HANDLE_VALUE ? GetLastError() : 0;
    if (pipe != INVALID_HANDLE_VALUE) CloseHandle(pipe);
    bool internal_pipe_ok=false;
    if(_wcsicmp(argv[1],L"PBZSteamLab")==0){
        // 用途：主机同名管道必须不可见，但箱内同名服务与客户端必须能通信。
        HANDLE server=CreateNamedPipeW(argv[9],PIPE_ACCESS_DUPLEX|FILE_FLAG_OVERLAPPED,
                                      PIPE_TYPE_BYTE|PIPE_READMODE_BYTE,1,4096,4096,0,nullptr);
        if(server!=INVALID_HANDLE_VALUE){
            HANDLE client=CreateFileW(argv[9],GENERIC_READ|GENERIC_WRITE,0,nullptr,OPEN_EXISTING,0,nullptr);
            if(client!=INVALID_HANDLE_VALUE){
                const char pipe_data[]="inside-only";DWORD written=0,read=0;char received[32]{};
                bool wrote=WriteFile(client,pipe_data,sizeof(pipe_data),&written,nullptr)!=FALSE;
                OVERLAPPED overlapped{};overlapped.hEvent=CreateEventW(nullptr,TRUE,FALSE,nullptr);
                bool read_ok=ReadFile(server,received,sizeof(pipe_data),&read,&overlapped)!=FALSE;
                if(!read_ok && GetLastError()==ERROR_IO_PENDING && WaitForSingleObject(overlapped.hEvent,1000)==WAIT_OBJECT_0)
                    read_ok=GetOverlappedResult(server,&overlapped,&read,FALSE)!=FALSE;
                internal_pipe_ok=wrote && read_ok && written==sizeof(pipe_data) && read==sizeof(pipe_data)
                                 && memcmp(pipe_data,received,sizeof(pipe_data))==0;
                CancelIoEx(server,&overlapped);if(overlapped.hEvent)CloseHandle(overlapped.hEvent);
                CloseHandle(client);
            }
            CloseHandle(server);
        }
    }
    HANDLE appdata=CreateFileW(argv[11],GENERIC_READ|GENERIC_WRITE,FILE_SHARE_READ,nullptr,
                              OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    DWORD appdata_error=appdata==INVALID_HANDLE_VALUE ? GetLastError() : 0;
    if(appdata!=INVALID_HANDLE_VALUE)CloseHandle(appdata);
    std::ostringstream out;
    out << "{\"pid\":" << GetCurrentProcessId() << ",\"sandbox_verified\":true,"
        << "\"file_d\":" << (file_d?"true":"false") << ",\"file_e\":" << (file_e?"true":"false")
        << ",\"file_c\":" << (file_c?"true":"false") << ",\"file_d_error\":" << error_d
        << ",\"file_e_error\":" << error_e << ",\"file_c_error\":" << error_c
        << ",\"registry\":" << (registry?"true":"false")
        << ",\"wsa_startup\":" << started << ",\"tcp4_error\":" << tcp4 << ",\"tcp6_error\":" << tcp6
        << ",\"external_error\":" << external << ",\"udp_error\":" << udp << ",\"pipe_error\":" << pipe_error
        << ",\"internal_pipe_ok\":" << (internal_pipe_ok?"true":"false")
        << ",\"appdata_deny_error\":" << appdata_error;
    // 用途：当用户目录探针失败时定位哪一级不可见，区分权限/路径/容器问题。
    out << ",\"c_path_checks\":[";
    std::wstring cpath = argv[5]; bool first = true;
    for (size_t i = 2; i <= cpath.size(); ++i) {
        if (i != cpath.size() && cpath[i] != L'\\') continue;
        std::wstring prefix = cpath.substr(0, i == 2 ? 3 : i);
        DWORD attr = GetFileAttributesW(prefix.c_str());
        if (!first) out << ","; first = false;
        out << "{\"length\":" << prefix.size() << ",\"attributes\":" << attr
            << ",\"error\":" << (attr == INVALID_FILE_ATTRIBUTES ? GetLastError() : 0) << "}";
    }
    out << "]";
    wchar_t local[4096]{}; GetEnvironmentVariableW(L"LOCALAPPDATA",local,4096);
    out << ",\"local_env\":" << std::quoted(utf8(local)) << ",\"token_sid\":" << std::quoted(utf8(sid));
    HANDLE dir=CreateFileW(local, FILE_READ_ATTRIBUTES, FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,
                          nullptr, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, nullptr);
    wchar_t finalname[4096]{};
    if(dir!=INVALID_HANDLE_VALUE){ GetFinalPathNameByHandleW(dir,finalname,4096,FILE_NAME_NORMALIZED); CloseHandle(dir); }
    out << ",\"local_final\":" << std::quoted(utf8(finalname)) << "}";
    std::string json = out.str();
    HANDLE report = CreateFileW(argv[2], GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (report == INVALID_HANDLE_VALUE) return 66;
    DWORD count = 0; bool saved = WriteFile(report, json.data(), static_cast<DWORD>(json.size()), &count, nullptr);
    CloseHandle(report);
    return saved && file_d && file_e && file_c && registry && tcp4 == (local_tcp?0:WSAEACCES) && tcp6 == (local_tcp?0:WSAEACCES)
            // WFP可能接受UDP入队再丢弃；UDP是否抵达由主机端阳性/阴性接收实验裁决。
            && external == WSAEACCES && (udp == WSAEACCES || udp == 0) && pipe_error != 0 && appdata_error==ERROR_ACCESS_DENIED
            && (_wcsicmp(argv[1],L"PBZSteamLab")!=0 || internal_pipe_ok) ? 0 : 67;
}
