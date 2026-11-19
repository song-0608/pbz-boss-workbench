local root=assert(arg[1])
local Probe=require('player_activity_probe')
local checks,classes=0,0
local function ability(name,usable)
    return{usable=usable,GetClass=function()
        classes=classes+1
        return{GetFullName=function()return name end}
    end}
end
local function valid(a)checks=checks+1;return a and a.usable end
local specs={GetArrayNum=function(self)return #self end}
for i=1,200 do specs[i]={ActiveCount=0,Ability=ability('idle-'..i,true)}end
specs[10]={ActiveCount=1,Ability=ability('active-a',true)}
specs[20]={ActiveCount=2,Ability=ability('active-a',true)}
specs[30]={ActiveCount=1,Ability=ability('active-b',true)}
specs[40]={ActiveCount=1,Ability=ability('retired',false)}
local player={AbilitySystemComponent={ActivatableAbilities={Items=specs}}}
local function old_snapshot()
    local found={}
    for i=1,specs:GetArrayNum()do
        local s=specs[i]
        if valid(s.Ability)and s.ActiveCount>0 then found[s.Ability:GetClass():GetFullName()]=true end
    end
    return found
end
local old=old_snapshot();assert(checks==200 and classes==3)
checks,classes=0,0
local current=Probe.snapshot(player,valid)
assert(checks==4 and classes==3 and current['active-a']and current['active-b']and not current.retired)
for name in pairs(old)do assert(current[name])end
for name in pairs(current)do assert(old[name])end
-- A new activation is observed on the next call, even when array length and
-- object identity are unchanged. Retirement and deactivation are fresh too.
specs[50].ActiveCount=1
assert(Probe.snapshot(player,valid)['idle-50'])
specs[10].ActiveCount=0;specs[20].ActiveCount=0
assert(not Probe.snapshot(player,valid)['active-a'])
specs[30].Ability.usable=false
assert(not Probe.snapshot(player,valid)['active-b'])
-- Inactive UObject members must not be touched, including stale handles.
specs[60]=setmetatable({ActiveCount=0},{__index=function()error('inactive ability dereferenced')end})
assert(Probe.snapshot(player,valid)['idle-50'])
specs[50].Ability=ability('replacement',true)
assert(Probe.snapshot(player,valid).replacement)
local old_size=specs.GetArrayNum;specs.GetArrayNum=function()return 513 end
assert(not pcall(Probe.snapshot,player,valid),'oversized native arrays remain rejected')
specs.GetArrayNum=old_size
print('PASS 200-spec audit: usable queries 200 -> 4 with identical active classes; fresh per-frame activation, retirement and array bound')
