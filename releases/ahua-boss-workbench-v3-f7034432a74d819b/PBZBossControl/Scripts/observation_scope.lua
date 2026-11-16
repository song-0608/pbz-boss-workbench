-- 用途：给延迟只读采样绑定当前控制凭据；F10退出或再次接管后，旧采样自行停止。
-- 只判断会话边界，不捕获异常、不屏蔽当前控制中的真实故障。
local Scope={};Scope.__index=Scope
function Scope.capture(session)
    assert(session and session.state=='ACTIVE' and type(session.receipt)=='table','active observation receipt required')
    return setmetatable({session=session,receipt=session.receipt},Scope)
end
function Scope:current()
    return self.session.state=='ACTIVE' and self.session.receipt==self.receipt
end
return Scope
