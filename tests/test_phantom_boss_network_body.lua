-- Execute the actual patched upstream snapshot functions, not a parallel sender.
local candidate=assert(arg[1])
local file=assert(io.open(candidate..'/upstream-local-patches/coop.lua','rb'))
local source=file:read('a');file:close()
local start=assert(source:find('    local function sendPlayer()\n',1,true))
local finish=assert(source:find('    -- A hit reaction of the local player',start,true))
local code=source:sub(start,finish-1)..'\nreturn {send=sendPlayer,pawn=localPawn}\n'
local checks=0
local function check(name,fn)fn();checks=checks+1;print('PASS '..name)end
local function fixture(bwb)
    local e={reads={},sends={},fallbacks=0,offsets=0}
    local native={GetAddress=function()return 10 end}
    local boss={GetAddress=function()return 20 end}
    local pc={GetAddress=function()return 30 end}
    local slow={hp=0,maxhp=0,cine=0}
    local api={}
    if bwb then api.bossWorkbench={network_body=function()return e.body,e.body and e.body:GetAddress()end}end
    local env={api=api,slow=slow,net={frameNow=1,localMap=1,UNSETTLED_S=1},math=math,os=os,
        valid=function(o)return o~=nil end,MOVE_WALKING=1,MOVE_FALLING=2,MOVE_NONE=0,
        getPlayer1=function()e.fallbacks=e.fallbacks+1;return pc,native end,
        game={pawnOffset=function()e.offsets=e.offsets+1;return 8 end,
            read=function(pawn,addr)
                assert(addr==pawn:GetAddress());e.reads[#e.reads+1]=pawn
                return addr,2,3,4,0,0,0,1,90,100
            end},
        link={pointer=function()return 10 end,state=function(...)e.sends[#e.sends+1]={...}end}}
    e.fn=assert(load(code,'@actual_patched_upstream_sendPlayer','t',env))()
    e.native,e.boss,e.body,e.slow,e.env=native,boss,boss,slow,env
    return e
end
check('retained AI Boss supplies position and health instead of native Pawn',function()
    local e=fixture(true);e.fn.send()
    assert(e.reads[1]==e.boss and e.sends[1][1]==20 and e.fn.pawn()==e.boss)
    assert(e.fallbacks==0 and e.offsets==0 and e.slow.pc==nil and e.slow.pawnAt==nil)
end)
check('unready or transitioning Boss emits no stale native state',function()
    local e=fixture(true);e.body=nil;e.fn.send()
    assert(#e.sends==0 and #e.reads==0 and e.fallbacks==0 and e.fn.pawn()==nil)
end)
check('restoration changes to the newly acknowledged native body without old pointer cache',function()
    local e=fixture(true);e.fn.send();e.body=e.native;e.env.net.frameNow=2;e.fn.send()
    assert(e.reads[2]==e.native and e.sends[2][1]==10 and e.fn.pawn()==e.native)
    assert(e.offsets==0 and e.fallbacks==0)
end)
check('cleared observation stops slow sampling as well as the state sender',function()
    local e=fixture(true);e.fn.send();e.body=nil;e.env.net.frameNow=2
    assert(e.fn.pawn()==nil);e.fn.send();assert(#e.sends==1 and e.fallbacks==0)
end)
check('unmodified upstream path keeps its native Pawn cache when no workbench is attached',function()
    local e=fixture(false);e.fn.send();e.fn.send()
    assert(#e.reads==2 and e.reads[1]==e.native and e.fallbacks==1 and e.offsets==1)
end)
check('actual slow watcher keeps map identity but cannot inspect inventory loot or currency',function()
    local first=assert(source:find('    local function watchSlowly(now)\n',1,true))
    local last=assert(source:find('    -- Where to show that player this frame.',first,true))
    local code=source:sub(first,last-1)..'\nreturn watchSlowly\n'
    local reads=0
    local game=setmetatable({getHealth=function()error('health was already read this frame')end,
        mapName=function()return 'Arena'end,forgetActors=function()end},
        {__index=function(_,key)reads=reads+1;error('unexpected inventory/other watcher: '..key)end})
    local env={api={bossWorkbench={}},localPawn=function()return {}end,
        game=game,slow={hpAt=1},net={frameNow=1},reach={},handover={reset=function()end},
        link={map=function(name)assert(name=='Arena');return 123 end}}
    local run=assert(load(code,'actual_patched_watchSlowly','t',env))()
    run(1);assert(reads==0 and env.net.localMap==123)
end)
check('actual upstream downed-player watcher exits before owed inventory and rewards',function()
    local first=assert(source:find('    local function watchOwnDeath()\n',1,true))
    local tail=source:sub(first+#'    local function watchOwnDeath()\n')
    local guard=assert(tail:match('^([^\n]+)\n'))
    local touched=false
    local run=assert(load('return function()\n'..guard..'\ntouch()\nend','actual_death_guard','t',
        {api={bossWorkbench={}},touch=function()touched=true end}))()
    run();assert(not touched)
end)
check('legacy move samplers exit before stance scans gear and props during Boss sessions',function()
    local f=assert(io.open(candidate..'/upstream-local-patches/moves.lua','r'));local moves=f:read('a');f:close()
    for _,anchor in ipairs({'    coop.frameTicks.moveStarts = function()\n','    coop.extraTicks.moves = function()\n'})do
        local at=assert(moves:find(anchor,1,true));local tail=moves:sub(at+#anchor)
        local guard=assert(tail:match('^([^\n]+)\n'));local touched=false
        local fn=assert(load('return function()\n'..guard..'\ntouch()\nend','actual_move_guard','t',
            {api={bossWorkbench={}},touch=function()touched=true end}))()
        fn();assert(not touched)
    end
    assert(source:find('local QUICK = { BWV1 = true,',1,true),'cosmetic frames must use the native quick lane')
end)
print('PASS '..checks..' network body groups; patched upstream Lua, fake engine, no relay/game')
