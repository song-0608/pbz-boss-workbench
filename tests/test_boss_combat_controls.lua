local root=assert(arg[1]);package.path=root..'/tools/?.lua;'..root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local Controls=require('boss_combat_controls')
local total=0
local function test(name,fn)fn();total=total+1;print('PASS '..name)end
local function fixture()
    local f={now=0,focused=true,down=false,allowed=true,active=0,casts=0,cancels=0,restores=0,clears=0}
    local r={world_id='world|lease',boss={name='Boss',address=2},input_enabled=true}
    local ability={IsA=function()return true end,GetClass=function()return{}end}
    local spec={Ability=ability}
    local b={check=function(_,receipt)assert(receipt==r)end,verify_control=function()return true end}
    function b:spec()f.spec_reads=(f.spec_reads or 0)+1;return spec,f.active,{}end
    b.calls={activate=function()f.active=1;return true end,
        cancel=function()f.cancels=f.cancels+1;if f.cancel_error then return false end;f.active=0;return true end}
    function b:verify_restored(receipt)
        assert(receipt==r);self.active_receipt=nil;return f.active==0
    end
    local s={state='OFF',config={controls={enter='F6'},skills={one={key='F1',verified=true}}},bridge=b}
    function s:enter()self.receipt=r;b.active_receipt=r;self.state='ACTIVE';r.input_enabled=true;return true end
    function s:restore()
        f.restores=f.restores+1;r.input_enabled=false
        if b:verify_restored(r)then self.receipt=nil;self.state='OFF';return true end
        self.state='FAULTED';return false,'restore failed'
    end
    function s:skill()f.casts=f.casts+1;return true end
    function s:request_skill(slot)return self:skill(slot)end
    function s:flush_buffered_skill()if self.buffered_skill then self.buffered_skill=nil;return self:skill('one')end;return true end
    function s:clear_buffered_skill()self.buffered_skill=nil;f.clears=f.clears+1 end
    local options={developer_only=true,now=function()return f.now end,input_allowed=function()return f.focused end,
        input_binding_verified=true,focus_binding_verified=true,
        read_defense=function()return{down=f.down,allowed=f.allowed}end,
        defense={key='RIGHT_MOUSE_BUTTON',developer_only=true,declaration_verified=true,
            class_path='/Fixture.Stance',active_count_field='ActiveCount',cancel_binding_verified=true,
            cancel_function='K2_CancelAbility'}}
    f.session=s;f.options=options;f.receipt=r;f.attach=function()return Controls.attach(s,options)end
    return f
