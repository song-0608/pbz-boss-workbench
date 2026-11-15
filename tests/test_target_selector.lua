-- 用途：验证敌我筛选、目标循环和失效处理；夹具不代表实机已通过。
local root=assert(arg[1]);package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local Selector=require('target_selector');local count=0
local function fixture()
    local f={}
    local function actor(name,x)
        local a={name=name,address=name,health=100,faction=2,x=x or 0,world=1}
        function a:IsValid()return not self.invalid end
        return a
    end
    f.boss=actor('boss');f.boss.faction=0;f.player=actor('player');f.player.faction=0
    f.a=actor('a',100);f.b=actor('b',200);f.rows={f.boss,f.player,f.b,f.a}
    f.calls={same=function(_,a,b)return a==b end,world=function(_,a)return{name='world',address=a.world}end,
        reference=function(_,a)return{name=a.name,address=a.address}end}
    f.selector=Selector.new(f.calls,{candidates=function()return f.rows end,health=function(a)return a.health end,
        usable=function(a)return not a.destroying end,position=function(a)return{X=a.x,Y=0,Z=0}end,relation=function(a,b)return a.faction==b.faction and 0 or 2 end})
    return f
end
local function test(name,fn)local ok,why=pcall(fn);assert(ok,name..': '..tostring(why));count=count+1;print('PASS '..name)end
test('first selection chooses nearest eligible enemy',function()local f=fixture();assert(f.selector:next(f.boss,f.player)==f.a)end)
test('cycling reaches another actor and wraps',function()local f=fixture();assert(f.selector:next(f.boss,f.player,f.a)==f.b);assert(f.selector:next(f.boss,f.player,f.b)==f.a)end)
test('one enemy is not reported as a switch',function()local f=fixture();f.b.health=0;local a,why=f.selector:next(f.boss,f.player,f.a);assert(not a and why=='no alternate hostile target')end)
test('dead and invalid objects excluded',function()local f=fixture();f.a.health=0;f.b.invalid=true;assert(not f.selector:next(f.boss,f.player))end)
test('other world and friendly objects excluded',function()local f=fixture();f.a.world=2;f.b.faction=0;assert(not f.selector:next(f.boss,f.player))end)
test('out of radius and nonfinite coordinates excluded',function()local f=fixture();f.a.x=3001;f.b.x=0/0;assert(not f.selector:next(f.boss,f.player))end)
test('nonfinite health excluded',function()local f=fixture();f.a.health=math.huge;f.b.health=0/0;assert(not f.selector:next(f.boss,f.player))end)
test('duplicates do not create false alternate target',function()local f=fixture();f.rows={f.a,f.a};assert(not f.selector:next(f.boss,f.player,f.a))end)
test('oversized candidate list is explicitly refused',function()local f=fixture();for i=1,257 do f.rows[i]=f.a end;local a,why=f.selector:next(f.boss,f.player);assert(not a and why=='target scan bound exceeded')end)
test('stale current target chooses fresh nearest',function()local f=fixture();assert(f.selector:next(f.boss,f.player,{invalid=true})==f.a)end)
test('current actor health rechecked on next scan',function()local f=fixture();f.a.health=0;assert(f.selector:next(f.boss,f.player,f.a)==f.b)end)
test('destroy requested but still valid object is excluded',function()local f=fixture();f.a.destroying=true;assert(f.a:IsValid());assert(f.selector:next(f.boss,f.player)==f.b)end)
print('Target selector fixtures passed: '..count)
test('visibility false and unreadable both reject targets',function()
    local f=fixture();f.selector.native.visible=function(_,target)return target==f.b end
    assert(f.selector:next(f.boss,f.player)==f.b)
    f.selector.native.visible=function()error('unreadable trace')end
    assert(not f.selector:next(f.boss,f.player))
end)
test('required visibility cannot silently degrade',function()
    local f=fixture();assert(not pcall(Selector.new,f.calls,f.selector.native,{require_visibility=true}))
end)
