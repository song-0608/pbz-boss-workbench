-- 用途：仅核对独立镜头需要的本机枚举；不创建角色、摄像机或修改游戏对象。
ExecuteWithDelay(1500,function()ExecuteInGameThread(function()
    local ok,why=pcall(function()
        for _,path in ipairs({"/Script/Engine.EAttachmentRule","/Script/Engine.ECollisionChannel",
            "/Script/Engine.ESpawnActorCollisionHandlingMethod","/Script/Engine.ESpawnActorScaleMethod"})do
            local value=StaticFindObject(path)
            assert(value and value:IsValid(),"enum missing: "..path)
            value:ForEachName(function(name,number)
                print("PBZ_CAMERA_CONTRACT:ENUM="..path.."|"..name:ToString().."|"..number.."\n")
            end)
        end
        print("PBZ_CAMERA_CONTRACT:PASS=enum query only\n")
    end)
    if not ok then print("PBZ_CAMERA_CONTRACT:ISSUE="..tostring(why).."\n")end
end)end)
