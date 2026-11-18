-- One metadata batch at a time. Never spawns, possesses, grants or activates.
local stopped,finished,current,pending=false,false,0,false
local deadline=os.time()+budget_seconds
local raw_print,raw_load,raw_dispatch=print,LoadAsset,ExecuteInGameThread
local function emit(key,value)raw_print('PBZ_FULL_CATALOG:'..key..'='..value..'\n')end
local function stop(reason)
    if not stopped then stopped=true;emit('STOP',reason)end
    return true
end
emit('START',fingerprint)
LoopAsync(100,function()
    if stopped or finished then return true end
    if os.time()>=deadline then return stop('outer metadata deadline')end
    if pending then return false end
    if current==#batches then finished=true;emit('END',fingerprint);return true end
    current=current+1;pending=true
    local own=current;local batch=batches[own];local closed=false
    local env=setmetatable({}, {__index=_G})
    env.print=function(value)
        if stopped or own~=current then return end
        raw_print(value)
        if value:find('PBZ_ADAPTER_META:END='..batch.key,1,true)then
            if closed then return stop('duplicate batch completion')end
            closed=true;pending=false
        elseif value:find('PBZ_ADAPTER_META:STOP=',1,true)then stop('inner metadata deadline')end
    end
    env.ExecuteInGameThread=function(callback)
        raw_dispatch(function()
            if stopped or closed or own~=current or os.time()>=deadline then return end
            callback()
        end)
    end
    env.LoadAsset=function(path)
        assert(not stopped and not closed and own==current and os.time()<deadline,'metadata batch expired')
        return raw_load(path)
    end
    local chunk,why=load(batch.source,'frozen-catalog-'..batch.key,'t',env)
    if not chunk then return stop('metadata compilation failed: '..tostring(why))end
    local ok,reason=pcall(chunk)
    if not ok then return stop('metadata launch failed: '..tostring(reason))end
    return false
end)
