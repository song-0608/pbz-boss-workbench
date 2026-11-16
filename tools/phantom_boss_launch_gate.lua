-- One cold process, one activation. Waiting loads no gameplay modules and sends
-- no input. A launcher can supply current declarations after read-only capture.
local M={}
function M.wait(directory,activate,g,io_api,identity_api)
    g=g or _G;io_api=io_api or io
    assert(type(activate)=='function' and type(g.LoopInGameThreadWithDelay)=='function'
        and type(g.CancelDelayedAction)=='function','cancellable launch gate required')
    if rawget(g,'PBZBossOnlineGate') then return g.PBZBossOnlineGate end
    local self={state='DORMANT',closed=false,restore_pending=false}
    g.PBZBossOnlineGate=self
    local handle,peer,request
    local function read(name,maximum)
        local f=io_api.open(directory..name,'rb');if not f then return nil end
        local bytes=f:read(maximum+1);f:close()
        assert(type(bytes)=='string' and #bytes<=maximum,'oversized research gate file')
        return bytes
    end
    local function cancel()
        if handle~=nil then local h=handle;handle=nil;g.CancelDelayedAction(h)end
    end
    local function close(reason)
        if self.closed then return not self.restore_pending end
        self.closed=true;self.reason=tostring(reason);self.state='CLOSING'
        if peer then
            local ok,clean=pcall(peer.close,peer)
            self.restore_pending=not ok or clean~=true
        end
        self.state='CLOSED';cancel();return not self.restore_pending
    end
    function self:close(reason)return close(reason or 'research gate closed')end
    local function fields(bytes)
        local result={};assert(bytes and #bytes>0,'missing gate request')
        for line in bytes:gmatch('[^\r\n]+')do
            local key,value=line:match('^([a-z_]+)=([%w_%-/%.]+)$')
            assert(key and not result[key],'invalid or duplicate gate field')
            result[key]=value
        end
        local count=0;for _ in pairs(result)do count=count+1 end
        assert(count==8 and result.mode=='two-player-online-research'
            and (result.role=='host' or result.role=='guest')
            and #result.session==32 and result.session:match('^[0-9a-f]+$')
            and #result.activation==32 and result.activation:match('^[0-9a-f]+$')
            and result.binding=='bwb_current_bindings.lua','unexpected gate identity')
        result.issued_at=assert(tonumber(result.issued_at));result.expires_at=assert(tonumber(result.expires_at))
        assert(result.issued_at==math.floor(result.issued_at) and result.expires_at==math.floor(result.expires_at)
            and result.issued_at>0 and result.issued_at<=os.time() and result.expires_at>os.time()
            and result.expires_at-result.issued_at<=1200,'expired or unbounded gate request')
        return result
    end
    local function tick()
        if self.closed then return end
        local ok,why=pcall(function()
            if read('bwb_stop.txt',256) then close('launcher stop requested');return end
            if not request then
                local bytes=read('bwb_gate.ini',2048)
                if not bytes then return end -- inert installed payload, no lease
                request=fields(bytes)
                self.state='WAITING_DECLARATIONS'
            end
            if os.time()>=request.expires_at then close('research lease expired');return end
            if peer then
                if peer.startup_state=='FAILED' or peer.closed or peer.restore_pending then
                    close('assembly startup or recovery stopped')
                end
                return
            end
            local data=read(request.binding,1048576);if not data then return end
            -- The launcher emits only a returned data table. Empty environment
            -- prevents a declaration file from calling native/global functions.
            local chunk=assert(load(data,'@current-online-declarations','t',{}))
            local captured=chunk()
            assert(type(captured)=='table' and captured.activation==request.activation
                and captured.session==request.session and captured.role==request.role
                and captured.issued_at==request.issued_at and captured.expires_at==request.expires_at
                and captured.boss_id==request.boss_id
                and type(captured.native_player_class)=='string' and type(captured.assembly)=='table',
                'declarations belong to another launch')
            if not identity_api then
                assert(type(g.package)=='table' and type(g.package.loadlib)=='function',
                    'native process identity loader unavailable')
                identity_api=assert(g.package.loadlib(directory..'../dlls/main.dll','bwb_process_identity'))
            end
            local identity=identity_api()
            assert(type(identity)=='string' and identity:match('^[1-9][0-9]*:[1-9][0-9]*$')
                and type(captured.process_identity)=='string' and captured.process_identity==identity,
                'declarations belong to another game process')
            captured.mode=request.mode
            captured.lease_provider=function()
                assert(not self.closed or self.state=='CLOSING' or self.restore_pending,'research gate is closed')
                return {mode=request.mode,isolated=true,session_id='bwb_'..request.session,
                    role=request.role,issued_at=request.issued_at,expires_at=request.expires_at,
                    exe_sha256=captured.exe_sha256,catalog_sha256=captured.catalog_sha256,
                    upstream_commit=captured.upstream_commit}
            end
            captured.session='bwb_'..request.session
            self.state='ACTIVATING'
            peer=assert(activate(captured),'activation did not return its recovery owner')
            assert(type(peer.close)=='function','activation recovery owner missing')
            self.state='ACTIVE'
        end)
        if not ok then self.failure=tostring(why);close('gate rejected: '..self.failure)end
    end
    handle=g.LoopInGameThreadWithDelay(250,tick)
    assert(handle~=nil,'gate scheduler must return cancellation handle')
    return self
end
return M
