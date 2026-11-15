-- 用途：仅供显式开发死亡验收，在原生Kill前回读本次技能活动；不发招、不改血量、不调用死亡接口。
local Guard={}
function Guard.activity(session,bridge,require_active)
    assert(session.state=='ACTIVE'and session.receipt,'active control receipt required')
    if not require_active then
        assert(not session.current_skill,'idle active boss required')
        return nil
    end
    local token=assert(session.current_skill,'owned skill must already be running')
    local record=assert(bridge.tokens[token],'tracked skill token required')
    assert(record.receipt==session.receipt and record.id=='skill_08','exact current-session skill08 required')
    local _,active=bridge:spec(session.receipt,bridge:definition(record.id))
    assert(math.type(active)=='integer'and active>0 and active<=255,'skill08 is not actually active')
    return record.id,active
end
return Guard
