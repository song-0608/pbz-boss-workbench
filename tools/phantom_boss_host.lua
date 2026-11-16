-- Minimal UE4SS host for the control-plane observer. No NPC enumeration, possession,
-- inventory, ability grant, memory offsets or network policy changes.
local M = {}
local function valid(object)
    return object and object:IsValid()==true
end
local function object_ref(object)
    assert(valid(object),'invalid engine object')
    local class=object:GetClass()
    assert(valid(class),'invalid object class')
    local address,name,class_name=object:GetAddress(),object:GetFullName(),class:GetFullName()
    assert(type(address)=='number' and address>0 and address==math.floor(address),'invalid object address')
    assert(type(name)=='string' and #name>0,'invalid full object name')
    local path=type(class_name)=='string' and class_name:match('^[^ ]+ (/.+)$')
    assert(path,'unreadable class path')
    return {address=address,name=name,class=path}
end
local function same(a,b)
    return a.address==b.address and a.name==b.name and a.class==b.class
end
local function world_id(actor)
    local world=actor:GetWorld()
    local ref=object_ref(world)
    return ref.name..'|'..string.format('%.0f',ref.address)..'|'..ref.class
end

function M.new(api,launch,globals)
    local g=globals or _G
    assert(type(api.getPlayer1)=='function' and type(api.link.now)=='function')
    assert(type(g.LoopInGameThreadWithDelay)=='function' and type(g.CancelDelayedAction)=='function',
        'cancellable game-thread scheduler required')
    assert(type(launch.revoke_control)=='function','dedicated controller restoration callback required')
    assert(type(launch.native_player_class)=='string'
        and launch.native_player_class:match('^/[A-Za-z0-9_/.]+_C$'),'captured native player class required')
    local expected_session,expected_build,expected_catalog=launch.session,launch.exe_sha256,launch.catalog_sha256
    local native_class,revoke=launch.native_player_class,launch.revoke_control
    local expires=launch.expires_at
    assert(type(expires)=='number' and expires>os.time() and expires<=os.time()+1200)
    local function check_lease()
        assert(launch.mode=='two-player-online-research' and launch.session==expected_session
            and launch.exe_sha256==expected_build and launch.catalog_sha256==expected_catalog
            and launch.native_player_class==native_class and launch.revoke_control==revoke
            and launch.expires_at==expires and os.time()<expires,'online research lease expired or changed')
    end
    check_lease()
    local host={}
    local control_probe
    host.bind_control_probe=function(probe)
        assert(type(probe)=='function' and control_probe==nil,'one online control observer required')
        control_probe=probe
        return function()
            if control_probe~=probe then return true end
            assert(probe()==nil,'cannot detach an active or unverified control observer')
            control_probe=nil
            return true
        end
    end
    host.now=function()
        local now=api.link.now()
        assert(type(now)=='number' and now==now and now>=0 and now<math.huge,'invalid native monotonic clock')
        return now
    end
    host.identify=function(actor,expected_world)
        local ref=object_ref(actor)
        ref.world=world_id(actor)
        assert(expected_world==nil or ref.world==expected_world,'actor is in another World')
        return ref
    end
    host.snapshot=function()
        check_lease()
        local pc,pawn=api.getPlayer1()
        local controller=host.identify(pc)
        local body=host.identify(pawn,controller.world)
        assert(same(object_ref(pc:K2_GetPawn()),body),'controller Pawn readback mismatch')
        assert(same(object_ref(pawn:GetController()),controller),'Pawn controller readback mismatch')
        local remote=control_probe and control_probe()
        if remote~=nil then
            assert(type(remote)=='table' and remote.verified==true,'online control observation unverified')
            assert(same(host.identify(remote.player_controller,controller.world),controller)
                and same(host.identify(remote.player,controller.world),body),
                'controlled Boss belongs to another local player')
            assert(body.class==native_class,'remote control original Pawn class changed')
            local boss=host.identify(remote.body,controller.world)
            local ai=host.identify(remote.controller,controller.world)
            assert(boss.class~=native_class and not same(boss,body) and not same(ai,controller),
                'remote control requires an independent Boss and AI controller')
            assert(same(host.identify(remote.body:GetController(),controller.world),ai)
                and same(host.identify(remote.controller:K2_GetPawn(),controller.world),boss),
                'Boss AI ownership readback mismatch')
            return {body=boss,body_actor=remote.body,controller=ai,player_controller=controller,player=body,
                world=controller.world,native_player=false,remote_control=true}
        end
        return {body=body,body_actor=pawn,controller=controller,world=controller.world,
            native_player=body.class==native_class}
    end
    host.on_revoke=function(reason)
        -- Restoration deliberately remains callable after expiry; the controller validates
        -- its captured World and actor identities before touching any saved objects.
        return revoke(reason)
    end
    host.log=function(message) api.log('[BWB] '..tostring(message)) end
    host.schedule=function(milliseconds,callback)
        assert(milliseconds==100 and type(callback)=='function','bounded observer cadence required')
        local handle,active,retired=nil,true,false
        local function cancel()
            active=false
            if handle~=nil and not retired then g.CancelDelayedAction(handle);retired=true end
        end
        local function recover(reason)
            if api.coop and api.coop.net then api.coop.net.enabled=false end
            local ok,result=pcall(host.on_revoke,reason)
            if not ok or result~=true then pcall(host.log,'observer recovery unverified: '..tostring(result))end
        end
        handle=g.LoopInGameThreadWithDelay(milliseconds,function()
            if not active then return end
            -- UE4SS ignores callback return values: cancellation must be explicit.
            local ok,stop=pcall(callback)
            if not ok then
                local cancelled,why=pcall(cancel)
                recover('observer callback failed')
                if not cancelled then pcall(host.log,'observer scheduler recovery pending: '..tostring(why))end
                return
            end
            if stop==true then
                local cancelled,why=pcall(cancel)
                if not cancelled then
                    recover('observer scheduler cancellation failed')
                    pcall(host.log,'observer scheduler recovery pending: '..tostring(why))
                end
            end
        end)
        assert(handle~=nil,'native scheduler did not return a cancellation handle')
        return cancel
    end
    return host
end
return M
