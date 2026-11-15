-- 用途：验证pending-kill包装与GC删除包装的不同处理，防止旧地址复用后误判为活对象。
local root=assert(arg[1]);package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local Lifecycle=require('object_lifecycle')
local calls=0
local library={IsValid=function()return true end}
function library:CallFunction(_,object)calls=calls+1;return object.engine_usable==true end
library.engine_usable=true
local fn={IsValid=function()return true end}
local service=Lifecycle.new({StaticFindObject=function(path)
 return path:find('Default__',1,true)and library or fn
end},{binding_verified=true})
local alive={IsValid=function()return true end,engine_usable=true}
assert(service:usable(alive))
alive.engine_usable=false;assert(not service:usable(alive))
local stale={IsValid=function()return false end,engine_usable=true}
local before=calls;assert(not service:usable(stale)and calls==before)
assert(not service:usable(nil)and calls==before)
library.CallFunction=function()return nil end
assert(not pcall(service.usable,service,alive),'unreadable validity must not count as disposal')
print('PASS engine-invalid and GC-invalid objects rejected without calling a stale address')
