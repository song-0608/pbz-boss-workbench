#pragma once

#include <vector>
#include <unordered_map>
#include <memory>

#include <Input/KeyDef.hpp>
#include <Input/Common.hpp>
#include <Input/PlatformInputSource.hpp>

namespace RC::Input
{
    struct Win32WindowMessages;
    class Win32AsyncInputSource : public PlatformInputSource
    {
      private:
        std::vector<const wchar_t*> m_active_window_classes{};
        std::unordered_map<ModifierKey, bool> m_modifier_keys_down{};
        bool m_activated{false};
        bool m_was_focused{false};
        std::array<bool, max_keys> m_key_down{};
        std::shared_ptr<Win32WindowMessages> m_window_messages;
        bool m_message_attempted{false};
        auto release_window_messages() -> void;

      private:
        /// SAFETY: Only update and return m_input_events
        /// in the process_event function
        std::vector<InputEvent> m_input_events{};

      public:
        template <typename... WindowClasses>
        explicit Win32AsyncInputSource(WindowClasses... window_classes)
        {
            static_assert(std::conjunction<std::is_same<const wchar_t*, WindowClasses>...>::value, "WindowClasses must be of type const wchar_t*");

            m_modifier_keys_down.emplace(ModifierKey::SHIFT, false);
            m_modifier_keys_down.emplace(ModifierKey::CONTROL, false);
            m_modifier_keys_down.emplace(ModifierKey::ALT, false);

            register_window_classes(window_classes...);
        }

      private:
        template <typename WindowClass>
        auto register_window_classes(WindowClass window_class) -> void
        {
            m_active_window_classes.emplace_back(window_class);
        }

        template <typename WindowClass, typename... WindowClasses>
        auto register_window_classes(WindowClass window_class, WindowClasses... window_classes) -> void
        {
            m_active_window_classes.emplace_back(window_class);
            register_window_classes(window_classes...);
        }

        auto are_modifier_keys_down(const std::vector<ModifierKey>&) -> bool;
        auto is_program_focused() -> bool;

      public:
        bool is_available() override
        {
            return true;
        };

        bool activate() override
        {
            release_window_messages();
            m_message_attempted = false;
            m_key_down.fill(false);
            m_was_focused = false;
            return m_activated = true;
        };

        bool deactivate() override
        {
            m_activated = false;
            release_window_messages();
            return true;
        };

        std::vector<InputEvent>& process_event(Handler* handler) override;
        ~Win32AsyncInputSource() override;
        int source_priority() override
        {
            return 0;
        }

        const char* get_name() override
        {
            return "Win32Async";
        }
    };
}; // namespace RC::Input
