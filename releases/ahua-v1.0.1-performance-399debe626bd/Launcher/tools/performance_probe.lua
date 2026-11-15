-- Developer-only, read-only timing wrappers; no control policy or game state changes.
local clock=os.clock
local bucket={}
local frames,total,maximum=0,0,0
local started=clock()
local function wrap(owner,key,label)
    local original=owner[key]
    if type(original)~='function'then return end
    owner[key]=function(...)
        local at=clock()
        local result=table.pack(pcall(original,...))
        local row=bucket[label]or{count=0,seconds=0}
        row.count=row.count+1;row.seconds=row.seconds+clock()-at;bucket[label]=row
        if not result[1]then error(result[2],0)end
        return table.unpack(result,2,result.n)
    end
end
local Bridge=require('control_bridge')
local create_bridge=Bridge.new
Bridge.new=function(api,...)
    wrap(api,'find_exact','find_exact');wrap(api,'find_all','find_all');wrap(api,'usable','usable')
    return create_bridge(api,...)
end
for _,key in ipairs({'context','world_boundary','control_health','maintain_control','verify_control','update_camera','move','look'})do
    wrap(Bridge,key,'bridge.'..key)
end
local Runtime=require('runtime')
local create_runtime=Runtime.new
Runtime.new=function(bridge,config,host)
    wrap(host,'read_input','read_input');wrap(host,'status','status');wrap(host,'inspect_idle_world','idle_world')
    local original=host.every_frame
    local runtime
    host.every_frame=function(fn)
        return original(function(...)
            local at=clock()
            local result=table.pack(pcall(fn,...))
            local elapsed=clock()-at
            frames=frames+1;total=total+elapsed;maximum=math.max(maximum,elapsed)
            local now=clock()
            if now-started>=5 then
                print(string.format('PBZ_PERF:WINDOW=state=%s|wall=%.6f|frames=%d|callback_ms=%.6f|max_ms=%.6f|at=%d\n',
                    runtime and runtime.session.state or'UNKNOWN',now-started,frames,1000*total/frames,1000*maximum,os.time()))
                local keys={};for key in pairs(bucket)do keys[#keys+1]=key end;table.sort(keys)
                for _,key in ipairs(keys)do local row=bucket[key]
                    print(string.format('PBZ_PERF:COST=%s|calls=%d|ms=%.6f\n',key,row.count,1000*row.seconds))
                end
                bucket={};frames,total,maximum=0,0,0;started=clock()
            end
            if not result[1]then error(result[2],0)end
            return table.unpack(result,2,result.n)
        end)
    end
    runtime=create_runtime(bridge,config,host)
    return runtime
end
print('PBZ_PERF:ENABLED=read-only Windows CRT elapsed-clock probe; method costs inclusive\n')
