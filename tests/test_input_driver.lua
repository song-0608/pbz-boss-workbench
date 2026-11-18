-- 用途：测试输入方向、暂停和输入失败后的恢复；不读取真实键盘、不访问游戏。
local root = assert(arg[1], "project directory required")
package.path = root .. "/mod/PBZBossControl/Scripts/?.lua;" .. package.path
local Driver, UEInput = require("input_driver"), require("ue_input")
local total = 0
local function test(name, action)
    local ok, why = pcall(action);assert(ok,name .. ": " .. tostring(why));total=total+1;print("PASS "..name)
end
local function fixture(input)
    local session = { state = "ACTIVE", receipt = {}, moves = {}, looks = {}, restores = 0 }
    function session:poll() return true end
    function session:restore() self.restores=self.restores+1;self.state="OFF";return true end
    session.bridge = {
        verify_control = function() return true end,
        move = function(_, receipt,x,y,scale)
            assert(receipt==session.receipt);session.moves[#session.moves+1]={x=x,y=y,scale=scale};return true
        end,
        look = function(_,receipt,yaw,pitch)
            assert(receipt==session.receipt);session.looks[#session.looks+1]={yaw=yaw,pitch=pitch};return true
        end,
    }
    return Driver.new(session,{read_input=function()return input end}),session
end
test("diagonal movement remains unit length",function()
    local d,s=fixture({allowed=true,forward=true,right=true,yaw_degrees=0});assert(d:step())
    local v=s.moves[1];assert(math.abs(v.x*v.x+v.y*v.y-1)<1e-10)
end)
test("camera yaw rotates forward movement",function()
    local d,s=fixture({allowed=true,forward=true,yaw_degrees=90});assert(d:step())
    assert(math.abs(s.moves[1].x)<1e-10 and math.abs(s.moves[1].y-1)<1e-10)
end)
test("opposite held keys cancel",function()
    local d,s=fixture({allowed=true,forward=true,backward=true,yaw_degrees=0});assert(d:step());assert(#s.moves==0)
end)
test("pause or blocked input submits nothing",function()
    local d,s=fixture({allowed=false,forward=true});assert(d:step());assert(#s.moves==0 and #s.looks==0)
end)
test('pause menu restores before sending any further boss input',function()
    local d,s=fixture({allowed=false,paused=true,forward=true})
    assert(not d:step());assert(s.restores==1 and s.state=='OFF'and #s.moves==0)
end)
test("inactive control does not sample inputs",function()
    local d,s=fixture({allowed=true,forward=true,yaw_degrees=0});s.state="OFF"
    d.api.read_input=function()error("must not sample")end;assert(not d:step());assert(#s.moves==0)
end)
test("input failure restores rather than continuing to move",function()
    local d,s=fixture({});d.api.read_input=function()error("lost input source")end
    assert(not d:step());assert(s.restores==1 and #s.moves==0)
end)
test("invalid rotation does not submit movement",function()
    local d,s=fixture({allowed=true,forward=true,yaw_degrees=0/0});assert(not d:step())
    assert(s.restores==1 and #s.moves==0)
end)
test("look input routes to the controlled pawn",function()
    local d,s=fixture({allowed=true,yaw_degrees=0,look_yaw=2,look_pitch=-1});assert(d:step())
    assert(s.looks[1].yaw==2 and s.looks[1].pitch==-1)
end)
test("native input uses struct key and named scalar out parameters",function()
    local pc={}
    function pc:IsMoveInputIgnored()return false end
    function pc:IsLookInputIgnored()return false end
    function pc:IsInputKeyDown(key)return key.KeyName=="W" end
    function pc:GetControlRotation()return {Yaw=45}end
    function pc:GetInputMouseDelta(dx,dy)dx.DeltaX=4;dy.DeltaY=-2 end
    local input=UEInput.new({check=function()return pc end},{make_name=function(v)return v end,
        game_paused=function()return false end},{input_verified=true,mouse_scale=0.5}):read({})
    assert(input.forward and not input.backward and input.look_yaw==2 and input.look_pitch==-1 and input.yaw_degrees==45)
end)
test("unverified FKey binding is rejected",function()
    assert(not pcall(UEInput.new,{}, {make_name=function()end,game_paused=function()end},{input_verified=false}))
end)
test('fast finite mouse movement is bounded rather than rejecting control',function()
    local pc={IsMoveInputIgnored=function()return false end,IsLookInputIgnored=function()return false end,
        IsInputKeyDown=function()return false end,GetControlRotation=function()return{Yaw=0}end,
        GetInputMouseDelta=function(_,dx,dy)dx.DeltaX=4000;dy.DeltaY=-3000 end}
    local input=UEInput.new({check=function()return pc end},{make_name=function(v)return v end,
        game_paused=function()return false end},{input_verified=true,mouse_scale=0.1}):read({})
    assert(input.allowed and input.look_yaw==10 and input.look_pitch==-10)
end)
test("lost possession is detected without movement input",function()
    local d,s=fixture({allowed=true,yaw_degrees=0})
    s.bridge.verify_control=function()return false end
    assert(not d:step());assert(s.restores==1 and #s.moves==0)
end)
test('maintenance happens before strict verification and movement',function()
    local d,s=fixture({allowed=true,forward=true,yaw_degrees=0});local ready=false
    s.bridge.maintain_control=function(_,receipt)assert(receipt==s.receipt);ready=true;return true end
    s.bridge.verify_control=function()return ready end
    assert(d:step());assert(#s.moves==1 and s.restores==0)
end)
test('rejected maintenance restores without sampling player input',function()
    local d,s=fixture({allowed=true,forward=true,yaw_degrees=0})
    s.bridge.maintain_control=function()return false end
    d.api.read_input=function()error('must not sample after maintenance failure')end
    assert(not d:step());assert(s.restores==1 and #s.moves==0)
end)
test('buffer failure cannot move or turn an obsolete control receipt',function()
    for _,mode in ipairs({'restored','faulted','replacement'})do
        local d,s=fixture({allowed=true,forward=true,yaw_degrees=0,look_yaw=2})
        local cameras=0;s.bridge.update_camera=function()cameras=cameras+1;return true end
        s.flush_buffered_skill=function()
            if mode=='restored'then s:restore();s.receipt=nil
            elseif mode=='faulted'then s.state='FAULTED'
            else s.receipt={}end
            return true
        end
        assert(not d:step(),mode)
        assert(#s.moves==0 and #s.looks==0 and cameras==0,'no stale frame may reach bridge input: '..mode)
        assert(s.restores==1,'restore once, including when the buffered skill already restored')
    end
end)
test('successful buffered skill suppresses movement and keeps same-frame camera',function()
    local d,s=fixture({allowed=true,forward=true,yaw_degrees=0,look_yaw=2})
    s.flush_buffered_skill=function()s.current_skill='new native token';return true end
    assert(d:step());assert(#s.moves==0 and #s.looks==1 and s.restores==0)
end)
test('target-follow camera yaw takes precedence over sampled and post-look yaw',function()
    for _,look_yaw in ipairs({0,2})do
        local d,s=fixture({allowed=true,forward=true,yaw_degrees=0,look_yaw=look_yaw})
        s.bridge.look=function()return true,20 end
        s.bridge.update_camera=function()return true,90 end
        assert(d:step())
        assert(math.abs(s.moves[1].x)<1e-10 and math.abs(s.moves[1].y-1)<1e-10)
    end
end)
test('invalid post-camera yaw restores before moving',function()
    for _,yaw in ipairs({0/0,math.huge,'bad'})do
        local d,s=fixture({allowed=true,forward=true,yaw_degrees=0})
        s.bridge.update_camera=function()return true,yaw end
        assert(not d:step());assert(s.restores==1 and #s.moves==0)
    end
end)
print("Input driver fixtures: "..total.." passed; no runtime movement verification claimed.")
