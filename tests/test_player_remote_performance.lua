-- Count native adapter reads, not GPU frames or elapsed gameplay time.
local root,candidate=assert(arg[1]),assert(arg[2])
package.path=candidate..'/PBZBossControl/Scripts/?.lua;'..package.path
local Remote=require('remote_control')
local Original=assert(loadfile(root..'/releases/ahua-boss-workbench-v5-3f29975fe3b8826f/PBZBossControl/Scripts/remote_control.lua'))()
local function fixture(implementation,scheduler)
    local f={pc={},player={enabled=true},boss={},ai={started=true,tick=true,actor_tick=true},
        move_blocks=0,look_blocks=0,clock=100,reads=0,writes=0,read_counts={}}
    f.pc.pawn=f.player;f.player.controller=f.pc;f.ai.pawn=f.boss;f.boss.controller=f.ai
    f.rotation={Pitch=0,Yaw=10,Roll=0}
    local calls={reference=function(_,value)return value end,resolve=function(_,value)assert(value);return value end,
        same=function(_,a,b)return a==b end,pawn=function(_,value)return value.pawn end,
        controller=function(_,value)return value.controller end}
    local function read(name,fn)
        return function(...)
            f.reads=f.reads+1;f.read_counts[name]=(f.read_counts[name]or 0)+1
            if f.override==name then return f.override_value end
            return fn(...)
        end
    end
    local function write(fn)return function(...)f.writes=f.writes+1;return fn(...)end end
    local native={
        ai_started=read('ai_started',function(ai)return ai.started end),
        ai_tick=read('ai_tick',function(ai)return ai.actor_tick end),
        brain_tick=read('brain_tick',function(ai)return ai.tick end),
        input_enabled=read('input_enabled',function(player)return player.enabled end),
        move_ignored=read('move_ignored',function()return f.move_blocks>0 end),
        look_ignored=read('look_ignored',function()return f.look_blocks>0 end),
        set_ai_started=write(function(ai,on)ai.started=on end),
        set_ai_tick=write(function(ai,on)ai.actor_tick=on end),
        set_brain_tick=write(function(ai,on)ai.tick=on;if f.on_brain_write then f.on_brain_write()end end),
        snapshot=function()return{move_ignored=false,look_ignored=false,input_enabled=true,
            rotation={Pitch=0,Yaw=10,Roll=0}}end,
        block_move=write(function(_,on)f.move_blocks=f.move_blocks+(on and 1 or -1)end),
        block_look=write(function(_,on)f.look_blocks=f.look_blocks+(on and 1 or -1)end),
        disable_input=write(function(player)player.enabled=false end),
        enable_input=write(function(player)player.enabled=true end),
        rotation=function()return f.rotation end,
        set_rotation=write(function(_,value)f.rotation=value end),
        move=write(function()f.moved=true end)}
    f.service=implementation.new(calls,native,{binding_verified=true,scheduler_trial=scheduler,
        now=function()return f.clock end})
    f.ticket=f.service:capture(f.pc,f.player,f.boss,f.ai);f.service:apply(f.ticket)
    f.reads=0;f.writes=0;f.read_counts={}
    return f
end
local original,patched=fixture(Original),fixture(Remote)
for _=1,1000 do assert(original.service:maintain(original.ticket));assert(patched.service:maintain(patched.ticket))end
assert(original.reads==13000 and patched.reads==7000,
    'no-write maintenance must avoid the second identical full snapshot, while keeping brain policy validation')
assert(original.writes==0 and patched.writes==0,'read optimization must not introduce state writes')
assert(patched.read_counts.ai_started==1000 and patched.read_counts.ai_tick==1000
    and patched.read_counts.input_enabled==1000 and patched.read_counts.move_ignored==1000
    and patched.read_counts.look_ignored==1000 and patched.read_counts.brain_tick==2000)

local f=fixture(Remote);f.ai.tick=true
f.on_brain_write=function()f.boss.controller=f.pc end
assert(not f.service:maintain(f.ticket)and f.writes==1 and not f.ai.tick,
    'a native maintenance write must be followed by a fresh complete ownership/input verification')
f=fixture(Remote);f.boss.controller=f.pc;f.ai.tick=true
assert(not f.service:maintain(f.ticket)and f.writes==0,'other broken invariants cannot be repaired by writing brain state')
f=fixture(Remote);assert(f.service:maintain(f.ticket));f.player.enabled=true
assert(not pcall(f.service.move,f.service,f.ticket,1,0,1)and f.writes==0,
    'movement must re-read input invariants instead of reusing a previous maintenance snapshot')
f=fixture(Remote);assert(f.service:maintain(f.ticket));f.pc.pawn={}
assert(not pcall(f.service.look,f.service,f.ticket,1,1)and f.writes==0,
    'look must re-read player ownership instead of reusing a previous maintenance snapshot')
f=fixture(Remote);assert(f.service:maintain(f.ticket));f.ai.actor_tick=true
assert(not f.service:verify(f.ticket),'a later verification must never reuse the previous snapshot')

for _,name in ipairs({'ai_started','ai_tick','brain_tick','input_enabled','move_ignored','look_ignored'})do
    for _,value in ipairs({1,'false'})do
        f=fixture(Remote);f.override=name;f.override_value=value
        assert(not pcall(f.service.maintain,f.service,f.ticket)and f.writes==0,'unknown native boolean must fail before writes: '..name)
    end
    f=fixture(Remote);f.override=name
    assert(not pcall(f.service.maintain,f.service,f.ticket)and f.writes==0,'missing native boolean must fail before writes: '..name)
end
local unsafe=fixture(Original);unsafe.override='ai_started'
assert(unsafe.service:maintain(unsafe.ticket),'negative control reproduces nil AI state accepted by old boolean negation')

f=fixture(Remote,true);f.service:begin_scheduler(f.ticket,'attack_01',25)
local before=f.writes;assert(f.service:maintain(f.ticket)and f.writes==before)
f.clock=125;assert(not f.service:maintain(f.ticket)and f.writes==before,
    'snapshot reuse must preserve exact scheduler expiry and must not renew it')
f.service:end_scheduler(f.ticket);assert(f.service:restore(f.ticket)and f.player.enabled and f.ai.tick and f.ai.actor_tick)
print('PASS 1000 no-write remote maintenance calls: original adapter reads=13000, candidate reads=7000; writes=0')
print('PASS fresh verification after writes and across calls, strict native booleans, ownership changes and scheduler expiry')
