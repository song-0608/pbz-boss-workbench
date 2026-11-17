#define NOMINMAX
#define HAS_INPUT
#define RC_INPUT_BUILD_STATIC
#include <Windows.h>
#include <array>
#include <iostream>
#include <stdexcept>
#include <string>
#include <Input/Handler.hpp>
#include <Input/Platform/Win32AsyncInputSource.hpp>

namespace fixture {
std::array<SHORT, 256> keys{};
bool foreground = true;
DWORD pid = 42;
std::wstring window_class = L"UnrealWindow";
SHORT async_state(int key) { SHORT state = keys.at(key); keys[key] &= ~1; return state; }
HWND foreground_window() { return foreground ? reinterpret_cast<HWND>(1) : nullptr; }
DWORD window_pid(HWND, LPDWORD result) { if (result) *result = pid; return 1; }
DWORD current_pid() { return 42; }
int class_name(HWND, LPWSTR output, int size) {
    if (window_class.empty()) return 0;
    wcsncpy_s(output, size, window_class.c_str(), _TRUNCATE);
    return static_cast<int>(window_class.size());
}
void require(bool value, const char* label) {
    if (!value) throw std::runtime_error(label);
    std::cout << "PASS: " << label << '\n';
}
}

#define GetAsyncKeyState fixture::async_state
#define GetForegroundWindow fixture::foreground_window
#define GetWindowThreadProcessId fixture::window_pid
#define GetCurrentProcessId fixture::current_pid
#define GetClassNameW fixture::class_name
// Compile the actual production implementation against deterministic Win32 calls.
#include "../upstream/RE-UE4SS/deps/first/Input/src/Platform/Win32AsyncInputSource.cpp"

namespace RC::Input {
auto ModifierKeys::operator|=(const ModifierKey& key) -> ModifierKeys& {
    keys |= ModifierKeys(key).keys;
    return *this;
}
auto Handler::get_allow_input() -> bool { return m_allow_input; }
auto Handler::set_allow_input(bool value) -> void { m_allow_input = value; }
auto Handler::register_keydown_event(Key key, EventCallbackCallable, uint8_t, void*) -> void {
    m_subscribed_keys[static_cast<size_t>(key)] = true;
}
}

int main() {
    using namespace RC::Input;
    using fixture::require;
    try {
        Handler handler;
        handler.register_keydown_event(Key::A, []{});
        handler.register_keydown_event(Key::LEFT_MOUSE_BUTTON, []{});
        Win32AsyncInputSource source(static_cast<const wchar_t*>(L"UnrealWindow"));
        source.activate();
        auto poll = [&]() { return source.process_event(&handler); };
        require(poll().empty(), "initial focus establishes baseline");
        fixture::keys[Key::A] = 1;
        fixture::keys[Key::LEFT_MOUSE_BUTTON] = 1;
        require(poll().empty(), "historical low bits do not generate keyboard or mouse events");
        fixture::keys[Key::A] = static_cast<SHORT>(0x8001);
        auto events = poll();
        require(events.size() == 1 && events[0].key == Key::A, "high bit generates one real press");
        require(poll().empty() && poll().empty(), "held key does not repeat");
        fixture::keys[Key::A] = 0; poll();
        fixture::keys[Key::A] = static_cast<SHORT>(0x8000);
        require(poll().size() == 1, "released key may be pressed again");
        fixture::keys[Key::A] = 0;
        fixture::keys[Key::LEFT_MOUSE_BUTTON] = static_cast<SHORT>(0x8000);
        events = poll();
        require(events.size() == 1 && events[0].key == Key::LEFT_MOUSE_BUTTON,
                "next distinct press needs no idle sampling frame");
        fixture::keys[Key::LEFT_MOUSE_BUTTON] = 0;
        fixture::keys[Key::A] = static_cast<SHORT>(0x8000);
        events = poll();
        require(events.size() == 1 && events[0].key == Key::A,
                "alternating keys preserve every new press");
        fixture::foreground = false;
        require(poll().empty(), "unfocused window receives no events");
        fixture::foreground = true;
        require(poll().empty() && poll().empty(), "key held during focus return is suppressed");
        fixture::keys.fill(0); poll();
        fixture::pid = 99;
        fixture::keys[Key::LEFT_MOUSE_BUTTON] = static_cast<SHORT>(0x8000);
        require(poll().empty(), "same class in another process is rejected");
        fixture::pid = 42;
        require(poll().empty() && poll().empty(), "foreign process press cannot leak on focus return");
        fixture::keys.fill(0); poll();
        fixture::keys[VK_SHIFT] = 1;
        fixture::keys[Key::A] = static_cast<SHORT>(0x8000);
        events = poll();
        require(events.size() == 1 && events[0].modifier_keys.empty(), "historical modifier bit is ignored");
        fixture::keys.fill(0); poll(); poll();
        fixture::keys[VK_SHIFT] = static_cast<SHORT>(0x8000);
        fixture::keys[Key::A] = static_cast<SHORT>(0x8000);
        events = poll();
        require(events.size() == 1 && !events[0].modifier_keys.empty(), "held modifier remains functional");
        fixture::keys.fill(0); poll(); poll();
        handler.set_allow_input(false);
        fixture::keys[Key::A] = static_cast<SHORT>(0x8000);
        require(poll().empty(), "input permission gate is preserved");
        handler.set_allow_input(true);
        require(poll().empty(), "disallowed press is not replayed later");
        source.deactivate(); fixture::keys.fill(0); poll(); source.activate();
        fixture::keys[Key::A] = static_cast<SHORT>(0x8000);
        require(poll().empty(), "reactivation resets focus baseline");
        fixture::keys.fill(0); poll();
        fixture::window_class = L"Sandbox:PBZSteamLab:UnrealWindow";
        fixture::keys[Key::A] = static_cast<SHORT>(0x8000);
        require(poll().size() == 1, "exact observed research class accepts a current press");
        fixture::keys.fill(0); poll();
        fixture::pid = 99;
        fixture::keys[Key::A] = static_cast<SHORT>(0x8000);
        require(poll().empty(), "research class in another process stays rejected");
        fixture::pid = 42;
        require(poll().empty() && poll().empty(), "return from foreign research window seeds held keys");
        fixture::keys.fill(0); poll();
        fixture::window_class = L"Sandbox:OtherBox:UnrealWindow";
        fixture::keys[Key::A] = static_cast<SHORT>(0x8000);
        require(poll().empty(), "other sandbox namespace stays rejected");
        fixture::keys.fill(0); poll();
        fixture::window_class = L"OtherPrefix:UnrealWindow";
        fixture::keys[Key::A] = static_cast<SHORT>(0x8000);
        require(poll().empty(), "arbitrary class suffix is insufficient");
        fixture::window_class = L"Sandbox:PBZSteamLab:UnrealWindow";
        fixture::keys.fill(0); poll();
        fixture::keys[Key::A] = 1;
        require(poll().empty(), "research window cannot replay historical low bits");
        std::cout << "WIN32_ASYNC_INPUT_REGRESSION:PASS\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL: " << error.what() << '\n';
        return 1;
    }
}
