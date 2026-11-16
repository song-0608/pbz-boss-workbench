"""Exact patches applied only to a disposable copy of the pinned native source."""

PATCHES = (
    ('native/relay.hpp',
     '    double seconds = 0;            // 0 = for the life of the game\n',
     '    double seconds = 0;            // 0 = for the life of the game\n'
     '    bool bwb_research = false;\n'
     '    std::string bwb_secret;\n'
     '    double bwb_expires = 0;\n'),
    ('native/relay.hpp',
     '        std::unique_ptr<Link> link;\n        if (o.transport == "steam")',
     '        // Recheck the actual settings consumed by this run, before any socket opens.\n'
     '        if (o.bwb_research) {\n'
     '            const auto hex64 = [](const std::string& s) {\n'
     '                return s.size()==64 && std::all_of(s.begin(),s.end(),[](unsigned char c){\n'
     '                    return (c>=\'0\' && c<=\'9\') || (c>=\'a\' && c<=\'f\');\n'
     '                });\n'
     '            };\n'
     '            const auto expected = o.role=="host" ? "host" : "guest";\n'
     '            if (o.transport!="udp" || (o.role!="host" && o.role!="client")\n'
     '                || !o.this_pc_only || o.allow_any || party_size(ini)!=2\n'
     '                || ini["partysize"]!="2" || lower(ini["thispconly"])!="on"\n'
     '                || lower(ini["allowanyaddress"])!="off" || lower(ini["role"])!=expected\n'
     '                || ini["port"]!=std::to_string(o.port) || !signed_packets\n'
     '                || !hex64(secret) || secret!=o.bwb_secret\n'
     '                || (o.role=="client" && (o.peer!="127.0.0.1" || ini["hostaddress"]!="127.0.0.1"))\n'
     '                || !std::isfinite(o.bwb_expires) || o.bwb_expires<=std::time(nullptr))\n'
     '                throw std::runtime_error("research relay settings changed or expired");\n'
     '        }\n'
     '        std::unique_ptr<Link> link;\n        if (o.transport == "steam")'),
    ('native/relay.hpp',
     '                relay.tick(now);\n',
     '                if (o.bwb_research && std::time(nullptr)>=o.bwb_expires) break;\n'
     '                relay.tick(now);\n'),
)


def patched(name, data):
    text = data.decode('utf-8')
    for filename, before, after in PATCHES:
        if filename == name:
            if '\r\n' in text:
                before, after = before.replace('\n', '\r\n'), after.replace('\n', '\r\n')
            if text.count(before) != 1:
                raise ValueError('Pinned native patch context drift: ' + filename)
            text = text.replace(before, after, 1)
    return text.encode('utf-8')
