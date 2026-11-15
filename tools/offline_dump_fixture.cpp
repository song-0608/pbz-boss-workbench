// 用途：在专用小程序中产生一个已知调用链的转储，检验分析器；与游戏和存档无关。
#include <windows.h>
#include <dbghelp.h>
#pragma comment(lib,"dbghelp.lib")
__declspec(noinline) int known_leaf(volatile int* p) { return *p+3; }
__declspec(noinline) int known_middle(volatile int* p) { volatile int n=known_leaf(p);return n+5; }
__declspec(noinline) int known_outer(volatile int* p) { volatile int n=known_middle(p);return n+7; }
static int save_fixture(EXCEPTION_POINTERS* info) {
    HANDLE f=CreateFileW(L"fixture.dmp",GENERIC_WRITE,0,nullptr,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(f==INVALID_HANDLE_VALUE)return EXCEPTION_CONTINUE_SEARCH;
    MINIDUMP_EXCEPTION_INFORMATION e{GetCurrentThreadId(),info,FALSE};
    BOOL ok=MiniDumpWriteDump(GetCurrentProcess(),GetCurrentProcessId(),f,MiniDumpNormal,&e,nullptr,nullptr);
    CloseHandle(f);return ok?EXCEPTION_EXECUTE_HANDLER:EXCEPTION_CONTINUE_SEARCH;
}
int main() {
    SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);
    __try { volatile int* p=nullptr;return known_outer(p); }
    __except(save_fixture(GetExceptionInformation())) { return 0; }
}
