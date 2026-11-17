#include <Input/Handler.hpp>
#include <Input/KeyDef.hpp>
#include <Input/Common.hpp>
#include <Input/Platform/Win32AsyncInputSource.hpp>
#include <mutex>

#define NOMINMAX
#include <Windows.h>

namespace RC::Input
{
    // A hook on this process's game-window thread observes ordinary messages;
    // it never injects input, changes a message, or hooks another process.
    // Keeping a bounded queue avoids losing a complete tap between async polls.
    struct Win32WindowMessages
    {
        struct Press { InputEvent event; DWORD at; };
        std::mutex mutex;
        HWND window{};
        DWORD thread{};
        HHOOK hook{};
        bool focused{false};
        bool allowed{false};
        bool active{true};
        DWORD baseline{};
        std::array<bool, max_keys> down{};
        std::array<bool, max_keys> subscribed{};
        std::vector<Press> pending;
    };

    namespace
    {
        std::mutex message_sources_mutex;
        std::unordered_map<DWORD, std::weak_ptr<Win32WindowMessages>> message_sources;

        LRESULT CALLBACK message_hook(int code, WPARAM removed, LPARAM value)
        {
            std::shared_ptr<Win32WindowMessages> source;
            {
                std::lock_guard lock(message_sources_mutex);
                auto found = message_sources.find(GetCurrentThreadId());
                if (found != message_sources.end()) source = found->second.lock();
            }
            if (code >= 0 && removed == PM_REMOVE && source)
            {
                const auto& message = *reinterpret_cast<const MSG*>(value);
                std::lock_guard lock(source->mutex);
                if (source->active && message.hwnd == source->window)
                {
                    DWORD pid{};
                    const auto foreground = GetForegroundWindow();
                    if (foreground) GetWindowThreadProcessId(foreground, &pid);
                    if (foreground != source->window || pid != GetCurrentProcessId() || message.message == WM_KILLFOCUS ||
                        (message.message == WM_ACTIVATEAPP && !message.wParam))
                    {
                        source->focused = false;
                        source->pending.clear();
                    }
                    else if (source->focused)
                    {
                        int key = -1;
                        bool down = false;
                        bool repeat = false;
                        switch (message.message)
                        {
                        case WM_KEYDOWN: case WM_SYSKEYDOWN:
                            key = static_cast<int>(message.wParam); down = true;
                            repeat = (message.lParam & (LPARAM{1} << 30)) != 0; break;
                        case WM_KEYUP: case WM_SYSKEYUP: key = static_cast<int>(message.wParam); break;
                        case WM_LBUTTONDOWN: case WM_LBUTTONDBLCLK: key = VK_LBUTTON; down = true; break;
                        case WM_LBUTTONUP: key = VK_LBUTTON; break;
                        case WM_RBUTTONDOWN: case WM_RBUTTONDBLCLK: key = VK_RBUTTON; down = true; break;
                        case WM_RBUTTONUP: key = VK_RBUTTON; break;
                        case WM_MBUTTONDOWN: case WM_MBUTTONDBLCLK: key = VK_MBUTTON; down = true; break;
                        case WM_MBUTTONUP: key = VK_MBUTTON; break;
                        case WM_XBUTTONDOWN: case WM_XBUTTONDBLCLK:
                            key = HIWORD(message.wParam) == XBUTTON1 ? VK_XBUTTON1 : VK_XBUTTON2; down = true; break;
                        case WM_XBUTTONUP: key = HIWORD(message.wParam) == XBUTTON1 ? VK_XBUTTON1 : VK_XBUTTON2; break;
                        }
                        if (key >= 0 && key < max_keys)
                        {
                            const auto now = static_cast<DWORD>(GetTickCount64());
                            // Ignore messages queued before focus/activation or delayed by a stall.
                            if (now - message.time > 250 || message.time - source->baseline > 0x7fffffffUL)
                            {
                                source->focused = false;
                                source->pending.clear();
                            }
                            else
                            {
                                const bool edge = down && !source->down[key] && !repeat;
                                source->down[key] = down;
                                if (edge && source->allowed && source->subscribed[key])
                                {
                                    ModifierKeys modifiers{};
                                    // This runs on the message's own thread: GetKeyState reflects
                                    // queue-time modifiers, even if the physical tap is already up.
                                    if ((GetKeyState(VK_SHIFT) & 0x8000) != 0) modifiers |= ModifierKey::SHIFT;
                                    if ((GetKeyState(VK_CONTROL) & 0x8000) != 0) modifiers |= ModifierKey::CONTROL;
                                    if ((GetKeyState(VK_MENU) & 0x8000) != 0) modifiers |= ModifierKey::ALT;
                                    if (source->pending.size() < 64)
                                        source->pending.push_back({InputEvent{static_cast<Key>(key), modifiers}, message.time});
                                    else
                                    {
                                        source->focused = false;
                                        source->pending.clear();
                                    }
                                }
                            }
                        }
                    }
                }
            }
            return CallNextHookEx(nullptr, code, removed, value);
        }

