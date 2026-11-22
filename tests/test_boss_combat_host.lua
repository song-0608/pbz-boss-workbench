local root=assert(arg[1]);package.path=root..'/tools/?.lua;'..root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local Host=require('boss_combat_host')
local total=0
local function test(name,fn)fn();total=total+1;print('PASS '..name)end
local function fixture()
    local f={paused=false,menu=false,queries=0,checks=0}
    local r={input_enabled=true};local pc={}
    local b={check=function(_,actual)assert(actual==r);f.checks=f.checks+1;return pc end}
    local s={bridge=b,state='ACTIVE',receipt=r}
    local rt={running=true,session=s,host={workbench={is_open=function()return f.menu end}}}
    local pause={IsGamePaused=function(_,actual)assert(actual==pc);f.queries=f.queries+1;return f.paused end}
    local contract={pid=42,native_input_binding_verified=true,cues={},defense_by_role={
        ['056_youlong']={key='RIGHT_MOUSE_BUTTON'}}}
    f.pause_query=function(pc)return pause:IsGamePaused(pc)end
    f.options=Host.options(rt,'056_youlong',contract,{},f.pause_query,function()end)
    f.runtime=rt;f.session=s;f.receipt=r;f.contract=contract;f.pause=pause
    return f
end
test('active input uses the exact runtime session with no ambient session global',function()
    local f=fixture();assert(rawget(_G,'session')==nil)
    assert(f.options.input_allowed(f.receipt));assert(f.checks==1 and f.queries==1)
    assert(f.options.defense==f.contract.defense_by_role['056_youlong'])
    assert(f.options.cues==f.contract.cues and f.options.native_input.pid==42)
end)
test('inactive changed or disabled session and menu reject before querying the engine',function()
    for _,mode in ipairs({'stopped','session','bridge','state','missing','receipt','disabled','menu'})do
        local f=fixture();local receipt=f.receipt
        if mode=='stopped'then f.runtime.running=false
        elseif mode=='session'then f.runtime.session={}
        elseif mode=='bridge'then f.session.bridge={}
        elseif mode=='state'then f.session.state='RESTORING'
        elseif mode=='missing'then receipt=nil
        elseif mode=='receipt'then receipt={input_enabled=true}
        elseif mode=='disabled'then f.receipt.input_enabled=false
        else f.menu=true end
        assert(not f.options.input_allowed(receipt),mode)
        assert(f.checks==0 and f.queries==0,mode)
    end
end)
test('only an explicit false pause query permits input',function()
    local f=fixture()
    for _,value in ipairs({true,0,'false'})do
        f.paused=value;assert(not f.options.input_allowed(f.receipt))
    end
    f.paused=nil;assert(not f.options.input_allowed(f.receipt))
    f.paused=false;assert(f.options.input_allowed(f.receipt))
    f.pause.IsGamePaused=function()error('world changed')end
    assert(not pcall(f.options.input_allowed,f.receipt))
end)
test('a role without a declared stance retains cues without borrowing another role ability',function()
    local f=fixture();local options=Host.options(f.runtime,'057_wanjun',f.contract,{},f.pause_query)
    assert(options.defense==nil and options.cues==f.contract.cues)
    assert(options.input_allowed(f.receipt))
end)
test('unverified or foreign input contract is rejected at host creation',function()
    for _,value in ipairs({false,0,'true'})do
        local f=fixture();f.contract.native_input_binding_verified=value
        assert(not pcall(Host.options,f.runtime,'056_youlong',f.contract,{},f.pause_query))
    end
    for _,value in ipairs({0,-1,4.5,'42'})do
        local f=fixture();f.contract.pid=value
        assert(not pcall(Host.options,f.runtime,'056_youlong',f.contract,{},f.pause_query))
    end
end)
test('native held input still follows fresh menu and pause state through the combat controller',function()
    local f=fixture();f.runtime.session.state='OFF';f.runtime.session.receipt=nil
    local s=f.session;local b=s.bridge;b.verify_restored=function()return true end
    function s:enter()self.state='ACTIVE';self.receipt=f.receipt;return true end
    function s:restore()self.state='OFF';self.receipt=nil;return true end
    s.config={controls={},skills={}};f.options.defense=nil;f.options.cues=nil
    local focused=true
    f.options.globals.PBZNativeCombatInputSnapshot=function()
        return{schema=1,pid=42,now=1,allowed=focused,down=false}
    end
    require('boss_combat_controls').attach(s,f.options);assert(s:enter())
    assert(s:sample_combat_input({allowed=true}))
    f.menu=true;assert(not s:sample_combat_input({allowed=true}));f.menu=false
    f.paused=true;assert(not s:sample_combat_input({allowed=true}));f.paused=false
    focused=false;assert(not s:sample_combat_input({allowed=true}))
    focused=true;assert(s:sample_combat_input({allowed=true}));assert(s:restore())
end)
if arg[2]then
    test('generated arena assembly runs and samples with undeclared globals rejected',function()
        local file=assert(io.open(arg[2]..'/PBZBossControl/Scripts/owned_arena.lua','rb'))
        local source=file:read('*a');file:close()
        local first=assert(source:find('                    if options.native_combat_contract then',1,true))
        local last=assert(source:find('                    deferred=true',first,true))
        local f=fixture();f.contract.cues=nil;f.contract.defense_by_role={}
        -- UE4SS exposes reflected functions as callable objects.
        local native=f.pause.IsGamePaused
        f.pause.IsGamePaused=setmetatable({}, {__call=function(_,...)return native(...)end})
        local s=f.session;s.state='OFF';s.receipt=nil
        function s:enter()self.state='ACTIVE';self.receipt=f.receipt;return true end
        function s:restore()self.state='OFF';self.receipt=nil;return true end
        s.bridge.verify_restored=function()return true end;s.config={controls={},skills={}}
        local globals={PBZNativeCombatInputSnapshot=function()
            return{schema=1,pid=42,now=1,allowed=true,down=false}
        end}
        local env={runtime=f.runtime,profile={id='056_youlong'},
            options={developer_only=true,native_combat_contract=f.contract},_G=globals,
            StaticFindObject=function(path)
                assert(path=='/Script/Engine.Default__GameplayStatics');return f.pause
            end,valid=function(value)return value==f.pause end,
            assert=assert,require=require,log=function()end}
        setmetatable(env,{__index=function(_,key)error('undeclared assembly global: '..tostring(key))end})
        assert(load(source:sub(first,last-1),'generated combat assembly','t',env))()
        assert(s:enter());assert(s:sample_combat_input({allowed=true}))
        f.menu=true;assert(not s:sample_combat_input({allowed=true}));f.menu=false
        assert(s:restore())
    end)
end
print('Combat host binding fixtures: '..total..'; live input remains unverified')
