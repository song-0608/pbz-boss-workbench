-- 用途：死亡验收不能用按键或旧技能令牌代替真实活动回读；本测试不会调用游戏。
local root=assert(arg[1]);package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local Guard=require('death_trial_guard');local count=0
local function fixture()
    local receipt={};local f={active=1,reads=0}
    f.session={state='ACTIVE',receipt=receipt,current_skill='token'}
    f.bridge={tokens={token={receipt=receipt,id='skill_08'}}}
    function f.bridge:definition(id)assert(id=='skill_08');return{id=id}end
    function f.bridge:spec(r,d)assert(r==receipt and d.id=='skill_08');f.reads=f.reads+1;return{},f.active end
    return f
end
local function test(name,fn)local ok,why=pcall(fn);assert(ok,name..': '..tostring(why));count=count+1;print('PASS '..name)end
test('explicit active trial requires real positive activity',function()
    local f=fixture();local id,active=Guard.activity(f.session,f.bridge,true)
    assert(id=='skill_08'and active==1 and f.reads==1)
end)
test('idle default refuses active skill and accepts idle receipt',function()
    local f=fixture();assert(not pcall(Guard.activity,f.session,f.bridge,false));assert(f.reads==0)
    f.session.current_skill=nil;assert(Guard.activity(f.session,f.bridge,false)==nil)
end)
test('finished unreadable and unbounded activity cannot authorize death',function()
    for _,value in ipairs({0,-1,0/0,math.huge,256,1.5})do
        local f=fixture();f.active=value;assert(not pcall(Guard.activity,f.session,f.bridge,true))
    end
end)
test('stale receipt unrelated skill and missing token rejected before activity query',function()
    for _,kind in ipairs({'receipt','skill','token','inactive'})do
        local f=fixture()
        if kind=='receipt'then f.bridge.tokens.token.receipt={}
        elseif kind=='skill'then f.bridge.tokens.token.id='attack_01'
        elseif kind=='token'then f.session.current_skill=nil else f.session.state='OFF'end
        assert(not pcall(Guard.activity,f.session,f.bridge,true));assert(f.reads==0)
    end
end)
print('Death trial activity fixtures: '..count..' passed; no native Kill invoked.')
