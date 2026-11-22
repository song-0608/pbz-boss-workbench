local root=assert(arg[1],'project directory required')
local Driver=require('input_driver')

for _,look_yaw in ipairs({0,2})do
    local receipt={}
    local moved
    local session={state='ACTIVE',receipt=receipt,
        bridge={
            verify_control=function()return true end,
            look=function(_,current)assert(current==receipt);return true,20 end,
            update_camera=function(_,current)assert(current==receipt);return true,90 end,
            move=function(_,current,x,y)assert(current==receipt);moved={x,y};return true end
        }}
    function session:poll()return true end
    function session:restore()self.restores=(self.restores or 0)+1;self.state='OFF';return true end
    local driver=Driver.new(session,{read_input=function()
        return{allowed=true,forward=true,yaw_degrees=0,look_yaw=look_yaw}
    end})
    assert(driver:step())
    assert(math.abs(moved[1])<1e-10 and math.abs(moved[2]-1)<1e-10,
        'movement must use final target-camera yaw')
end

for _,yaw in ipairs({0/0,math.huge,'bad'})do
    local moves=0
    local session={state='ACTIVE',receipt={},
        bridge={verify_control=function()return true end,
            update_camera=function()return true,yaw end,
            move=function()moves=moves+1;return true end}}
    function session:poll()return true end
    function session:restore()self.restores=(self.restores or 0)+1;self.state='OFF';return true end
    local driver=Driver.new(session,{read_input=function()
        return{allowed=true,forward=true,yaw_degrees=0}
    end})
    assert(not driver:step()and session.restores==1 and moves==0,
        'invalid final camera yaw must restore before moving')
end

do
    local receipt={}
    local moves,looks,cameras=0,0,0
    local session={state='ACTIVE',receipt=receipt,
        bridge={
            verify_control=function()return true end,
            move=function(_,current)assert(current==receipt);moves=moves+1;return true end,
            look=function(_,current)assert(current==receipt);looks=looks+1;return true end,
            update_camera=function(_,current)assert(current==receipt);cameras=cameras+1;return true end
        }}
    function session:poll()return true end
    function session:flush_buffered_skill()self.current_skill='new native token';return true end
    local driver=Driver.new(session,{read_input=function()
        return{allowed=true,forward=true,yaw_degrees=0,look_yaw=2}
    end})
    assert(driver:step())
    assert(moves==0 and looks==1 and cameras==1,'active skill must suppress movement after same-frame camera handling')
end

for _,mode in ipairs({'restored','faulted','replacement'})do
    local receipt={}
    local moves,looks=0,0
    local session={state='ACTIVE',receipt=receipt,restores=0,
        bridge={
            verify_control=function()return true end,
            move=function(_,current)assert(current==receipt);moves=moves+1;return true end,
            look=function(_,current)assert(current==receipt);looks=looks+1;return true end,
            update_camera=function()error('obsolete frame must not update camera')end
        }}
    function session:poll()return true end
    function session:restore()
        self.restores=self.restores+1
        self.state='OFF'
        self.receipt=nil
        return true
    end
    function session:flush_buffered_skill()
        if mode=='restored'then self:restore()
        elseif mode=='faulted'then self.state='FAULTED'
        else self.receipt={}end
        return true
    end
    local driver=Driver.new(session,{read_input=function()
        return{allowed=true,forward=true,yaw_degrees=0,look_yaw=2}
    end})
    assert(not driver:step(),mode)
    assert(moves==0 and looks==0,'stale frame reached bridge input: '..mode)
    assert(session.restores==1,'restore must happen once: '..mode)
end

do
    local receipt={remote_control={}}
    local fresh,remote_reads=0,0
    local pc={GetControlRotation=function()return{Yaw=0}end,
        GetInputMouseDelta=function(_,x,y)x.DeltaX=0;y.DeltaY=0 end,
        IsInputKeyDown=function()return false end,
        IsMoveInputIgnored=function()return true end}
    local bridge={maintenance_verifies_control=true,
        maintain_control=function(_,r)assert(r==receipt);return true,nil,pc end,
        check=function(_,r)assert(r==receipt);fresh=fresh+1;return pc end,
        api={remote={verify=function(_,ticket)
            assert(ticket==receipt.remote_control);remote_reads=remote_reads+1;return true
        end}}}
    local input=require('ue_input').new(bridge,
        {make_name=function(key)return key end,game_paused=function(value)assert(value==pc);return false end},
        {input_verified=true,mouse_scale=.22})
    local session={state='ACTIVE',receipt=receipt,bridge=bridge,poll=function()return true end}
    function session:restore(why)error(why)end
    local driver=Driver.new(session,{read_input=function(...)return input:read(...)end})
    assert(driver:step() and fresh==0 and remote_reads==0)
    assert(input:read(receipt).allowed and fresh==1 and remote_reads==1,
        'input outside the maintained frame must check controller and remote ownership again')
end

print('PASS buffered skill activity suppresses movement and stale frames cannot be reused')
