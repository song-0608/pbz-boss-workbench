local root=assert(arg[1],'project required')
package.path=root..'/tools/?.lua;'..root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local Adapter=require('boss_defense_bridge')
local total=0
local function test(name,fn)fn();total=total+1;print('PASS '..name)end
local function fixture()
    local f={now=0,focus=true,world=true,stance=true,active=0,activations=0,cancels=0}
    local cls={};local ability={IsA=function()return f.stance end,GetClass=function()return cls end}
    local spec={Ability=ability};local asc={}
    local r={world_id='lease|world',boss={name='Boss One',address=32},input_enabled=true}
    local b={active_receipt=r}
    function b:check(receipt)assert(f.world and receipt==r,'changed world');return{}end
    function b:spec(receipt)assert(receipt==r);return spec,f.active,asc end
    function b:verify_control(receipt)return receipt==r end
    b.calls={activate=function(_,actual,actual_class)
        assert(actual==asc and actual_class==cls);f.activations=f.activations+1;f.active=1;return true end,
        cancel=function(_,actual)assert(actual==spec);f.cancels=f.cancels+1;f.active=0;return true end}
    f.bridge=b;f.receipt=r;f.contract={developer_only=true,declaration_verified=true,class_path='/Fixture.Stance_C',
        active_count_field='ActiveCount',cancel_binding_verified=true,cancel_function='K2_CancelAbility'}
    f.attach=function()return Adapter.attach(b,r,f.contract,function()return f.now end,function()return f.focus end)end
    return f
end
test('unique granted NPC stance uses original activation and exact cancellation',function()
    local f=fixture();local d=f.attach();assert(d==f.receipt.native_defense)
    d:step({down=false,allowed=true});assert(d:step({down=true,allowed=true}))
    assert(f.activations==1 and f.active==1);assert(d:step({down=false,allowed=true}))
    assert(f.cancels==1 and f.active==0)
end)
test('missing developer gate and active or wrong-ancestry stance never attach',function()
    for _,mode in ipairs({'gate','active','ancestry'})do
        local f=fixture()
        if mode=='gate'then f.contract.developer_only=false elseif mode=='active'then f.active=1 else f.stance=false end
        assert(not pcall(f.attach));assert(f.activations==0 and f.receipt.native_defense==nil)
    end
end)
test('native input permission loss releases the owned stance',function()
    local f=fixture();local d=f.attach();d:step({down=false,allowed=true});d:step({down=true,allowed=true})
    f.focus=false;assert(not d:step({down=true,allowed=true}));assert(f.cancels==1 and f.active==0)
end)
test('old receipt and changed world never reach native cancellation',function()
    for _,mode in ipairs({'world','receipt'})do
        local f=fixture();local d=f.attach();d:step({down=false,allowed=true});d:step({down=true,allowed=true})
        if mode=='world'then f.world=false else f.bridge.active_receipt={}end
        assert(not pcall(d.release,d,'restore'));assert(f.cancels==0 and d.owned)
    end
end)
test('grant changed to non NPC type rejects subsequent activation',function()
    local f=fixture();local d=f.attach();d:step({down=false,allowed=true});f.stance=false
    assert(not pcall(d.step,d,{down=true,allowed=true}));assert(f.activations==0)
end)
test('a live defense controller cannot be replaced by a second adapter',function()
    local f=fixture();f.attach();assert(not pcall(f.attach));assert(f.activations==0)
end)
print('Defense native adapter fixtures: '..total..'; not a live grant verification')
