-- 用途：为本项目实际核对的 PBZ build 26367565 解析全局对象数组。
-- 来源：本机原版程序 RVA 0x1584AA5 的三条 RIP 相对指令；可执行区唯一匹配。
-- 证据：evidence/adaptation/static-calls-patterns.json 与 latest-object-array-probe.json。
-- 原理：NumElements - ObjAvailableListEstimateCount - ObjFirstGCIndex；不使用固定运行地址。
function Register() -- 用途：交给 UE4SS 扫描，位移字节使用通配符以兼容 ASLR。
    return "8B 05 ?? ?? ?? ?? 2B 05 ?? ?? ?? ?? 2B 05 ?? ?? ?? ?? 0F 5A C0 89 05 ?? ?? ?? ??"
end

function OnMatchFound(match_address) -- 用途：只接受三条指令同时指向已验证相对布局的候选。
    local num_elements = match_address + 6 + DerefToInt32(match_address + 2)
    local available_count = match_address + 12 + DerefToInt32(match_address + 8)
    local first_gc_index = match_address + 18 + DerefToInt32(match_address + 14)
    -- 用途：确认所匹配的三个字段来自同一结构，防止仅按字节外观误认。
    if num_elements - first_gc_index ~= 0x20 then return 0 end
    if available_count - first_gc_index ~= 0x68 then return 0 end
    return first_gc_index -- 用途：ObjFirstGCIndex 位于 FUObjectArray+0，返回结构首地址。
end
