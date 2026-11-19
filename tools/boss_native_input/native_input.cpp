#define NOMINMAX
#include <windows.h>
#include <Mod/CppUserModBase.hpp>
#include <LuaMadeSimple/LuaMadeSimple.hpp>
#include "policy.hpp"

namespace {
class NativeInput final : public RC::CppUserModBase {
public:
    NativeInput() {
        ModName=STR("PBZNativeCombatInput");ModVersion=STR("0.1.0");
        ModDescription=STR("Read-only foreground and fixed RMB snapshot for the development Boss controller");
        ModAuthors=STR("PBZ local research");
    }
    auto on_lua_start(RC::StringViewType name, RC::LuaMadeSimple::Lua& lua,
        RC::LuaMadeSimple::Lua&, RC::LuaMadeSimple::Lua&, RC::LuaMadeSimple::Lua*) -> void override {
        if (name != STR("PBZBossControl") && name != STR("PBZObserveAI")
            && name != STR("PBZNativeInputSmoke")) return;
        lua.register_function("PBZNativeCombatInputSnapshot", [](const RC::LuaMadeSimple::Lua& state) -> int {
            // No async worker, global object scan, file polling, key injection, or engine mutation.
            const auto window=GetForegroundWindow();DWORD pid=0;wchar_t cls[256]{};
            if (window) GetWindowThreadProcessId(window,&pid);
            const auto class_ok=window && GetClassNameW(window,cls,256)>0;
            const auto control=(GetAsyncKeyState(VK_CONTROL)&0x8000)!=0;
            const auto alt=(GetAsyncKeyState(VK_MENU)&0x8000)!=0;
            const bool permitted=class_ok && pbz_input::allowed(GetCurrentProcessId(),pid,cls,
                IsIconic(window)!=FALSE,control,alt);
            const bool down=permitted && (GetAsyncKeyState(VK_RBUTTON)&0x8000)!=0;
            auto result=state.prepare_new_table();
            result.add_pair("schema",1);result.add_pair("allowed",permitted);result.add_pair("down",down);
            result.add_pair("now",static_cast<double>(GetTickCount64())/1000.0);
            result.add_pair("pid",static_cast<std::int64_t>(GetCurrentProcessId()));
            result.make_local();return 1;
        });
    }
};
}
extern "C" {
__declspec(dllexport) RC::CppUserModBase* start_mod() {return new NativeInput();}
__declspec(dllexport) void uninstall_mod(RC::CppUserModBase* mod) {delete mod;}
}
