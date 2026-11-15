-- 用途：真实Calls身份检查与World退休逻辑一起执行，覆盖存活组件、地址复用、读取失败和旧World仍存活。
local root=assert(arg[1]);package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local Boundary=require('world_boundary');local Calls=require('ue_calls')
local registry,serial={},100
local function object(name)
    serial=serial+1;local o={alive=true,name=name,address=serial}
    function o:IsValid()return true end
    function o:GetAddress()return self.address end
    function o:GetFullName()return 'Object '..self.name end
    function o:GetClass()return{GetFullName=function()return'Class /Fixture.Type'end}end
    function o:GetWorld()return registry['/World']end
    registry[name]=o;return o
end
local calls=Calls.new({find_exact=function(p)return registry[p]end,usable=function(o)return o.alive end})
local world,pc,boss,component=object('/World'),object('/PC'),object('/Boss'),object('/Component')
local receipt={world=calls:reference(world),player_controller=calls:reference(pc),boss=calls:reference(boss),
    camera_rig={component=calls:reference(component)}}
assert(Boundary.inspect(calls,receipt)=='same')
local original_get_world=pc.GetWorld
function pc:GetWorld()return nil end
assert(Boundary.inspect(calls,receipt)=='pending')
pc.GetWorld=original_get_world
pc.alive=false;assert(Boundary.inspect(calls,receipt)=='pending')
world.alive=false;boss.alive=false;assert(Boundary.inspect(calls,receipt)=='pending')
component.alive=false;assert(Boundary.inspect(calls,receipt)=='retired')
component.alive=true;component.address=999
assert(not pcall(Boundary.inspect,calls,receipt))
component.address=receipt.camera_rig.component.address
function component:IsValid()error('unreadable')end
assert(not pcall(Boundary.inspect,calls,receipt))
print('PASS world boundary disposal, surviving component, identity reuse and unreadable validity')
local Session=require('session');local Driver=require('input_driver')
local b={clock=100,status='same',restores=0,inputs=0}
function b:context()return{isolated=true,offline=true,exe_sha256='fixture',world_id='old',boss_available=true}end
function b:capture()return{}end
function b:take_control()return true end
function b:verify_control()return true end
function b:can_start_skill()return true end
function b:start_skill()return'token'end
function b:is_skill_finished()return false end
function b:cancel_skills()error('must not cancel old-world ability')end
function b:restore()self.restores=self.restores+1;error('must not restore old-world participants')end
function b:verify_restored()return true end
function b:world_boundary()return self.status,'surviving world',self.clock end
local s=Session.new(b,{expected_exe_sha256='fixture',skills={one={id='one',verified=true}}})
assert(s:enter());assert(s:skill('one'));b.status='pending'
assert(not s:skill('one'));assert(not s:poll());assert(s.state=='TRANSITIONING'and s.receipt and s.current_skill)
local d=Driver.new(s,{read_input=function()b.inputs=b.inputs+1;error('input must be suspended')end})
assert(not d:step());assert(b.inputs==0 and b.restores==0)
b.status='retired';assert(not d:step());assert(s.state=='OFF'and not s.receipt and not s.current_skill and b.restores==0)
assert(s:enter());b.status='pending';assert(not s:poll());b.clock=116;assert(not s:poll());assert(s.state=='FAULTED'and s.receipt)
print('PASS transition suspends input, preserves pending receipt, retires disposed state and fails on timeout')
local old=object('/ReloadWorld');local oldref=calls:reference(old)
local newer=object('/ReloadWorld');local enumerated={old,newer}
local exact_calls=Calls.new({find_exact=function(p)return registry[p]end,
    find_all=function()return enumerated end,usable=function(o)return o.alive end})
assert(not pcall(exact_calls.optional,exact_calls,oldref))
assert(exact_calls:retirement_optional(oldref)==old)
old.alive=false;assert(not exact_calls:retirement_optional(oldref))
enumerated={newer};assert(not exact_calls:retirement_optional(oldref))
old.alive=true;old.name='/Reused';enumerated={old,newer}
assert(exact_calls:retirement_optional(oldref).retirement_ambiguous==true)
old.alive=false;assert(not exact_calls:retirement_optional(oldref))
old.alive=true;registry['/ReloadWorld']=nil;assert(exact_calls:retirement_optional(oldref).retirement_ambiguous==true)
print('PASS same-name new World independently enumerates old identity without accepting replacement')
