-- 用途：当前进程已核对的视线查询与只读状态输出；屏幕层由配套启动器渲染。
local Native={}
local function json_string(value)
    return '"'..value:gsub('[%z\1-\31\\"]',function(c)
        if c=='"'then return '\\"'elseif c=='\\'then return '\\\\'end
        return string.format('\\u%04x',string.byte(c))
    end)..'"'
end
function Native.new(g,binding,attest)
    assert(binding and binding.binding_verified==true,'current player UI contract required')
    assert(type(attest)=='function','bounded status lease required')
    local closed=false
    local visibility_state,visibility_samples={},0
    return {
        visible=function(boss,target)
            local controller=boss:GetController()
            assert(controller and controller:IsValid(),'controlled boss AI controller missing')
            -- 零向量明确使用引擎的Controller视点规则；不从隐藏主角位置做视线检测。
            local visible=controller:LineOfSightTo(target,{X=0,Y=0,Z=0},false)==true
            local key=boss:GetFullName()..'|'..target:GetFullName()
            if visibility_state[key]~=visible and visibility_samples<128 then
                visibility_state[key]=visible;visibility_samples=visibility_samples+1
                -- 仅诊断：比较显式Boss中心与Controller默认视点，绝不以替代结果放宽视线门槛。
                local ok,diagnostic=pcall(function()
                    local b,c,t=boss:K2_GetActorLocation(),controller:K2_GetActorLocation(),target:K2_GetActorLocation()
                    return string.format('default=%s|boss_center=%s|boss=%.3f,%.3f,%.3f|controller=%.3f,%.3f,%.3f|target=%.3f,%.3f,%.3f',
                        tostring(visible),tostring(controller:LineOfSightTo(target,b,false)==true),b.X,b.Y,b.Z,c.X,c.Y,c.Z,t.X,t.Y,t.Z)
                end)
                g.print('PBZ_PLAYER_UI:VISIBILITY_DIAGNOSTIC='..key..'|'..tostring(diagnostic)..'|readable='..tostring(ok)..'\n')
            end
            return visible
        end,
        now=os.time,
        render=function(pc,value)
            assert(not closed,'HUD closed')
            local grant=attest()
            assert(grant and grant.offline and grant.isolated and grant.expires_at>os.time(),'status lease expired')
            assert(type(value)=='string'and #value<=4096,'bounded HUD text required')
            g.print('PBZ_PLAYER_UI:STATUS={"at":'..os.time()..',"session":'..json_string(grant.session_id)
                ..',"expires_at":'..grant.expires_at..',"player":'..json_string(pc:GetFullName())
                ..',"text":'..json_string(value)..'}\n')
        end,
        health=function(pawn)return pawn.AttributeSetBase.Health.CurrentValue end,
        name=function(pawn)
            return pawn['Actor Config']:GetCharacterName():ToString()
        end,
        close=function()
            closed=true
        end,
    }
end
return Native
