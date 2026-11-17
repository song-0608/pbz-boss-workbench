-- 用途：只读核对当前玩家阵营与锁定组件，同时记录引擎真实枚举，不创建或修改角色。
ExecuteWithDelay(1000,function()ExecuteInGameThread(function()
    local ok,why=pcall(function()
        local function log(k,v)print('PBZ_COMBAT_CONTRACT:'..k..'='..tostring(v)..'\n')end
        local enum=StaticFindObject('/Script/AIModule.ETeamAttitude')
        assert(enum and enum:IsValid(),'team attitude enum missing')
        enum:ForEachName(function(name,value)log('ENUM',name:ToString()..'|'..value)end)
        local count=0
        for _,pc in ipairs(FindAllOf('PBZPlayerController')or{})do
            if pc:IsValid()and pc.Pawn and pc.Pawn:IsValid()and pc:GetFullName():find(':PersistentLevel.',1,true)then
                count=count+1
                local player=pc.Pawn
                log('PLAYER',player:GetFullName())
                local velocity=player:GetVelocity()
                log('PLAYER_VELOCITY',string.format('%.6f,%.6f,%.6f',velocity.X,velocity.Y,velocity.Z))
                local faction=player['Faction Component'];assert(faction and faction:IsValid(),'player faction missing')
                log('PLAYER_FACTION',faction:GetCurrnetFaction().TagName:ToString())
                local target=player:GetTargetingComponent();assert(target and target:IsValid(),'player targeting missing')
                log('PLAYER_TARGETING',target:GetFullName())
                log('PLAYER_TARGET_SOCKET',target.LockTarget.SocketName:ToString())
                local component=target.LockTarget.Component
                log('PLAYER_TARGET_COMPONENT',component and component:IsValid()and component:GetFullName()or'None')
                local attrs=player.AttributeSetBase
                if attrs and attrs:IsValid()then log('PLAYER_ATTRIBUTE_CLASS',attrs:GetClass():GetFullName())end
            end
        end
        assert(count==1,'unique gameplay player required')
        log('PASS','read only faction and component query')
    end)
    if not ok then print('PBZ_COMBAT_CONTRACT:ISSUE='..tostring(why)..'\n')end
end)end)
