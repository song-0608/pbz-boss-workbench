-- Reuse the accepted chooser without inheriting its offline launch/status proof.
-- One coordinator survives Boss reassembly; each runtime owns only its menu layer.
local M={}
local function cleanup(errors,name,callback)
    local ok,result=pcall(callback)
    if not ok or result~=true then errors[#errors+1]=name..': '..tostring(result);return false end
    return true
end
local function quote(value)
    return '"'..value:gsub('[%z\1-\31\\"]',function(c)
        if c=='"'then return '\\"'elseif c=='\\'then return '\\\\'end
        return string.format('\\u%04x',string.byte(c))
    end)..'"'
end
function M.new(scope,peer,dependencies,config,emit,now,renderer)
    now=now or os.time
    local req=dependencies.require
    local selected,active,changing,stopped=nil,nil,false,false
    local self={}
    local widget=req('boss_workbench').new({entries=function()
        local out={}
        for _,entry in ipairs(req('workbench_catalog').list())do
            if config.bosses[entry.id]then
                out[#out+1]={id=entry.id,name=entry.name,playable=true,
                    detail='联机研究角色；Enter 装配，双方握手后按 F6 接管'}
            end
        end
        assert(#out==4,'exact four-Boss online catalog required')
        return out
    end,selected=function()return selected end})
    self.widget=widget
    local function publish(text,grant)
        assert(type(text)=='string'and #text<=4096,'bounded online workbench status required')
        emit('PBZ_ONLINE_UI:STATUS={"at":'..now()..',"session":'..quote(grant.session_id)
            ..',"role":'..quote(grant.role)..',"expires_at":'..grant.expires_at
            ..',"mode":"two-player-online-research","text":'..quote(text)..'}\n')
    end
    function self:mount(control,host,layer,pc,id,recovery)
        scope:attest(false)
        if self.recovery and not recovery then assert(self:stop_recovery()==true,'recovery menu retirement pending')end
        assert(not stopped and config.bosses[id] and not active,'previous menu owner must retire before mounting')
        local owner={control=control,layer=layer,pc=pc,last_at=-math.huge,last_revision=-1,recovery=recovery==true}
        active=owner;selected=not recovery and id or nil;changing=false;widget:changed()
        for index,entry in ipairs(widget.options.entries())do if entry.id==id then widget.cursor=index end end
        widget:set_adapter({
            restore=function(reason)
                scope:attest(false)
                if active~=owner then return false,'retired menu owner' end
                local ok,why=control.session:restore(reason)
                return ok==true and control.session.state=='OFF' and not control.session.receipt,why
            end,
            lock=function()
                scope:attest(false);assert(active==owner,'retired menu owner')
                return layer:lock(pc)
            end,
            unlock=function()return layer:unlock()end,
            select=function(next_id)
                scope:attest(false)
                assert(active==owner and control.session.state=='OFF'and not control.session.receipt,
                    'restore native player before online Boss selection')
                changing=true
                local ok,result,why=pcall(peer.select_boss,peer,next_id)
                if not ok or result~=true then
                    changing=false;widget.busy=false
                    return false,ok and why or result
                end
                return true
            end,
        })
        -- Runtime.stop must restore the old input layer, while keeping the chooser
        -- busy until the asynchronous replacement has actually become ready.
        host.workbench=setmetatable({}, {__index=function(_,key)
            if key=='shutdown'then return function()
                local errors={}
                cleanup(errors,'online workbench input recovery failed',function()return layer:unlock()end)
                if renderer then cleanup(errors,'online menu widget recovery failed',function()return renderer:close()end)end
                assert(#errors==0,table.concat(errors,'; '))
                if active==owner then
                    active=nil;widget.opened=false;widget.busy=changing
                end
                return true
            end end
            local value=widget[key]
            if type(value)=='function'then return function(_,...)return value(widget,...)end end
            return value
        end})
        host.status=function(_,force)
            if active~=owner or stopped then return end
            local at=now()
            if not force and widget.revision==owner.last_revision and at-owner.last_at<1 then return end
            local grant=scope:attest(false)
            if renderer then
                local index=0
                for i,entry in ipairs(widget.options.entries())do if entry.id==selected then index=i end end
                local ok,shown=pcall(renderer.render,renderer,pc,widget.opened,widget.cursor,index)
                if not ok or shown~=true then
                    emit('[BWB] online workbench render failed; retiring input runtime: '..tostring(shown)..'\n')
                    control.runtime:stop('online workbench rendering failed')
                    return
                end
            end
            local text=widget:is_open()and widget:text()or
                ((owner.recovery and 'Boss 装配重试  |  Insert 选择角色  |  Enter 重试\n'or
                'Boss 联机工作台  |  Insert 选择角色  |  F6 接管  |  F10 恢复\n')
                ..(peer.protocol.ready and '双方身份已确认' or '等待另一端身份确认'))
            if not widget:is_open() and widget.message~='' then text=text..'\n'..widget.message end
            publish(text,grant);owner.last_at=at;owner.last_revision=widget.revision
        end
        return host.workbench
    end
    -- A clean assembly rejection must not strand the chooser after Runtime.stop
    -- released its keys. This owner has menu keys only, never takeover/skills.
    function self:stop_recovery()
        local r=self.recovery
        if not r then return true end
        r.running=false
        local errors={}
        if r.cancel and cleanup(errors,'recovery scheduler retirement failed',function()r.cancel();return true end)then r.cancel=nil end
        if r.host.release_keys and not r.keys_released then
            r.keys_released=cleanup(errors,'recovery key retirement failed',function()return r.host.release_keys()end)
        end
        if not r.view_closed then
            r.view_closed=cleanup(errors,'recovery menu input restoration failed',function()return r.view:shutdown()end)
        end
        assert(#errors==0,table.concat(errors,'; '))
        self.recovery=nil;return true
    end
    function self:recover(host,layer,pc,id,guard,schedule)
        scope:attest(false)
        assert(not stopped and type(guard)=='function'and type(schedule)=='function','live recovery menu bindings required')
        if self.recovery then return true end
        assert(not active,'active Boss runtime still owns the chooser')
        assert(guard()==true,'original player recovery unverified')
        local r={host=host,running=true,pending=false}
        local control={session={state='OFF'}}
        control.session.restore=function()return guard()==true end
        control.runtime={stop=function()return self:stop_recovery()end}
        r.view=self:mount(control,host,layer,pc,id,true);self.recovery=r
        local function action(method,delta)
            if not r.running or self.recovery~=r then return end
            local ok,why=pcall(function()
                scope:attest(false);assert(guard()==true,'original player recovery changed')
                if delta then return r.view:move(delta)end
                return r.view[method](r.view)
            end)
            if not ok then
                emit('[BWB] recovery menu stopped: '..tostring(why)..'\n')
                self:stop_recovery();return
            end
            if r.running then host.status(nil,true)end
        end
        local function dispatch(key,method,delta)
            if not r.running or r.pending then return end
            if method~='toggle'and not widget.opened then return end
            local release=method=='confirm'or method=='close'or(method=='toggle'and widget.opened)
            local function invoke()r.pending=false;if r.running then host.on_game_thread(function()action(method,delta)end)end end
            if release and host.after_key_release then r.pending=true;host.after_key_release(key,invoke)
            else invoke()end
        end
        local ok,why=pcall(function()
            local keys={INS={'toggle'},UP_ARROW={'move',-1},DOWN_ARROW={'move',1},RETURN={'confirm'},ESCAPE={'close'},F10={'close'}}
            if host.validate_keys then local allowed={};for key in pairs(keys)do allowed[key]=true end;host.validate_keys(allowed)end
            for key,row in pairs(keys)do
                local selected_key,method,delta=key,row[1],row[2]
                host.bind_key(key,function()dispatch(selected_key,method,delta)end)
            end
            r.cancel=schedule(250,function()
                if not r.running then return end
                local valid=pcall(function()scope:attest(false);assert(guard()==true)end)
                if not valid then self:stop_recovery();return end
                host.status(nil,false)
            end)
            assert(type(r.cancel)=='function','cancellable recovery status timer required')
            widget:changed('装配未完成；Insert 重新选择，Enter 重试')
            host.status(nil,true)
        end)
        if not ok then self:stop_recovery();error(why)end
        return true
    end
    function self:assembly_changed(state,reason)
        if state=='REJECTED'or state=='FAULTED'then
            changing=false;widget.busy=false;widget:changed('装配未完成：'..tostring(reason or state))
        end
    end
    function self:close()
        stopped=true
        local errors={}
        cleanup(errors,'recovery menu cleanup pending',function()return self:stop_recovery()end)
        if active and cleanup(errors,'online menu input recovery pending',function()return active.layer:unlock()end)then active=nil end
        if renderer then cleanup(errors,'online menu widget recovery pending',function()return renderer:close()end)end
        assert(#errors==0,table.concat(errors,'; '))
        changing=false;widget.opened=false;widget.busy=false
        return true
    end
    return self
end
return M
