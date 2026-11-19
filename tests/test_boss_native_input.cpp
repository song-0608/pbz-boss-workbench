#include "policy.hpp"
#include <cstdlib>
#include <iostream>
int main() {
    using pbz_input::allowed;
    auto check=[](bool condition){if(!condition)std::abort();};
    check(allowed(42,42,L"UnrealWindow",false,false,false));
    check(allowed(42,42,L"Sandbox:PBZSteamLab:UnrealWindow",false,false,false));
    check(!allowed(42,43,L"UnrealWindow",false,false,false));
    check(!allowed(0,0,L"UnrealWindow",false,false,false));
    check(!allowed(42,42,L"ConsoleWindowClass",false,false,false));
    check(!allowed(42,42,L"Sandbox:Other:UnrealWindow",false,false,false));
    check(!allowed(42,42,L"UnrealWindow",true,false,false));
    check(!allowed(42,42,L"UnrealWindow",false,true,false));
    check(!allowed(42,42,L"UnrealWindow",false,false,true));
    std::cout<<"PASS nine native focus policy cases; no live key or gameplay acceptance\n";
}
