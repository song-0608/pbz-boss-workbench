-- 原生清锁定在死亡目标上提前返回时，仍精确清理本实例并严格读回。
local root=assert(arg[1]);package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local count=0
local function fixture(mode)
    local mesh={IsValid=function()return true end}
    local values={Component=mesh,SocketName='head'}
    local f={stops=0,writes=0}
    -- 反射结构是原地字段代理。整结构表赋值只遍历存在的键，nil键不能清指针。
    local slot=setmetatable({},{__index=values,__newindex=function(_,key,value)
        f.writes=f.writes+1
        if mode=='write_error'then error('injected reflected write failure')end
        if mode~='ignored'then values[key]=value end
    end})
    local component=setmetatable({StopLockTarget=function()
        f.stops=f.stops+1
        if mode=='native'then values.Component=nil;values.SocketName='None'end
    end},{__index=function(_,key)if key=='LockTarget'then return slot end end,
        __newindex=function(_,key,value)
            assert(key=='LockTarget')
            for field,item in pairs(value)do slot[field]=item end
        end})
    local native=require('ue_combat').new({FName=function(s)return s end,
        StaticFindObject=function()return{IsValid=function()return true end}end},{binding_verified=true})
    f.component=component;f.native=native;f.slot=function()return slot end
    return f
end
local function test(name,fn)local ok,why=pcall(fn);assert(ok,name..': '..tostring(why));count=count+1;print('PASS '..name)end
test('native success avoids reflected fallback',function()
    local f=fixture('native');f.native.clear_target(f.component);assert(f.stops==1 and f.writes==0)
end)
test('dead target stale component is cleared with exact empty socket',function()
    local f=fixture('stale');f.native.clear_target(f.component)
    assert(f.stops==1 and f.writes==2 and f.slot().Component==nil and f.slot().SocketName=='None')
end)

test('whole struct nil table reproduces the observed skipped pointer',function()
    local f=fixture('stale');f.component.LockTarget={Component=nil,SocketName='None'}
    assert(f.slot().Component,'nil table field must reproduce UE4SS skip semantics')
    f.native.clear_target(f.component);assert(f.slot().Component==nil)
end)
test('ignored reflected cleanup never reports success',function()
    local f=fixture('ignored');assert(not pcall(f.native.clear_target,f.component));assert(f.slot().Component)
end)
test('reflected cleanup error propagates',function()
    local f=fixture('write_error');assert(not pcall(f.native.clear_target,f.component))
end)
test('repeat cleanup leaves empty target empty',function()
    local f=fixture('stale');f.native.clear_target(f.component);f.native.clear_target(f.component)
    assert(f.stops==2 and f.writes==2)
end)
print('Native combat cleanup checks passed: '..count)
