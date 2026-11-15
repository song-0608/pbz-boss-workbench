-- 用途：核对真实调用层的技能实例取消，不把假对象测试当作游戏内技能验收。
local root=assert(arg[1],"project directory required")
package.path=root.."/mod/PBZBossControl/Scripts/?.lua;"..package.path
local Calls=require("ue_calls")
local total=0
local function test(name,fn)
    local ok,why=pcall(fn);assert(ok,name..": "..tostring(why));total=total+1;print("PASS "..name)
end
local function fixture()
    local f={calls=0};local cls={GetFullName=function()return "Class /Fixture/Skill.Skill_C"end}
    local function object(name)
        return {IsValid=function()return true end,GetClass=function()return cls end,
            GetFullName=function()return "Skill "..name end}
    end
    f.cdo=object("/Fixture/Skill.Default__Skill_C")
    f.instance=object("/Fixture/Map:PersistentLevel.Skill_1")
    f.instance.bIsActive=true;f.instance.bIsCancelable=true
    local function array(items)
        items.GetArrayNum=function()return #items end;return items
    end
    f.spec={Ability=f.cdo,ActiveCount=1,NonReplicatedInstances=array({f.instance}),ReplicatedInstances=array({})}
    function f.instance:K2_CancelAbility()f.calls=f.calls+1;self.bIsActive=false;f.spec.ActiveCount=0 end
    f.binding={cancel_binding_verified=true,cancel_function="K2_CancelAbility",active_count_field="ActiveCount"}
    f.native=Calls.new({find_exact=function()end})
    return f
end
test("active cancellable instance reaches native cancel",function()
    local f=fixture();assert(f.native:cancel(f.spec,f.binding));assert(f.calls==1 and f.spec.ActiveCount==0)
end)
test("unverified cancel binding cannot call the instance",function()
    local f=fixture();f.binding.cancel_binding_verified=false
    assert(not pcall(f.native.cancel,f.native,f.spec,f.binding));assert(f.calls==0)
end)
test("uncancellable skill remains active and reports failure",function()
    local f=fixture();f.instance.bIsCancelable=false;assert(not f.native:cancel(f.spec,f.binding));assert(f.calls==0)
end)
test("class defaults are never treated as active skill instances",function()
    local f=fixture();f.cdo.bIsActive=true;f.cdo.bIsCancelable=true
    f.cdo.K2_CancelAbility=function()error("CDO must not be cancelled")end
    f.spec.NonReplicatedInstances[1]=f.cdo
    assert(not f.native:cancel(f.spec,f.binding));assert(f.calls==0)
end)
test("cancel must clear the actual activity count",function()
    local f=fixture();f.instance.K2_CancelAbility=function()f.calls=f.calls+1 end
    assert(not f.native:cancel(f.spec,f.binding));assert(f.calls==1 and f.spec.ActiveCount==1)
end)
test("unbounded instance arrays are rejected before native calls",function()
    local f=fixture();f.spec.NonReplicatedInstances.GetArrayNum=function()return 1000000 end
    assert(not pcall(f.native.cancel,f.native,f.spec,f.binding));assert(f.calls==0)
end)
test('cancel diagnostic distinguishes blocked instance from no-match',function()
    local f=fixture();local rows={};f.native.api.cancel_trace=function(row)rows[#rows+1]=row end
    f.instance.bIsCancelable=false;assert(not f.native:cancel(f.spec,f.binding))
    assert(rows[1].reason=='instance_not_cancelable'and rows[1].invoked==0)
    rows={};f.instance.bIsActive=false;assert(not f.native:cancel(f.spec,f.binding))
    assert(rows[1].reason=='no_matching_active_instance')
end)
test('failing diagnostic cannot prevent real cancellation',function()
    local f=fixture();f.native.api.cancel_trace=function()error('broken observer')end
    assert(f.native:cancel(f.spec,f.binding));assert(f.calls==1)
end)
test('optional resolution distinguishes disposal from replacement and unreadable validity',function()
    local reference={name='Object /Fixture.Owner',address=1048,class='Class /Fixture.Owner_C'}
    local object={IsValid=function()return true end,GetFullName=function()return reference.name end,
        GetAddress=function()return 1048 end,GetClass=function()return{GetFullName=function()return reference.class end}end}
    local api={find_exact=function()return object end,usable=function()return true end}
    local calls=Calls.new(api)
    assert(calls:optional(reference)==object)
    api.usable=function()return false end;assert(calls:optional(reference)==nil)
    object.GetAddress=function()return 2000 end
    assert(not pcall(calls.optional,calls,reference),'engine-invalid replacement must still fail identity check')
    object.GetAddress=function()return 1048 end
    api.usable=function()return nil end;assert(not pcall(calls.optional,calls,reference))
    api.usable=function()error('validity query failed')end;assert(not pcall(calls.optional,calls,reference))
    object.IsValid=function()return false end;assert(calls:optional(reference)==nil)
    api.find_exact=function()return nil end;assert(calls:optional(reference)==nil)
    assert(not pcall(calls.resolve,calls,reference))
end)
print("Native call fixtures: "..total.." passed; cancellation not runtime verified.")
