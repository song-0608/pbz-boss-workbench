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
std::array<SHORT, 256> message_keys{};
SHORT queued_key_state(int key) { return message_keys.at(key); }
bool foreground = true;
DWORD pid = 42;
std::wstring window_class = L"UnrealWindow";
bool hook_available = false;
HOOKPROC hook = nullptr;
int installs = 0, unhooks = 0;
ULONGLONG ticks = 1000;
DWORD current_thread() { return 1; }
ULONGLONG tick_count() { return ticks; }
HHOOK install_hook(int type, HOOKPROC callback, HINSTANCE module, DWORD thread) {
    ++installs;
    if (!hook_available) return nullptr;
    if (type != WH_GETMESSAGE || module || thread != 1) throw std::runtime_error("process-local message hook required");
    hook = callback;
    return reinterpret_cast<HHOOK>(1);
}
BOOL unhook(HHOOK) { ++unhooks; hook = nullptr; return true; }
LRESULT next_hook(HHOOK, int, WPARAM, LPARAM) { return 73; }
void message(UINT type, WPARAM key = 0, LPARAM flags = 0, DWORD at = 0, WPARAM removed = PM_REMOVE, HWND window = reinterpret_cast<HWND>(1)) {
    if (!hook) throw std::runtime_error("message observer not installed");
    MSG message{}; message.hwnd = window; message.message = type; message.wParam = key;
    message.lParam = flags; message.time = at ? at : static_cast<DWORD>(ticks);
    if (removed == PM_REMOVE && key < 256) {
        if (type == WM_KEYDOWN || type == WM_SYSKEYDOWN) message_keys[key] = static_cast<SHORT>(0x8000);
        if (type == WM_KEYUP || type == WM_SYSKEYUP) message_keys[key] = 0;
    }
    if (hook(0, removed, reinterpret_cast<LPARAM>(&message)) != 73) throw std::runtime_error("message chain modified");
}
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
#define GetKeyState fixture::queued_key_state
#define GetForegroundWindow fixture::foreground_window
#define GetWindowThreadProcessId fixture::window_pid
#define GetCurrentProcessId fixture::current_pid
#define GetClassNameW fixture::class_name
#define GetCurrentThreadId fixture::current_thread
#define GetTickCount64 fixture::tick_count
#define SetWindowsHookExW fixture::install_hook
#define UnhookWindowsHookEx fixture::unhook
#define CallNextHookEx fixture::next_hook
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
        handler.register_keydown_event(Key::XBUTTON_ONE, []{});
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
        const auto failed_installs = fixture::installs;
        poll(); poll();
        require(fixture::installs == failed_installs, "unavailable message hook is not retried every poll");

        // Exercise the actual window-message production path. All Win32 calls
        // remain deterministic fixtures; no keyboard or mouse input is injected.
        source.deactivate(); fixture::keys.fill(0); fixture::hook_available = true;
        Win32AsyncInputSource messages(static_cast<const wchar_t*>(L"UnrealWindow"));
        messages.activate();
        auto drain = [&]() { return messages.process_event(&handler); };
        require(drain().empty() && fixture::hook, "message observer attaches only to the current process window thread");
        fixture::message(WM_KEYDOWN, Key::A); fixture::message(WM_KEYUP, Key::A);
        events = drain();
        require(events.size() == 1 && events[0].key == Key::A && fixture::keys[Key::A] == 0,
                "complete keyboard tap between async polls is preserved exactly once");
        require(drain().empty(), "drained message tap is never replayed");
        fixture::message(WM_KEYDOWN, VK_SHIFT); fixture::message(WM_KEYDOWN, Key::A);
        fixture::message(WM_KEYUP, Key::A); fixture::message(WM_KEYUP, VK_SHIFT);
        events = drain();
        require(events.size() == 1 && !events[0].modifier_keys.empty(), "short chord keeps event-time modifiers after release");
        fixture::message(WM_KEYDOWN, Key::A); fixture::message(WM_KEYDOWN, Key::A, LPARAM{1} << 30);
        require(drain().size() == 1, "held key and native autorepeat do not create duplicate actions");
        fixture::message(WM_KEYUP, Key::A);
        fixture::message(WM_LBUTTONDOWN); fixture::message(WM_LBUTTONUP);
        events = drain();
        require(events.size() == 1 && events[0].key == Key::LEFT_MOUSE_BUTTON, "short mouse tap uses the same bounded queue");
        fixture::message(WM_XBUTTONDOWN, WPARAM{XBUTTON1} << 16);
        fixture::message(WM_XBUTTONUP, WPARAM{XBUTTON1} << 16);
        events = drain();
        require(events.size() == 1 && events[0].key == Key::XBUTTON_ONE, "side mouse buttons remain available");
        fixture::message(WM_KEYDOWN, Key::A, 0, 0, PM_NOREMOVE);
        require(drain().empty(), "peeked message is ignored until removed");
        fixture::message(WM_KEYDOWN, Key::A); fixture::message(WM_KEYUP, Key::A);
        handler.set_allow_input(false);
        require(drain().empty(), "permission is rechecked at dispatch");
        fixture::message(WM_KEYDOWN, Key::A); fixture::message(WM_KEYUP, Key::A);
        handler.set_allow_input(true);
        require(drain().empty(), "press observed while input is disabled is discarded");
        fixture::message(WM_KEYDOWN, Key::A); fixture::message(WM_KEYUP, Key::A);
        fixture::ticks += 251;
        require(drain().empty(), "queued tap older than 250 ms expires after a stall");
        fixture::message(WM_KEYDOWN, Key::A, 0, static_cast<DWORD>(fixture::ticks - 300));
        require(drain().empty(), "stale window messages force a fresh focus baseline");
        fixture::message(WM_KEYDOWN, Key::A); fixture::message(WM_KEYUP, Key::A);
        fixture::message(WM_KILLFOCUS);
        require(drain().empty(), "focus loss between polls flushes pending input");
        fixture::message(WM_KEYDOWN, Key::A, 0, 0, PM_REMOVE, reinterpret_cast<HWND>(2));
        require(drain().empty(), "other window messages cannot trigger this source");
        fixture::pid = 99;
        fixture::message(WM_KEYDOWN, Key::A); fixture::message(WM_KEYUP, Key::A);
        fixture::pid = 42;
        require(drain().empty(), "foreign foreground activity cannot leak through a fast focus roundtrip");
        fixture::keys[Key::A] = static_cast<SHORT>(0x8000);
        fixture::foreground = false; drain(); fixture::foreground = true;
        require(drain().empty(), "message path seeds a key held on focus return");
        fixture::message(WM_KEYDOWN, Key::A);
        require(drain().empty(), "held key from another focus cannot cast");
        fixture::keys.fill(0); fixture::message(WM_KEYUP, Key::A);
        for (int index = 0; index < 65; ++index) {
            fixture::message(WM_KEYDOWN, Key::A); fixture::message(WM_KEYUP, Key::A);
        }
        require(drain().empty(), "overflow discards the batch and establishes a new baseline");
        fixture::message(WM_KEYDOWN, Key::A); fixture::message(WM_KEYUP, Key::A);
        require(drain().size() == 1, "fresh input resumes after bounded overflow recovery");
        fixture::message(WM_KEYDOWN, Key::A); fixture::message(WM_KEYUP, Key::A);
        messages.deactivate();
        require(!fixture::hook && fixture::unhooks == 1 && drain().empty(), "deactivation unhooks and drops pending actions");
        std::cout << "WIN32_ASYNC_INPUT_REGRESSION:PASS\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL: " << error.what() << '\n';
        return 1;
    }
}
