-- Reuse the accepted chooser without inheriting its offline launch/status proof.
-- One coordinator survives Boss reassembly; each runtime owns only its menu layer.
local M={}
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
    function self:mount(control,host,layer,pc,id)
        scope:attest(false)
        assert(not stopped and config.bosses[id] and not active,'previous menu owner must retire before mounting')
        local owner={control=control,layer=layer,pc=pc,last_at=-math.huge,last_revision=-1}
        active=owner;selected=id;changing=false
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
                assert(layer:unlock()==true,'online workbench input recovery failed')
                if renderer then assert(renderer:close()==true,'online menu widget recovery failed')end
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
                local index
                for i,entry in ipairs(widget.options.entries())do if entry.id==selected then index=i end end
                local ok,shown=pcall(renderer.render,renderer,pc,widget.opened,widget.cursor,index)
                if not ok or shown~=true then
                    emit('[BWB] online workbench render failed; retiring input runtime: '..tostring(shown)..'\n')
                    control.runtime:stop('online workbench rendering failed')
                    return
                end
            end
            local text=widget:is_open()and widget:text()or
                ('Boss 联机工作台  |  Insert 选择角色  |  F6 接管  |  F10 恢复\n'
                ..(peer.protocol.ready and '双方身份已确认' or '等待另一端身份确认'))
            publish(text,grant);owner.last_at=at;owner.last_revision=widget.revision
        end
        return host.workbench
    end
    function self:assembly_changed(state,reason)
        if state=='REJECTED'or state=='FAULTED'then
            changing=false;widget.busy=false;widget:changed('装配未完成：'..tostring(reason or state))
        end
    end
    function self:close()
        stopped=true
        if active then assert(active.layer:unlock()==true,'online menu input recovery pending');active=nil end
        if renderer then assert(renderer:close()==true,'online menu widget recovery pending')end
        changing=false;widget.opened=false;widget.busy=false
        return true
    end
    return self
end
return M
