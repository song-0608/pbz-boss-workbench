// Exercise the exact two Saved locations without opening an existing save file.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <filesystem>
#include <string>
#include <cstdio>

using QueryProcess=LONG (*)(HANDLE,WCHAR*,WCHAR*,WCHAR*,ULONG*);

bool marker(const std::filesystem::path& path,const std::string& token,bool create) {
    const auto name=path.filename().wstring();
    if (name.rfind(L"BWBOnlineProbe_",0)!=0 || path.extension()!=L".tmp"
        || path.parent_path().filename()!=L"Saved") return false;
    if (create) {
        std::filesystem::create_directories(path.parent_path());
        // CREATE_NEW also proves that this box did not see the other box's marker.
        HANDLE file=CreateFileW(path.c_str(),GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);
        if (file==INVALID_HANDLE_VALUE)return false;
        DWORD size=0;const bool ok=WriteFile(file,token.data(),static_cast<DWORD>(token.size()),&size,nullptr)
            && size==token.size();CloseHandle(file);if (!ok)return false;
    }
    HANDLE file=CreateFileW(path.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,0,nullptr);
    if(file==INVALID_HANDLE_VALUE)return false;
    char text[256]{};DWORD size=0;
    const bool ok=ReadFile(file,text,sizeof(text),&size,nullptr) && std::string(text,size)==token;
    CloseHandle(file);return ok;
}

int wmain(int argc,wchar_t** argv) {
    if(argc!=7)return 2;
    const std::wstring box=argv[1],mode=argv[2];
    if ((box!=L"PBZOnlineHost" && box!=L"PBZOnlineGuest") || (mode!=L"write" && mode!=L"read"))return 2;
    HMODULE dll=GetModuleHandleW(L"SbieDll.dll");
    auto query=dll?reinterpret_cast<QueryProcess>(GetProcAddress(dll,"SbieApi_QueryProcess")):nullptr;
    WCHAR actual[64]{},image[128]{},sid[128]{};ULONG session=0;
    if(!query || query(reinterpret_cast<HANDLE>(static_cast<ULONG_PTR>(GetCurrentProcessId())),
        actual,image,sid,&session)!=0 || box!=actual)return 3;
    const std::wstring wide_token=argv[5];
    if(wide_token.size()!=32)return 2;
    std::string token;
    for(wchar_t c:wide_token){if(!((c>=L'0' && c<=L'9') || (c>=L'a' && c<=L'f')))return 2;token+=static_cast<char>(c);}
    bool local=false,installed=false;
    try {
        local=marker(argv[3],token,mode==L"write");
        installed=marker(argv[4],token,mode==L"write");
    }catch(const std::exception&){}
    const std::string result=std::string("{\"sandbox_verified\":true,\"local_saved\":")
        +(local?"true":"false")+",\"installed_saved\":"+(installed?"true":"false")+"}\n";
    HANDLE report=CreateFileW(argv[6],GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(report==INVALID_HANDLE_VALUE)return 4;
    DWORD written=0;const bool saved=WriteFile(report,result.data(),static_cast<DWORD>(result.size()),&written,nullptr)
        && written==result.size();CloseHandle(report);
    return saved && local && installed ? 0 : 5;
}
