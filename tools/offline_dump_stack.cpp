// 用途：离线读取本地崩溃转储，用 Windows SDK 展开异常线程；不附加、不启动游戏。
// 隐私：只导出模块名、地址和状态，不导出内存字符串、账号或转储正文。
#define NOMINMAX
#include <windows.h>
#include <dbghelp.h>
#include <algorithm>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#pragma comment(lib, "dbghelp.lib")

struct Span { ULONG64 address, size, offset; };
struct Module {
    ULONG64 base; ULONG size, timestamp; std::wstring path; std::string name; bool matched=false;
    ULONG header_size=0; std::vector<IMAGE_SECTION_HEADER> sections; std::vector<IMAGE_RUNTIME_FUNCTION_ENTRY> functions;
};
static const unsigned char* bytes=nullptr;
static ULONG64 byte_count=0;
static std::vector<Span> spans;
static std::vector<Module> modules;
static unsigned read_misses=0, table_hits=0, table_misses=0, image_reads=0;

// 用途：拒绝越过转储边界的读取，避免损坏的诊断文件导致越界。
static const unsigned char* at(ULONG64 offset, ULONG64 size) {
    if (offset>byte_count || size>byte_count-offset) throw std::runtime_error("dump_bounds");
    return bytes+offset;
}
template<class T> static const T* obj(ULONG64 offset) { return reinterpret_cast<const T*>(at(offset,sizeof(T))); }
static std::string hex(ULONG64 n) { std::ostringstream s; s<<"0x"<<std::hex<<n; return s.str(); }
static std::string ascii_name(std::wstring s) {
    std::string out; for(wchar_t c:s) out+=(c>=32 && c<127)?char(c):'?'; return out;
}
static std::string quote(const std::string& s) {
    std::string out="\""; for(char c:s) { if(c=='\\'||c=='\"')out+='\\'; if(static_cast<unsigned char>(c)>=32)out+=c; } return out+'\"';
}
static Module* locate(ULONG64 pc) {
    for(auto& m:modules) if(pc>=m.base && pc-m.base<m.size)return &m; return nullptr;
}
// 用途：缺少转储映像页时，从头信息已匹配的本机 PE 文件读取展开元数据，明确计数。
static bool image_read(Module& m, ULONG64 rva, void* buffer, DWORD size) {
    if(!m.matched)return false;ULONG64 raw=0;bool found=false;
    if(rva<m.header_size && size<=m.header_size-rva) {raw=rva;found=true;}
    for(const auto& s:m.sections)if(rva>=s.VirtualAddress && rva-s.VirtualAddress<s.SizeOfRawData
        && size<=s.SizeOfRawData-(rva-s.VirtualAddress)) {raw=s.PointerToRawData+rva-s.VirtualAddress;found=true;break;}
    if(!found)return false;std::ifstream f(std::filesystem::path(m.path),std::ios::binary);
    f.seekg(raw);f.read(static_cast<char*>(buffer),size);return bool(f);
}
// 用途：StackWalk64 只能读取转储里已记录的字节；不读取任何运行中进程。
static BOOL CALLBACK read_dump(HANDLE, DWORD64 address, PVOID buffer, DWORD size, LPDWORD actual) {
    *actual=0;
    while(*actual<size) {
        bool found=false;
        for(const auto& s:spans) if(address>=s.address && address-s.address<s.size) {
            auto n=static_cast<DWORD>(std::min<ULONG64>(size-*actual,s.size-(address-s.address)));
            std::memcpy(static_cast<unsigned char*>(buffer)+*actual,at(s.offset+address-s.address,n),n);
            address+=n; *actual+=n; found=true; break;
        }
        if(!found) {
            auto m=locate(address);auto n=size-*actual;
            if(m && image_read(*m,address-m->base,static_cast<unsigned char*>(buffer)+*actual,n)) {
                ++image_reads;*actual+=n;address+=n;continue;
            }
            ++read_misses; return *actual!=0;
        }
    }
    return TRUE;
}
static PVOID CALLBACK function_table(HANDLE,DWORD64 pc) {
    auto m=locate(pc);
    if(m && m->matched) {
        auto rva=pc-m->base;
        auto it=std::upper_bound(m->functions.begin(),m->functions.end(),rva,
            [](ULONG64 value,const IMAGE_RUNTIME_FUNCTION_ENTRY& fn){return value<fn.BeginAddress;});
        if(it!=m->functions.begin()) {--it;if(rva>=it->BeginAddress && rva<it->EndAddress) {++table_hits;return &*it;}}
    }
    ++table_misses;return nullptr;
}
static DWORD64 CALLBACK module_base(HANDLE,DWORD64 pc) { auto m=locate(pc);return m?m->base:0; }
// 用途：只打开明确的本机盘符路径，检查时间戳与映像大小；不访问 UNC/符号服务器。
static bool matching_image(Module& m) {
    if(m.path.rfind(L"\\??\\",0)==0)m.path=m.path.substr(4);
    if(m.path.size()<3 || m.path[1]!=L':' || m.path[2]!=L'\\')return false;
    std::ifstream f(std::filesystem::path(m.path),std::ios::binary);
    IMAGE_DOS_HEADER dos{};f.read(reinterpret_cast<char*>(&dos),sizeof(dos));
    if(!f || dos.e_magic!=IMAGE_DOS_SIGNATURE || dos.e_lfanew<0 || dos.e_lfanew>1048576)return false;
    f.seekg(dos.e_lfanew);IMAGE_NT_HEADERS64 nt{};f.read(reinterpret_cast<char*>(&nt),sizeof(nt));
    bool match=f && nt.Signature==IMAGE_NT_SIGNATURE && nt.OptionalHeader.Magic==IMAGE_NT_OPTIONAL_HDR64_MAGIC
        && nt.OptionalHeader.SizeOfImage==m.size && nt.FileHeader.TimeDateStamp==m.timestamp;
    if(!match || nt.FileHeader.NumberOfSections>256)return false;
    m.header_size=nt.OptionalHeader.SizeOfHeaders;m.sections.resize(nt.FileHeader.NumberOfSections);
    f.seekg(dos.e_lfanew+sizeof(DWORD)+sizeof(IMAGE_FILE_HEADER)+nt.FileHeader.SizeOfOptionalHeader);
    f.read(reinterpret_cast<char*>(m.sections.data()),m.sections.size()*sizeof(IMAGE_SECTION_HEADER));
    if(!f)return false;m.matched=true;
    auto dir=nt.OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_EXCEPTION];
    if(dir.Size && dir.Size<67108864 && dir.Size%sizeof(IMAGE_RUNTIME_FUNCTION_ENTRY)==0) {
        m.functions.resize(dir.Size/sizeof(IMAGE_RUNTIME_FUNCTION_ENTRY));
        if(!image_read(m,dir.VirtualAddress,m.functions.data(),dir.Size))m.functions.clear();
    }
    return true;
}
static void frame_json(std::ostream& out, unsigned i, ULONG64 pc, ULONG64 sp) {
    auto m=locate(pc);out<<"{\"index\":"<<i<<",\"pc\":"<<quote(hex(pc))<<",\"sp\":"<<quote(hex(sp));
    if(m)out<<",\"module\":"<<quote(m->name)<<",\"rva\":"<<quote(hex(pc-m->base))
        <<",\"local_image_headers_match\":"<<(m->matched?"true":"false");
    else out<<",\"module\":null";
    out<<"}";
}
int wmain(int argc,wchar_t** argv) {
    if(argc!=4) { std::cerr<<"usage: offline_dump_stack.exe dump.dmp report.json local-symbol-directory\n";return 2; }
    HANDLE file=INVALID_HANDLE_VALUE,mapping=nullptr;
    try {
        // 用途：转储以只读映射打开；所有输出限定为用户指定的研究报告路径。
        file=CreateFileW(argv[1],GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
        if(file==INVALID_HANDLE_VALUE)throw std::runtime_error("open_dump");
        LARGE_INTEGER sz{};if(!GetFileSizeEx(file,&sz))throw std::runtime_error("dump_size");byte_count=sz.QuadPart;
        mapping=CreateFileMappingW(file,nullptr,PAGE_READONLY,0,0,nullptr);if(!mapping)throw std::runtime_error("map_dump");
        bytes=static_cast<const unsigned char*>(MapViewOfFile(mapping,FILE_MAP_READ,0,0,0));if(!bytes)throw std::runtime_error("view_dump");
        auto header=obj<MINIDUMP_HEADER>(0);if(header->Signature!=MINIDUMP_SIGNATURE || header->NumberOfStreams>4096)throw std::runtime_error("dump_header");
        const MINIDUMP_EXCEPTION_STREAM* exception=nullptr;const MINIDUMP_SYSTEM_INFO* system=nullptr;
        for(ULONG i=0;i<header->NumberOfStreams;++i) {
            auto d=obj<MINIDUMP_DIRECTORY>(header->StreamDirectoryRva+i*sizeof(MINIDUMP_DIRECTORY));
            at(d->Location.Rva,d->Location.DataSize);auto off=d->Location.Rva;
            if(d->StreamType==ExceptionStream)exception=obj<MINIDUMP_EXCEPTION_STREAM>(off);
            if(d->StreamType==SystemInfoStream)system=obj<MINIDUMP_SYSTEM_INFO>(off);
            if(d->StreamType==MemoryListStream) {
                auto n=*obj<ULONG>(off);if(n>1000000)throw std::runtime_error("memory_count");
                for(ULONG j=0;j<n;++j) { auto s=obj<MINIDUMP_MEMORY_DESCRIPTOR>(off+4+j*sizeof(MINIDUMP_MEMORY_DESCRIPTOR));
                    at(s->Memory.Rva,s->Memory.DataSize);spans.push_back({s->StartOfMemoryRange,s->Memory.DataSize,s->Memory.Rva}); }
            }
            if(d->StreamType==Memory64ListStream) {
                auto n=*obj<ULONG64>(off);auto data=*obj<ULONG64>(off+8);if(n>1000000)throw std::runtime_error("memory64_count");
                for(ULONG64 j=0;j<n;++j) { auto s=obj<MINIDUMP_MEMORY_DESCRIPTOR64>(off+16+j*sizeof(MINIDUMP_MEMORY_DESCRIPTOR64));
                    at(data,s->DataSize);spans.push_back({s->StartOfMemoryRange,s->DataSize,data});data+=s->DataSize; }
            }
            if(d->StreamType==ThreadListStream) {
                auto n=*obj<ULONG>(off);if(n>100000)throw std::runtime_error("thread_count");
                for(ULONG j=0;j<n;++j) { auto t=obj<MINIDUMP_THREAD>(off+4+j*sizeof(MINIDUMP_THREAD));
                    at(t->Stack.Memory.Rva,t->Stack.Memory.DataSize);spans.push_back({t->Stack.StartOfMemoryRange,t->Stack.Memory.DataSize,t->Stack.Memory.Rva}); }
            }
            if(d->StreamType==ModuleListStream) {
                auto n=*obj<ULONG>(off);if(n>100000)throw std::runtime_error("module_count");
                for(ULONG j=0;j<n;++j) { auto m=obj<MINIDUMP_MODULE>(off+4+j*sizeof(MINIDUMP_MODULE));
                    auto len=*obj<ULONG>(m->ModuleNameRva);if(len>65536 || len%2)throw std::runtime_error("module_name");
                    std::wstring path(reinterpret_cast<const wchar_t*>(at(m->ModuleNameRva+4,len)),len/2);
                    modules.push_back({m->BaseOfImage,m->SizeOfImage,m->TimeDateStamp,path,ascii_name(std::filesystem::path(path).filename().wstring())}); }
            }
        }
        if(!exception || !system || system->ProcessorArchitecture!=PROCESSOR_ARCHITECTURE_AMD64)throw std::runtime_error("need_amd64_exception");
        if(exception->ThreadContext.DataSize<sizeof(CONTEXT))throw std::runtime_error("short_context");
        CONTEXT context{};std::memcpy(&context,at(exception->ThreadContext.Rva,sizeof(context)),sizeof(context));
        // 用途：只给 StackWalk64 使用独立句柄；所有回调由本工具提供，完全不启动符号引擎。
        // 不调用 SymInitialize/SymLoadModule，因此也不会跟随映像里记录的外部 PDB 路径。
        int key=0;HANDLE h=reinterpret_cast<HANDLE>(&key);
        unsigned matched=0;
        for(auto& m:modules) { m.matched=matching_image(m);if(m.matched)++matched; }
        std::ofstream out(std::filesystem::path(argv[2]),std::ios::binary);if(!out)throw std::runtime_error("open_report");
        out<<"{\n\"method\":\"DbgHelp StackWalk64; dump-memory callback; matching local PE runtime-function tables; explicit local-image fallback; no symbol engine or PDB loading\",\n"
            <<"\"exception_code\":"<<quote(hex(exception->ExceptionRecord.ExceptionCode))
            <<",\n\"module_count\":"<<modules.size()<<",\"matching_images\":"<<matched<<",\"symbol_engine_used\":false,\n";
        auto seed_module=locate(context.Rip);
        out<<"\"exception_image_runtime_function_entries\":"<<(seed_module?seed_module->functions.size():0)
            <<",\"exception_pc_covered_by_local_runtime_function\":"<<(function_table(h,context.Rip)?"true":"false")<<",\n";
        if(exception->ExceptionRecord.NumberParameters>=2)out<<"\"access_operation\":"<<exception->ExceptionRecord.ExceptionInformation[0]
            <<",\"access_target\":"<<quote(hex(exception->ExceptionRecord.ExceptionInformation[1]))<<",\n";
        out<<"\"frames\":[\n";frame_json(out,0,context.Rip,context.Rsp);
        STACKFRAME64 frame{};frame.AddrPC={context.Rip,0,AddrModeFlat};frame.AddrStack={context.Rsp,0,AddrModeFlat};frame.AddrFrame={context.Rbp,0,AddrModeFlat};
        ULONG64 last_pc=context.Rip,last_sp=context.Rsp;unsigned recovered=0;std::string reason="frame_limit";
        for(unsigned i=0;i<64;++i) {
            SetLastError(0);BOOL ok=StackWalk64(IMAGE_FILE_MACHINE_AMD64,h,nullptr,&frame,&context,read_dump,function_table,module_base,nullptr);
            if(!ok) { reason="StackWalk64_failed_"+std::to_string(GetLastError());break; }
            if(frame.AddrPC.Offset==last_pc && frame.AddrStack.Offset==last_sp)continue;
            if(!frame.AddrPC.Offset) {reason="zero_pc";break;}
            if(frame.AddrStack.Offset<=last_sp) {reason="nonincreasing_sp";break;}
            if(!locate(frame.AddrPC.Offset)) {reason="next_pc_not_in_recorded_module";break;}
            out<<",\n";frame_json(out,++recovered,frame.AddrPC.Offset,frame.AddrStack.Offset);
            last_pc=frame.AddrPC.Offset;last_sp=frame.AddrStack.Offset;
        }
        out<<"\n],\n\"recovered_caller_frames\":"<<recovered<<",\"stop_reason\":"<<quote(reason)
            <<",\"dump_read_misses\":"<<read_misses<<",\"function_table_hits\":"<<table_hits<<",\"function_table_misses\":"<<table_misses
            <<",\"local_image_fallback_reads\":"<<image_reads
            <<",\n\"limitations\":\"Frame 0 is the exception context. Caller frames require validation; an incomplete walk is not a root cause. Matching PE headers alone does not prove runtime code and unwind metadata were unchanged.\"\n}\n";
        UnmapViewOfFile(bytes);CloseHandle(mapping);CloseHandle(file);
        std::cout<<"recovered_callers="<<recovered<<" stop="<<reason<<"\n";return 0;
    } catch(const std::exception& e) {
        if(bytes)UnmapViewOfFile(bytes);if(mapping)CloseHandle(mapping);if(file!=INVALID_HANDLE_VALUE)CloseHandle(file);
        std::cerr<<"offline_analysis_failed: "<<e.what()<<"\n";return 1;
    }
}
