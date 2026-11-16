local root,candidate=assert(arg[1]),assert(arg[2])
local directory=candidate..'/PBZCoop/Scripts/'
local checks=0
local function check(name,fn)fn();checks=checks+1;print('PASS '..name)end
local function fixture(fail)
    local s={loaded={},calls=0,closes=0,game={}}
    local api={version='1.7.3',getPlayer1=function()end}
    local g={};local peer={close=function()s.closes=s.closes+1 end}
    for _,name in ipairs({'bagSummary','grantLoot','watchCurrency','watchGear','hookGifts',
        'hookPiles','hookFlowers','hookRest','hookSit','watchItemFx','oweBoss','rollLoot',
        'payOwed','offerChestsAgain','commands','pickupShares','tipsWanted'})do
        s.game[name]=function()s.calls=s.calls+1;error('non-combat API reached: '..name)end
    end
    local env=setmetatable({dofile=function(path)
        local name=assert(path:match('/([^/]+)%.lua$'));s.loaded[#s.loaded+1]=name
        return function(a)
            if name=='lang' then assert(a==directory);return {} end
            assert(a==api)
            if name=='pbz' then return s.game end
            if name=='coop' then
                assert(s.game.hookGifts==nil and s.game.bagSummary==nil)
                return {net={enabled=false}}
            end
            if name=='bwb_startup' then
                assert(g.PBZ and api.puppets and api.hitfx);return peer
            end
            if name=='autostart' then
                assert(api.bossWorkbench==peer and g.PBZ.bossWorkbench==peer)
                api.partner.start();api.partner.goOnLink();api.onlinepanel.start()
                if fail then error('transport unavailable')end
            end
            return {}
        end
    end},{__index=_G})
    local mount=assert(loadfile(root..'/tools/phantom_boss_combat_runtime.lua','t',env))()
    function s:mount()return mount(api,directory,g)end
    s.api,s.g,s.peer=api,g,peer
    return s
end
check('only combat modules initialize in dependency order',function()
    local s=fixture();assert(s:mount()==s.peer)
    assert(table.concat(s.loaded,',')=='lang,pbz,coop,status,moves,puppets,hitfx,bwb_startup,autostart')
    assert(s.calls==0)
end)
check('kill rewards never invoke upstream loot inventory or currency functions',function()
    local s=fixture();s:mount()
    local dust,items,level=s.api.game.rollLoot({});assert(dust==0 and #items==0 and level==0)
    s.api.game.offerChestsAgain();assert(s.calls==0)
    for _,name in ipairs({'grantLoot','bagSummary','watchGear','hookGifts','hookPiles','hookRest','payOwed','oweBoss'})do
        assert(s.api.game[name]==nil,name)
    end
    assert(next(s.api.game.commands)==nil and not s.api.game.pickupShares and not s.api.game.tipsWanted)
end)
check('optional travel panel callbacks install no gameplay or input machinery',function()
    local s=fixture();s:mount()
    assert(not s.api.localcoop.bellMenuUp() and not s.api.localcoop.screenUp())
    assert(not s.api.partner.teleport and s.calls==0)
    for _,name in ipairs({'story','flowsync','units','rules','prologue','mapfog','freetravel','pvp','arena','revive','scaling'})do
        assert(s.api[name]==nil,name)
    end
end)
check('failed transport initialization restores the mounted peer',function()
    local s=fixture(true);assert(not pcall(s.mount,s));assert(s.closes==1)
end)
check('actual main takes combat composition before optional modules or command polling',function()
    local f=assert(io.open(candidate..'/upstream-local-patches/main.lua','r'));local src=f:read('a');f:close()
    local first=assert(src:find('do\n    return dofile(SCRIPT_DIR .. "bwb_combat_runtime.lua")',1,true))
    local last=assert(src:find('\napi.lang = dofile',first,true))
    local tail=src:sub(first,last-1)..'\nerror("optional module tail executed")'
    local calls=0
    local run=assert(load(tail,'actual_main_combat_dispatch','t',{
        api={},SCRIPT_DIR=directory,dofile=function(path)
            assert(path==directory..'bwb_combat_runtime.lua');return function()calls=calls+1 end
        end,error=error}))
    run();assert(calls==1)
end)
print('PASS '..checks..' combat runtime groups; isolated composition, no game started')
