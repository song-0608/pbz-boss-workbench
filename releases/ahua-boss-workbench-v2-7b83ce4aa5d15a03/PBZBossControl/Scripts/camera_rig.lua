-- 用途：管理Mod独立摄像机的创建、逐帧跟随和清理；不移动主角，也不借用其摄像机组件。
-- 镜头碰撞由原生SpringArm负责；引擎函数的具体调用放在另一个适配器内，便于单独核对声明。
local Rig = {}
Rig.__index = Rig

function Rig.new(calls, native, config)
    assert(type(native)=="table" and type(native.spawn_camera)=="function"
        and type(native.attach_boom)=="function" and type(native.rotate_boom)=="function"
        and type(native.destroy_camera)=="function" and type(native.destroy_boom)=="function",
        "camera native adapter incomplete")
    assert(type(config)=="table" and config.binding_verified==true,
        "camera parameter/property bindings must be verified")
    assert(type(config.distance)=="number" and config.distance>=150 and config.distance<=1200,
        "bounded third-person camera distance required")
    return setmetatable({calls=calls,native=native,config=config},Rig)
end

local function angle(value)
    assert(type(value)=="number" and value==value and math.abs(value)<10000000,"invalid camera angle")
    return (value+180)%360-180
end

function Rig:create(pc,boss,receipt)
    assert(not receipt.camera_rig,"camera rig already exists")
    local camera=self.native.spawn_camera(pc,boss,self.config)
    -- 用途：创建后立即记录清理责任；后续组件挂接失败，Bridge仍能恢复原镜头并删除自己的摄像机。
    local ticket={camera=self.calls:reference(camera),boss=self.calls:reference(boss),world=self.calls:world(boss),destroyed=false}
    receipt.camera_rig=ticket
    local boom,component=self.native.attach_boom(camera,boss,self.config,function(created)
        ticket.boom=self.calls:reference(created)
    end)
    ticket.boom=self.calls:reference(boom)
    ticket.component=self.calls:reference(component)
    self:update(pc,boss,ticket)
    return self.calls:resolve(ticket.camera)
end

function Rig:update(pc,boss,ticket)
    assert(ticket and not ticket.destroyed,"camera rig no longer active")
    local world=self.calls:world(boss)
    assert(world.name==ticket.world.name and world.address==ticket.world.address,"camera world changed")
    local rotation=pc:GetControlRotation()
    local pitch=math.max(self.config.min_pitch or -60,math.min(self.config.max_pitch or 20,angle(rotation.Pitch)))
    self.native.rotate_boom(self.calls:resolve(ticket.boom),{Pitch=pitch,Yaw=angle(rotation.Yaw),Roll=0})
    return true
end

function Rig:target(ticket) return self.calls:resolve(ticket.camera) end

function Rig:destroy(ticket)
    if not ticket or ticket.destroyed then return true end
    if not ticket.camera_destroyed then
        local camera=self.calls:optional(ticket.camera)
        if camera then assert(self.native.destroy_camera(camera)==true,'camera destruction not verified')end
        ticket.camera_destroyed=true
    end
    if ticket.boom and not ticket.boom_destroyed then
        local boom=self.calls:optional(ticket.boom)
        if boom then
            assert(self.native.destroy_boom(boom,self.calls:resolve(ticket.boss))==true,
                'camera arm destruction not verified')
        end
        ticket.boom_destroyed=true
    end
    ticket.destroyed=true
    return true
end

return Rig
