-- 用途：创建临时CameraActor与Boss所属的SpringArm；所有操作均需核对当前PBZ反射声明。
-- 不能使用旧UWorld:SpawnActor封装：本构建FinishSpawningActor多出Scale参数，须显式传入。
local Native = {}

function Native.new(g,binding)
    g=g or _G
    assert(binding and binding.binding_verified==true,"verified native camera contracts required")
    local lifecycle=require('object_lifecycle').new(g,binding)
    local function find(path)
        local value=g.StaticFindObject(path)
        assert(value and value:IsValid(),"missing camera dependency: "..path)
        return value
    end
    local function libraries()
        return find("/Script/Engine.Default__GameplayStatics"),find("/Script/Engine.Default__KismetMathLibrary")
    end
    return {
        spawn_camera=function(pc,boss,config)
            local statics,maths=libraries()
            local location=boss:K2_GetActorLocation()
            local transform=maths:MakeTransform({X=location.X,Y=location.Y,Z=location.Z},
                {Pitch=0,Yaw=0,Roll=0},{X=1,Y=1,Z=1})
            local camera=statics:BeginDeferredActorSpawnFromClass(pc,find("/Script/Engine.CameraActor"),
                transform,binding.spawn_collision,nil,binding.spawn_scale)
            assert(lifecycle:usable(camera),"temporary camera spawn rejected")
            -- 用途：Begin之后立即返回仍是deferred actor的清理句柄；Finish由挂接步骤完成。
            return camera
        end,
        attach_boom=function(camera,boss,config,checkpoint)
            local statics,maths=libraries()
            local location=boss:K2_GetActorLocation()
            local transform=maths:MakeTransform({X=location.X,Y=location.Y,Z=location.Z},
                {Pitch=0,Yaw=0,Roll=0},{X=1,Y=1,Z=1})
            local finished=statics:FinishSpawningActor(camera,transform,binding.spawn_scale)
            assert(finished and finished:IsValid() and finished:GetAddress()==camera:GetAddress(),"camera finish mismatch")
            local relative=maths:MakeTransform({X=0,Y=0,Z=0},
                {Pitch=0,Yaw=0,Roll=0},{X=1,Y=1,Z=1})
            -- 用途：臂归属Boss，原生碰撞查询才能忽略Boss自身；若归属摄像机，会撞到Boss胶囊体。
            local boom=boss:AddComponentByClass(find("/Script/Engine.SpringArmComponent"),true,relative,false)
            assert(boom and boom:IsValid(),"spring arm component not created")
            checkpoint(boom) -- 用途：之后挂接失败也能删除刚加的组件，不遗留到原Boss身上。
            assert(boom:K2_AttachToComponent(boss.RootComponent,g.FName("None"),
                binding.keep_relative,binding.keep_relative,binding.keep_world,false)==true,"spring arm attach failed")
            -- 用途：相机臂跟随Boss位置，但采用玩家控制旋转，不随Boss招式的身体旋转甩镜头。
            boom:SetAbsolute(false,true,true)
            boom.TargetArmLength=config.distance
            boom.TargetOffset={X=0,Y=0,Z=config.pivot_height or 80}
            boom.SocketOffset={X=0,Y=config.shoulder_offset or 45,Z=0}
            boom.bUsePawnControlRotation=false
            boom.bDoCollisionTest=true
            boom.ProbeSize=config.probe_size or 14
            boom.ProbeChannel=binding.camera_channel
            local component=camera.CameraComponent
            assert(component and component:IsValid(),"camera component missing")
            assert(component:K2_AttachToComponent(boom,g.FName("SpringEndpoint"),binding.snap,binding.snap,
                binding.keep_world,false)==true,"camera component attach failed")
            component.bConstrainAspectRatio=false
            component.bUsePawnControlRotation=false
            component:SetFieldOfView(config.fov or 90)
            return boom,component
        end,
        rotate_boom=function(boom,rotation)
            -- 用途：通过引擎函数更新世界变换；不直接改RelativeRotation字段冒充变换已更新。
            local hit={}
            boom:K2_SetWorldRotation(rotation,false,hit,true)
        end,
        destroy_camera=function(camera)
            -- 用途：本构建销毁后IsActorBeingDestroyed会返回false；以显式引擎有效性查询为准。
            if lifecycle:usable(camera)then camera:K2_DestroyActor()end
            assert(not lifecycle:usable(camera),'camera actor remains engine-usable after destruction')
            return true
        end,
        destroy_boom=function(boom,boss)
            -- 用途：注销Tick与启用标记是两件事；先关闭本Mod组件Tick，再销毁并分别回读。
            if not lifecycle:usable(boom)then return true end
            boom:SetComponentTickEnabled(false)
            assert(boom:IsComponentTickEnabled()==false,'owned camera arm tick could not be disabled')
            boom:K2_DestroyComponent(boss)
            -- 用途：销毁后不继续调用失效组件的原生方法；Tick在销毁前关闭并回读，之后确认引擎判为失效。
            assert(not lifecycle:usable(boom),'camera arm remains engine-usable after destruction')
            return true
        end,
    }
end

return Native
