local root=assert(arg[1]);package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local Trial=require('owned_disposal_trial')
local function fixture()
    local f={events={},active=1,destroys=0}
    local receipt={boss={}};local cls={GetFullName=function()return'BlueprintGeneratedClass /Fixture.Skill08'end}
    local instance={bIsActive=true,GetClass=function()return cls end,GetFullName=function()return'FixtureSkill08 /Game/Owned.Skill08'end}
    local array={instance,GetArrayNum=function(a)return#a end}
    local empty={GetArrayNum=function()return 0 end}
    local spec={Ability=instance,NonReplicatedInstances=array,ReplicatedInstances=empty}
    f.session={state='ACTIVE',receipt=receipt,current_skill='token'}
    f.bridge={tokens={token={id='skill_08',receipt=receipt}}}
    function f.bridge:definition()return{class_path='/Fixture.Skill08'}end
    function f.bridge:spec()assert(f.destroys==0,'post-disposal Spec access');return spec,f.active end
    f.boss={GetFullName=function()return'FixtureBoss /Game/Owned.Boss'end,GetAddress=function()return 42 end}
    function f.boss:K2_DestroyActor()f.destroys=f.destroys+1 end
    f.owned={};f.calls={resolve=function(_,ref)if ref==receipt.boss or ref==f.owned then return f.boss end end,same=function(_,a,b)return a==b end}
    f.lifecycle={usable=function(_,object)return object~=f.boss or f.destroys==0 end}
    f.log=function(k,v)f.events[#f.events+1]=k..':'..tostring(v)end
    f.run=function()return Trial.run(f.session,f.bridge,f.calls,f.owned,f.lifecycle,f.log)end
    f.instances=array
    return f
end
local f=fixture();assert(f.run()and f.destroys==1 and #f.events==3)
assert(f.events[1]:find('OWNED_DISPOSAL_ACTIVE_INSTANCE:skill_08|active=1',1,true)==1)
assert(f.events[3]=='OWNED_DISPOSAL_ENGINE_UNUSABLE:true')
f=fixture();f.active=0;assert(not pcall(f.run)and f.destroys==0)
f=fixture();f.instances[2]=f.instances[1];assert(not pcall(f.run)and f.destroys==0)
f=fixture();f.instances[1].bIsActive=false;assert(not pcall(f.run)and f.destroys==0)
f=fixture();f.owned={unrelated=true};local real=f.calls.resolve;f.calls.resolve=function(self,ref)if ref==f.owned then return{}end;return real(self,ref)end
assert(not pcall(f.run)and f.destroys==0)
print('PASS exact in-flight disposal, no post-disposal Spec access, inactive, duplicate, missing instance and foreign owner')
