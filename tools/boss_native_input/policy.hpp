#pragma once
#include <cstdint>
#include <string_view>
namespace pbz_input {
// Pure policy is also exercised without creating a window or reading real keys.
inline bool allowed(std::uint32_t own_pid, std::uint32_t foreground_pid,
                    std::wstring_view window_class, bool minimized, bool control, bool alt) {
    return own_pid != 0 && own_pid == foreground_pid && !minimized && !control && !alt
        && (window_class == L"UnrealWindow" || window_class == L"Sandbox:PBZSteamLab:UnrealWindow");
}
}