end
test('defense requires explicit focus/key source and cannot shadow existing controls',function()
    for _,mode in ipairs({'focus','input','control','skill'})do
        local f=fixture()
        if mode=='focus'then f.options.focus_binding_verified=false
        elseif mode=='input'then f.options.input_binding_verified=false
        elseif mode=='control'then f.options.defense.key='F6'
        else f.options.defense.key='F1'end
        assert(not pcall(f.attach));assert(f.session.native_combat_controls==nil)
    end
end)
test('held defense blocks immediate requests and buffered casts then restores native ability',function()
    local f=fixture();local c=f.attach();assert(f.session:enter());f.session:sample_combat_input({allowed=true})
    f.down=true;f.session:sample_combat_input({allowed=true});assert(f.active==1)
    f.session.buffered_skill=true;assert(not f.session:request_skill('one'));assert(f.session.buffered_skill==nil)
    f.session.buffered_skill=true;assert(f.session:flush_buffered_skill());assert(f.casts==0 and f.session.buffered_skill==nil)
    assert(f.session:restore());assert(f.cancels==1 and c.receipt==nil and f.session.state=='OFF')
end)
test('idle frames sample defense once and skip the native stance grant scan',function()
    local f=fixture();local samples=0
    local read=f.options.read_defense
    f.options.read_defense=function(...)samples=samples+1;return read(...)end
    f.attach();assert(f.session:enter());assert(f.spec_reads==1)
    for _=1,120 do
        assert(f.session:sample_combat_input({allowed=true}))
        assert(f.session:flush_buffered_skill())
    end
    assert(samples==120 and f.spec_reads==1)
    f.down=true;assert(f.session:sample_combat_input({allowed=true}));assert(f.active==1 and f.spec_reads>1)
    f.down=false;assert(f.session:sample_combat_input({allowed=true}));assert(f.active==0 and f.cancels==1)
end)
test('sampled suspension releases stance and key must cycle after focus returns',function()
    local f=fixture();f.attach();f.session:enter();f.session:sample_combat_input({allowed=true})
    f.down=true;f.session:sample_combat_input({allowed=true});assert(f.active==1)
    f.session:sample_combat_input({allowed=false});assert(f.active==0 and f.cancels==1)
    f.session:sample_combat_input({allowed=true});assert(f.active==0)
    f.down=false;f.session:sample_combat_input({allowed=true});f.down=true
    f.session:sample_combat_input({allowed=true});assert(f.active==1)
end)
test('current skill prevents native stance activation without ending that skill',function()
    local f=fixture();f.attach();f.session:enter();f.session:sample_combat_input({allowed=true})
    f.session.current_skill='token';f.down=true;f.session:sample_combat_input({allowed=true});assert(f.active==0)
    assert(f.session.current_skill=='token');f.session.current_skill=nil;f.now=.2
    f.session:sample_combat_input({allowed=true});assert(f.active==1)
end)
test('background request releases owned stance and never casts a skill',function()
    local f=fixture();f.attach();f.session:enter();f.session:sample_combat_input({allowed=true})
    f.down=true;f.session:sample_combat_input({allowed=true});f.focused=false
    assert(not f.session:request_skill('one'));assert(f.active==0 and f.casts==0)
end)
test('cleanup failure attempts player restore but retains receipt and permits retry',function()
    local f=fixture();local c=f.attach();f.session:enter();f.session:sample_combat_input({allowed=true})
    f.down=true;f.session:sample_combat_input({allowed=true});f.cancel_error=true
    assert(not f.session:restore());assert(f.restores==1 and c.cleanup_pending and c.receipt==f.receipt)
    assert(f.session.state=='FAULTED');f.cancel_error=false
    assert(f.session:restore());assert(f.session.state=='OFF'and c.receipt==nil)
end)
test('a new receipt re-arms only after release and never reuses previous input state',function()
    local f=fixture();f.attach();f.session:enter();f.session:sample_combat_input({allowed=true})
    assert(f.session:restore());f.down=true;assert(f.session:enter())
    f.session:sample_combat_input({allowed=true});assert(f.active==0)
    f.down=false;f.session:sample_combat_input({allowed=true});assert(f.session:skill('one'));assert(f.casts==1)
end)
test('missing grant fails entry and still invokes original player restoration',function()
    local f=fixture();f.session.bridge.spec=function()error('stance not granted')end
    local c=f.attach();assert(not f.session:enter());assert(f.restores==1 and f.session.state=='OFF'and c.receipt==nil)
end)
test('the live movement driver respects combat focus permission before movement or buffered cast',function()
    local f=fixture();f.attach();f.session:enter();f.session.poll=function()return true end
    local moves=0;f.session.bridge.move=function()moves=moves+1;return true end
    f.session.bridge.update_camera=function()return true end
    local Driver=assert(loadfile(root..'/tools/player_input_driver.lua'))()
    local driver=Driver.new(f.session,{read_input=function()
        return{allowed=true,forward=true,yaw_degrees=0}
    end})
    assert(driver:step());assert(moves==1)
    f.focused=false;f.session.buffered_skill=true
    assert(driver:step());assert(moves==1 and f.casts==0 and f.session.buffered_skill==nil)
    f.focused=true;assert(driver:step());assert(moves==2)
end)
test('defense native rejection does not block walking or force a fake successful guard',function()
    local f=fixture();f.attach();f.session:enter();f.session.poll=function()return true end
    f.session.bridge.calls.activate=function()return false end
    local moves=0;f.session.bridge.move=function()moves=moves+1;return true end
    f.session.bridge.update_camera=function()return true end
    local Driver=assert(loadfile(root..'/tools/player_input_driver.lua'))()
    local driver=Driver.new(f.session,{read_input=function()
        return{allowed=true,forward=true,yaw_degrees=0}
    end})
    assert(driver:step());f.down=true;assert(driver:step())
    assert(moves==2 and f.active==0 and f.session.state=='ACTIVE')
end)
test('unexpected World retirement forgets a disposed stance without native cancellation',function()
    local f=fixture()
    f.session.world_boundary=function(self)
        f.receipt.world_retired=true;self.state='OFF';self.receipt=nil;self.bridge.active_receipt=nil
        return'retired'
    end
    local c=f.attach();f.session:enter();f.session:sample_combat_input({allowed=true})
    f.down=true;f.session:sample_combat_input({allowed=true});assert(f.active==1)
    assert(f.session:world_boundary()=='retired')
    assert(c.receipt==nil and f.receipt.native_defense==nil and f.cancels==0)
end)
test('restore classifies retired World before attempting any stale defense cleanup',function()
    local f=fixture();local context_checks=0
    f.session.world_boundary=function(self)
        f.receipt.world_retired=true;self.state='OFF';self.receipt=nil;self.bridge.active_receipt=nil
        return'retired'
    end
    local c=f.attach();f.session:enter();f.session:sample_combat_input({allowed=true})
    f.down=true;f.session:sample_combat_input({allowed=true});assert(f.active==1)
    f.session.bridge.check=function()context_checks=context_checks+1;error('old World')end
    assert(f.session:restore());assert(context_checks==0 and f.cancels==0 and f.restores==0)
    assert(f.session.state=='OFF'and c.receipt==nil and not c.cleanup_pending)
end)
test('pending World restore preserves ownership without calling the previous native ability',function()
    local f=fixture();local pending=false;local context_checks=0
    f.session.world_boundary=function(self)
        if pending then self.state='TRANSITIONING';return'pending'end
        return'same'
    end
    local restore=f.session.restore
    f.session.restore=function(self,...)
        if self:world_boundary()~='same'then return false,'world transition pending or unverified'end
        return restore(self,...)
    end
    local c=f.attach();f.session:enter();f.session:sample_combat_input({allowed=true})
    f.down=true;f.session:sample_combat_input({allowed=true});pending=true
    f.session.bridge.check=function()context_checks=context_checks+1;error('old World')end
    assert(not f.session:restore());assert(context_checks==0 and f.cancels==0 and f.restores==0)
    assert(c.receipt==f.receipt and c.defense.owned and f.session.state=='TRANSITIONING')
end)
test('failed disposal cleanup faults the session and can retry after base receipt retirement',function()
    local f=fixture()
    f.session.world_boundary=function(self)
        if self.receipt then
            f.receipt.world_retired=true;self.state='OFF';self.receipt=nil;self.bridge.active_receipt=nil
            return'retired'
        end
        return'same'
    end
    local restore=f.session.restore
    f.session.restore=function(self,...)
        if not self.receipt then self.state='OFF';return true end
        return restore(self,...)
    end
    local c=f.attach();f.session:enter();local fail=true;local attempts=0
    c.cue={retire=function()
        attempts=attempts+1;return not fail,{'hook removal pending'}
    end}
    local status,why=f.session:world_boundary()
    assert(status=='faulted'and why:find('hook removal pending',1,true))
    assert(f.session.state=='FAULTED'and c.receipt==f.receipt and c.disposal_verified)
    assert(not f.session:restore());assert(f.session.state=='FAULTED'and c.receipt==f.receipt)
    fail=false;assert(f.session:restore())
    assert(f.session.state=='OFF'and c.receipt==nil and attempts==3 and f.cancels==0)
end)
test('direct restore cannot report success when World retirement leaves combat hooks behind',function()
    local f=fixture()
    f.session.world_boundary=function(self)
        f.receipt.world_retired=true;self.state='OFF';self.receipt=nil;self.bridge.active_receipt=nil
        return'retired'
    end
    local c=f.attach();f.session:enter()
    c.cue={retire=function()return false,{'hook removal pending'}end}
    local ok,why=f.session:restore()
    assert(not ok and why:find('hook removal pending',1,true))
    assert(f.session.state=='FAULTED'and c.cleanup_pending and c.receipt==f.receipt)
    assert(f.restores==0 and f.cancels==0)
end)
test('production Session restores across pending and retired Worlds with retryable hook disposal',function()
    local Base=require('session')
    for _,fail_hook in ipairs({false,true})do
        local f=fixture();local phase='pending';local hook_failed=fail_hook
        f.session.restore=Base.restore;f.session.world_boundary=Base.world_boundary
        f.session.record=Base.record;f.session.diagnostics={};f.session.world_id='world|lease'
        function f.session.bridge:world_boundary(receipt)
            assert(receipt==f.receipt)
            if phase=='pending'then return'pending','old objects not yet disposed',1 end
            self.active_receipt=nil;receipt.world_retired=true
            return'retired'
        end
        local c=f.attach();f.session:enter();f.session:sample_combat_input({allowed=true})
        f.down=true;f.session:sample_combat_input({allowed=true})
        c.cue={retire=function()return not hook_failed,{'hook removal pending'}end}
        f.session.bridge.check=function()error('previous World must not be queried')end
        assert(not f.session:restore());assert(f.session.state=='TRANSITIONING'and c.defense.owned)
        phase='retired';local ok=f.session:restore()
        if fail_hook then
            assert(not ok and f.session.state=='FAULTED'and not f.session.receipt)
            hook_failed=false;assert(f.session:restore())
        else assert(ok)end
        assert(f.session.state=='OFF'and c.receipt==nil and not c.cleanup_pending and f.cancels==0)
    end
end)
test('native helper supplies the monotonic clock and fresh fixed-key sample without editing the contract',function()
    local f=fixture()
    f.options.native_input={binding_verified=true,pid=42}
    f.options.globals={PBZNativeCombatInputSnapshot=function()
        return{schema=1,pid=42,now=f.now,allowed=f.focused,down=f.focused and f.down}
    end}
    f.options.input_binding_verified=nil;f.options.focus_binding_verified=nil
    f.options.read_defense=function()error('legacy sampler must be replaced')end
    f.attach();f.session:enter();assert(f.session:sample_combat_input({allowed=true}))
    f.down=true;f.now=.1;assert(f.session:sample_combat_input({allowed=true}));assert(f.active==1)
    f.focused=false;assert(not f.session:sample_combat_input({allowed=true}));assert(f.active==0)
    assert(f.options.focus_binding_verified==nil,'caller contract must remain immutable')
end)
print('Native combat arbitration fixtures: '..total..'; no live defense or visual acceptance')
