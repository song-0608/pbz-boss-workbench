// Standalone exercise of the same bootstrap and mailbox used by main.dll.
// This executable never loads UE4SS or starts the game.
#include "phantom_boss_native_bootstrap.cpp"
#include <thread>

int wmain(int argc,wchar_t** argv) {
    if (argc!=3) return 2;
    directory=argv[2];
    try {
        auto options=validate_request(directory+L"\\net_start.txt");
        const std::wstring mode=argv[1];
        if (mode==L"validate") return 0;
        if (mode==L"reload") {
            relay::write_atomic(options.ini,relay::read_text(directory+L"\\replacement.ini"));
            run_relay(options);
            return GetFileAttributesW((directory+L"\\relay_error.txt").c_str())!=INVALID_FILE_ATTRIBUTES ? 0 : 3;
        }
        if (mode!=L"exchange") return 2;
        const bool host=options.role=="host";
        const std::string mine=host ? "BWB_NATIVE_HOST" : "BWB_NATIVE_GUEST";
        const std::string other=host ? "BWB_NATIVE_GUEST" : "BWB_NATIVE_HOST";
        const float expected=host ? 202.0f : 101.0f;
        std::atomic<bool> done=false;
        bool event_seen=false, sample_seen=false, connected=false;
        std::thread network([&]{run_relay(options);done=true;});
        const double begin=relay::monotonic();
        double next_event=begin;
        while (!done && relay::monotonic()-begin<15) {
            relay::Sample sample{};
            sample.ms=static_cast<uint32_t>(relay::clock_ms());
            sample.x=host ? 101.0f : 202.0f;sample.hp=100;sample.max_hp=100;
            sample.map=0xB0B;sample.flags=relay::FLAG_GROUNDED;
            relay::mail.post_sample(sample);
            if (relay::monotonic()>=next_event) {
                relay::mail.post_sure(mine);next_event=relay::monotonic()+0.2;
            }
            double silence=0,delay=0;
            relay::Sample partner{};
            if (relay::mail.partner(relay::clock_ms(),partner,silence,delay)
                && partner.x==expected && partner.map==0xB0B && silence<500) sample_seen=true;
            const auto status=relay::mail.status();
            if (status.find(" connected=yes ")!=std::string::npos
                && status.find(" auth=on")!=std::string::npos) connected=true;
            if (relay::mail.take_events(relay::clock_ms()).find(other)!=std::string::npos) event_seen=true;
            Sleep(10);
        }
        relay::mail.ask_stop();
        network.join();
        const auto status=relay::mail.status();
        const bool reset=relay::mail.take_events(relay::clock_ms()).empty()
            && status.find("connected=no stopped=yes")!=std::string::npos;
        char result[128];
        std::snprintf(result,sizeof(result),"connected=%d sample=%d event=%d reset=%d\n",connected,sample_seen,event_seen,reset);
        relay::write_atomic(directory+L"\\bootstrap_result.txt",result);
        std::fputs(result,stdout);
        return connected && sample_seen && event_seen && reset ? 0 : 4;
    } catch (const std::exception& error) {
        std::fprintf(stderr,"rejected: %s\n",error.what());
        return 5;
    }
}