        auto attach_window_messages(HWND window) -> std::shared_ptr<Win32WindowMessages>
        {
            DWORD pid{};
            const auto thread = GetWindowThreadProcessId(window, &pid);
            if (!thread || pid != GetCurrentProcessId()) return {};
            auto source = std::make_shared<Win32WindowMessages>();
            source->pending.reserve(64); // No queue allocation from the game-window callback.
            source->window = window; source->thread = thread;
            {
                std::lock_guard lock(message_sources_mutex);
                if (!message_sources[thread].expired()) return {};
                message_sources[thread] = source;
            }
            source->hook = SetWindowsHookExW(WH_GETMESSAGE, message_hook, nullptr, thread);
            if (!source->hook)
            {
                std::lock_guard lock(message_sources_mutex);
                message_sources.erase(thread);
                return {};
            }
            return source;
        }
    }

    auto Win32AsyncInputSource::release_window_messages() -> void
    {
        auto source = std::move(m_window_messages);
        if (!source) return;
        {
            std::lock_guard lock(source->mutex);
            source->active = false; source->pending.clear();
        }
        if (source->hook) UnhookWindowsHookEx(source->hook);
        std::lock_guard lock(message_sources_mutex);
        const auto found = message_sources.find(source->thread);
        if (found != message_sources.end() && found->second.lock() == source) message_sources.erase(found);
    }

    Win32AsyncInputSource::~Win32AsyncInputSource() { release_window_messages(); }

    auto Win32AsyncInputSource::is_program_focused() -> bool
    {
        HWND hwnd = GetForegroundWindow();
        if (!hwnd) return false;
        DWORD foreground_process = 0;
        GetWindowThreadProcessId(hwnd, &foreground_process);
        if (foreground_process != GetCurrentProcessId()) return false;
        wchar_t current_window_class_name[MAX_PATH];
        if (!GetClassNameW(hwnd, current_window_class_name, MAX_PATH)) return false;
        for (const auto& active_window_class : m_active_window_classes)
        {
            if (wcscmp(current_window_class_name, active_window_class) == 0)
            {
                return true;
            }
            // Sandboxie may expose the registered research namespace instead
            // of the original Unreal class. Keep the foreground-process check
            // above and allow only this exact, observed research window class.
            if (wcscmp(active_window_class, L"UnrealWindow") == 0 &&
                wcscmp(current_window_class_name, L"Sandbox:PBZSteamLab:UnrealWindow") == 0)
            {
                return true;
            }
        }
        return false;
    }

    std::vector<InputEvent>& Win32AsyncInputSource::process_event(Handler* handler)
    {
        m_input_events.clear();

        if (!is_program_focused())
        {
            m_was_focused = false;
            m_message_attempted = false;
            if (m_window_messages)
            {
                std::lock_guard lock(m_window_messages->mutex);
                m_window_messages->focused = false; m_window_messages->pending.clear();
            }
            return m_input_events;
        }

        if (!m_activated)
        {
            return m_input_events;
        }

        const auto window = GetForegroundWindow();
        if (m_window_messages && m_window_messages->window != window)
        {
            release_window_messages(); m_message_attempted = false; m_was_focused = false;
        }
        if (!m_window_messages && !m_message_attempted)
        {
            m_message_attempted = true; m_window_messages = attach_window_messages(window);
        }
        if (m_window_messages)
        {
            auto& source = *m_window_messages;
            std::lock_guard lock(source.mutex);
            source.subscribed = handler->get_subscribed_keys();
            source.allowed = handler->get_allow_input();
            const auto now = static_cast<DWORD>(GetTickCount64());
            if (!m_was_focused || !source.focused)
            {
                source.pending.clear(); source.baseline = now;
                for (int key = 0; key < max_keys; ++key) source.down[key] = (GetAsyncKeyState(key) & 0x8000) != 0;
                source.focused = true; m_was_focused = true;
                return m_input_events;
            }
            if (source.allowed)
                for (const auto& press : source.pending)
                    if (source.subscribed[press.event.key] && now - press.at <= 250) m_input_events.push_back(press.event);
            source.pending.clear();
            return m_input_events;
        }

        // The low bit is historical desktop activity, not a currently held key.
        // On focus return, seed held keys so switching windows cannot cast a skill.
        if (!m_was_focused)
        {
            for (int key = 0; key < max_keys; ++key)
            {
                m_key_down[key] = (GetAsyncKeyState(key) & 0x8000) != 0;
            }
            m_was_focused = true;
            return m_input_events;
        }

        // Per-key edges already debounce held keys. A global one-frame barrier
        // swallowed a different key (including exit) if no idle sample intervened.
        const bool skip_this_frame = !handler->get_allow_input();

        // Check if any modifier keys are down
        ModifierKeys modifier_keys{};
        for (auto& [modifier_key, key_is_down] : m_modifier_keys_down)
        {
            if ((GetAsyncKeyState(modifier_key) & 0x8000) != 0)
            {
                modifier_keys |= modifier_key;
                key_is_down = true;
            }
            else
            {
                key_is_down = false;
            }
        }

        auto& subscribed_keys = handler->get_subscribed_keys();

        for (int key = 0; key < max_keys; ++key)
        {
            if (subscribed_keys[key])
            {
                const bool keyed = (GetAsyncKeyState(key) & 0x8000) != 0;
                if (keyed && !m_key_down[key])
                {
                    m_key_down[key] = true;
                    m_input_events.emplace_back(InputEvent{static_cast<Key>(key), modifier_keys});
                }
                else if (!keyed && m_key_down[key])
                {
                    m_key_down[key] = false;
                }
            }
        }

        if (skip_this_frame)
        {
            m_input_events.clear();
        }
        return m_input_events;
    }

} // namespace RC::Input
