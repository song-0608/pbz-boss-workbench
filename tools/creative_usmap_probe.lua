-- One native metadata dump, without gameplay changes or recurring callbacks.
print("PBZ_CREATIVE_USMAP:READY\n")
local attempted = false
ExecuteWithDelay(3000, function()
    ExecuteInGameThread(function()
        if attempted then return end
        attempted = true
        print("PBZ_CREATIVE_USMAP:ATTEMPT=1\n")
        if type(DumpUSMAP) ~= "function" then
            print("PBZ_CREATIVE_USMAP:FAILED=native DumpUSMAP unavailable\n")
            return
        end
        local ok, reason = pcall(function() DumpUSMAP(false) end)
        if ok then
            print("PBZ_CREATIVE_USMAP:RETURNED=true\n")
        else
            print("PBZ_CREATIVE_USMAP:FAILED=" .. tostring(reason) .. "\n")
        end
    end)
end)
