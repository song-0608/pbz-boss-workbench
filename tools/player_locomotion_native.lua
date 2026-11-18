local Native={}
function Native.new(g,binding)
    assert(binding and binding.locomotion_verified==true,'fresh walking metadata required')
    local statics=g.StaticFindObject('/Script/Engine.Default__GameplayStatics')
    assert(statics and statics:IsValid(),'native frame-time library unavailable')
    local function component(boss)
        assert(boss and boss:IsValid()and boss:IsA('/Script/Engine.Character'),'current character required')
        local movement=boss.CharacterMovement
        assert(movement and movement:IsValid()and movement:IsA('/Script/Engine.CharacterMovementComponent'),
            'current character movement required')
        assert(movement:GetOwner():GetAddress()==boss:GetAddress(),'foreign movement component rejected')
        return movement
    end
    return{binding_verified=true,
        read=function(boss)local m=component(boss);return{speed=m.MaxWalkSpeed,acceleration=m.MaxAcceleration}end,
        write=function(boss,state)
            local m=component(boss);local problems={}
            for key,field in pairs({speed='MaxWalkSpeed',acceleration='MaxAcceleration'})do
                if state[key]~=nil then
                    local ok,why=pcall(function()m[field]=state[key]end)
                    if not ok then problems[#problems+1]=tostring(why)end
                end
            end
            assert(#problems==0,table.concat(problems,'; '))
        end,
        yaw=function(boss)local f=boss:GetActorForwardVector();return math.deg(math.atan(f.Y,f.X))end,
        face=function(boss,yaw)
            component(boss)
            local rotation={Pitch=0,Yaw=yaw,Roll=0}
            boss.RootComponent:K2_SetWorldRotation(rotation,false,{},true)
            boss:GetController():SetControlRotation(rotation)
            local forward=boss:GetActorForwardVector();local radians=math.rad(yaw)
            assert(forward.X*math.cos(radians)+forward.Y*math.sin(radians)>0.999,'native facing did not verify')
        end,
        frame_seconds=function(boss)return statics:GetWorldDeltaSeconds(boss)end}
end
return Native
