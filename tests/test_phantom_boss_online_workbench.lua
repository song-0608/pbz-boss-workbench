local root,candidate=assert(arg[1]),assert(arg[2])
local dir=candidate..'/PBZCoop/Scripts/'
local deps=dofile(dir..'bwb_local_dependencies.lua')(dir)
local config=dofile(dir..'bwb_config.lua')
local Workbench=dofile(root..'/tools/phantom_boss_online_workbench.lua')
local checks=0
local function check(name,fn)fn();checks=checks+1;print('PASS '..name)end
local function fixture()
    local f={now=100,logs={},restores=0,locks=0,unlocks=0,selections=0}
    local grant={session_id='test-session',role='guest',expires_at=200}
    local scope={attest=function(_,restore)assert(restore or not f.expired);return grant end}
    local peer={protocol={ready=false}}
    local renderer={render=function(_,pc,opened,cursor,selected)
        f.renders=(f.renders or 0)+1;f.rendered={pc,opened,cursor,selected}
        if f.render_error then error('widget rendering rejected')end
        return true
    end,close=function()f.ui_closes=(f.ui_closes or 0)+1;return true end}
    local wb=Workbench.new(scope,peer,deps,config,function(line)f.logs[#f.logs+1]=line end,function()return f.now end,renderer)
    f.wb,f.peer,f.grant=wb,peer,grant
    function f:mount(id)
        local layer={lock=function(_,pc)
            assert(pc==self.pc);self.locks=self.locks+1;self.locked=true
            if self.lock_error then error('partial input attach')end
            return true
        end,unlock=function()
            self.unlocks=self.unlocks+1
            if self.unlock_error then return false end
            self.locked=false;return true
        end}
        self.pc={};self.host={}
        self.control={session={state='OFF',restore=function(s)
            self.restores=self.restores+1
            if self.restore_error then return false,'restore rejected' end
            s.state='OFF';s.receipt=nil;return true
        end}}
        self.control.runtime={stop=function()
            self.runtime_stops=(self.runtime_stops or 0)+1
            return self.view:shutdown()
        end}
        self.view=wb:mount(self.control,self.host,layer,self.pc,id or 'ahua_guitoudao')
        return self.view
    end
    function peer:select_boss(id)
        assert(not f.locked and f.control.session.state=='OFF'and not f.control.session.receipt)
        f.selections=f.selections+1;f.next_id=id
        if f.select_error then return false,'assembly rejected' end
        assert(f.view:shutdown());return true
    end
    return f
end
check('four pinned Bosses only and current selection matches each instance',function()
    local f=fixture();f:mount('056_youlong');local w=f.wb.widget
    local entries=w.options.entries();assert(#entries==4 and entries[w.cursor].id=='056_youlong')
    for _,e in ipairs(entries)do assert(config.bosses[e.id]and e.playable and not e.detail:find('离线'))end
end)
check('opening restores control before attaching the menu barrier',function()
    local f=fixture();local w=f:mount();f.control.session.state='ACTIVE';f.control.session.receipt={}
    assert(w:toggle()and f.restores==1 and f.locked and w:is_open())
    assert(not f.control.session.receipt and f.control.session.state=='OFF')
end)
check('failed player restoration cannot lock menu input',function()
    local f=fixture();local w=f:mount();f.restore_error=true
    assert(not w:toggle()and f.locks==0 and not w:is_open())
end)
check('partial input attachment is rolled back without opening',function()
    local f=fixture();local w=f:mount();f.lock_error=true
    assert(not w:toggle()and not f.locked and f.unlocks==1 and not w:is_open())
end)
check('same Boss confirmation only closes without reassembly',function()
    local f=fixture();local w=f:mount();assert(w:toggle());assert(w:confirm())
    assert(not w:is_open()and not f.locked and f.selections==0)
end)
check('different Boss restores menu input before retiring runtime',function()
    local f=fixture();local w=f:mount();assert(w:toggle()and w:move(1)and w:confirm())
    assert(f.selections==1 and f.next_id~='ahua_guitoudao'and not f.locked)
    assert(f.wb.widget.busy and not f.wb.widget.opened and not w:toggle())
end)
check('new assembly releases busy only when its runtime mounts',function()
    local f=fixture();local w=f:mount();assert(w:toggle()and w:move(1)and w:confirm())
    local next_id=f.next_id;f:mount(next_id)
    assert(not f.wb.widget.busy and f.wb.widget.options.selected()==next_id)
    assert(f.view:toggle()and f.locked)
end)
check('rejected assembly clears busy and preserves explicit failure',function()
    local f=fixture();local w=f:mount();assert(w:toggle()and w:move(1)and w:confirm())
    f.wb:assembly_changed('REJECTED','no clearance')
    assert(not f.wb.widget.busy and f.wb.widget.message:find('no clearance',1,true))
end)
check('immediate selection rejection leaves no busy menu or input lock',function()
    local f=fixture();local w=f:mount();f.select_error=true;assert(w:toggle()and w:move(1))
    assert(not w:confirm()and not f.locked and not w:is_open()and f.selections==1)
end)
check('failed menu detach retains input owner and prevents selection',function()
    local f=fixture();local w=f:mount();assert(w:toggle()and w:move(1));f.unlock_error=true
    assert(not pcall(w.confirm,w)and f.locked and f.selections==0)
    assert(not pcall(w.shutdown,w));f.unlock_error=false;assert(w:shutdown()and not f.locked)
end)
check('online status is separate from offline proof and throttled between changes',function()
    local f=fixture();f:mount();f.host.status(nil,false)
    for _=1,1000 do f.host.status(nil,false)end
    assert(#f.logs==1 and f.logs[1]:find('PBZ_ONLINE_UI:STATUS=',1,true))
    assert(f.logs[1]:find('"role":"guest"',1,true)and not f.logs[1]:find('offline',1,true))
    f.now=101;f.peer.protocol.ready=true;f.host.status(nil,false);assert(#f.logs==2)
    assert(f.view:toggle());f.host.status(nil,false);assert(#f.logs==3)
end)
check('retired runtime cannot emit stale status over a replacement',function()
    local f=fixture();local w=f:mount();local old=f.host.status
    assert(w:toggle()and w:move(1)and w:confirm());f:mount(f.next_id)
    old(nil,true);assert(#f.logs==0);f.host.status(nil,true);assert(#f.logs==1)
end)
check('expired lease refuses menu actions and new mounts',function()
    local f=fixture();local w=f:mount();f.expired=true
    assert(not pcall(w.toggle,w)and f.locks==0)
    assert(not pcall(f.host.status,nil,true))
end)
check('close is idempotent and restores input even after lease expiry',function()
    local f=fixture();local w=f:mount();assert(w:toggle());f.expired=true
    assert(f.wb:close()and f.wb:close()and not f.locked)
    f.host.status(nil,true);assert(#f.logs==0 and not f.wb.widget:is_open())
    f.expired=false;assert(not pcall(f.mount,f))
end)
check('native UMG receives current cursor selected Boss and open state',function()
    local f=fixture();local w=f:mount('056_youlong');assert(w:toggle()and w:move(1))
    f.host.status(nil,false)
    assert(f.rendered[1]==f.pc and f.rendered[2]==true and f.rendered[3]==1 and f.rendered[4]==4)
    for _=1,100 do f.host.status(nil,false)end
    assert(f.renders==1 and f.ui_closes==nil)
    assert(w:shutdown()and f.ui_closes==1 and not f.locked)
end)
check('native render rejection retires input runtime once and preserves diagnostic',function()
    local f=fixture();local w=f:mount();assert(w:toggle());f.render_error=true
    f.host.status(nil,true);f.host.status(nil,true)
    assert(f.runtime_stops==1 and not f.locked and f.ui_closes==1 and #f.logs==1)
    assert(f.logs[1]:find('render failed',1,true)and not w:is_open())
end)
check('closed menu exposes selection rejection and clears it on a successful remount',function()
    local f=fixture();local w=f:mount();f.select_error=true;assert(w:toggle()and w:move(1))
    assert(not w:confirm());f.host.status(nil,true)
    assert(f.logs[#f.logs]:find('assembly rejected',1,true)and not w:is_open())
    assert(w:toggle());assert(w:shutdown());f:mount('057_wanjun')
    assert(f.wb.widget.message=='');f.host.status(nil,true)
    assert(not f.logs[#f.logs]:find('assembly rejected',1,true))
end)
print('PASS '..checks..' online workbench groups; pinned chooser with fake native input, no game started')
