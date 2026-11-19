local root=assert(arg[1],'project required')
package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local Defense=require('boss_defense_input')
local total=0
local function test(name,fn)fn();total=total+1;print('PASS '..name)end
local function fixture()
    local f={now=0,identity='session|world|pawn|grant',allowed=true,same_world=true,busy=false,
        native=false,accept=true,activations=0,releases=0,cancels=0}
    f.adapter={context=function()return f end,active=function()return f.native end,
        activate=function()f.activations=f.activations+1;if f.accept then f.native=true end;return f.accept end,
        release=function()f.releases=f.releases+1;return true end,
        cancel=function()f.cancels=f.cancels+1;f.native=false;return true end}
    f.d=Defense.new(f.adapter);return f
end
local function sample(f,down,allowed)return f.d:step({down=down,allowed=allowed~=false})end
local function arm(f)assert(sample(f,false));assert(sample(f,true))end
test('takeover with held button requires release before native activation',function()
    local f=fixture();assert(not sample(f,true));assert(not sample(f,true));assert(f.activations==0)
    arm(f);assert(f.activations==1 and f.d:blocks_action())
end)
test('holding never restarts an active native stance and release cancels only owned stance',function()
    local f=fixture();arm(f)
    for i=1,30 do f.now=i/60;assert(sample(f,true))end
    assert(f.activations==1);assert(sample(f,false))
    assert(f.releases==1 and f.cancels==1 and not f.d:blocks_action())
    assert(sample(f,false));assert(f.releases==1)
end)
test('naturally completed NPC counter re-arms with bounded native checks',function()
    local f=fixture();arm(f);f.native=false;f.now=.02;assert(sample(f,true));assert(f.activations==1)
    f.now=.11;assert(sample(f,true));assert(f.activations==2)
    f.native=false;f.accept=false;f.now=.22;assert(not sample(f,true));assert(f.activations==3)
    for i=1,5 do f.now=.22+i*.01;sample(f,true)end
    assert(f.activations==3)
end)
test('existing stance is never adopted or cancelled',function()
    local f=fixture();f.native=true;arm(f);assert(sample(f,false))
    assert(f.activations==0 and f.releases==0 and f.cancels==0 and f.native)
end)
test('focus or menu suspension releases once and requires a fresh key cycle',function()
    local f=fixture();arm(f);assert(not sample(f,true,false));assert(not f.native)
    assert(not sample(f,true));assert(f.activations==1);arm(f);assert(f.activations==2)
end)
test('combat action blocks defense activation while preserving the hold',function()
    local f=fixture();f.busy=true;assert(sample(f,false));assert(not sample(f,true));assert(f.activations==0)
    f.busy=false;assert(sample(f,true));assert(f.activations==1)
end)
test('world and participant changes reject old native cleanup',function()
    for _,field in ipairs({'same_world','identity'})do
        local f=fixture();arm(f);f[field]=field=='identity'and'new world pawn'or false
        assert(not pcall(sample,f,false));assert(f.releases==0 and f.cancels==0 and f.d.owned)
    end
end)
test('activation exception preserves cleanup responsibility',function()
    local f=fixture();sample(f,false)
    f.adapter.activate=function()f.native=true;error('after mutation')end
    assert(not pcall(sample,f,true));assert(f.d.owned)
    assert(f.d:release('activation failed'));assert(f.cancels==1 and not f.d.owned)
end)
test('failed cancellation retains ownership until verified cleanup',function()
    local f=fixture();arm(f);f.adapter.cancel=function()return false end
    assert(not pcall(sample,f,false));assert(f.d.owned and f.d.release_pending)
    f.adapter.cancel=function()f.native=false;return true end
    assert(sample(f,false));assert(f.releases==1 and not f.d.owned)
end)
test('failed release notification is retried before native cancellation',function()
    local f=fixture();arm(f);local tries=0
    f.adapter.release=function()tries=tries+1;return tries>1 end
    assert(not pcall(sample,f,false));assert(f.d.owned and f.cancels==0)
    assert(sample(f,false));assert(tries==2 and f.cancels==1)
end)
test('invalid activity or backwards clock cannot authorize activation',function()
    local f=fixture();sample(f,false);f.adapter.active=function()return 0 end
    assert(not pcall(sample,f,true));assert(f.activations==0)
    f=fixture();f.now=2;sample(f,false);f.now=1
    assert(not pcall(sample,f,true));assert(f.activations==0)
end)
print('Native defense input fixtures: '..total..'; gameplay defense remains unverified')
