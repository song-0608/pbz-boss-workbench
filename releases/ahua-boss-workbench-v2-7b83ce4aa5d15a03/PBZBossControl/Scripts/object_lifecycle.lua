-- 用途：区分UE4SS仍持有弱引用包装、引擎仍允许使用对象和垃圾回收；不调用已失效包装里的地址。
local Lifecycle={}
function Lifecycle.new(g,binding)
    assert(binding and binding.binding_verified,'current engine validity declaration required')
    local library=g.StaticFindObject('/Script/Engine.Default__KismetSystemLibrary')
    local fn=g.StaticFindObject('/Script/Engine.KismetSystemLibrary:IsValid')
    assert(library and library:IsValid()and fn and fn:IsValid(),'engine validity query unavailable')
    local service={}
    function service:usable(object)
        -- 用途：GC后旧包装可能仍保存已经复用的地址，必须先检查UE4SS删除监听器维护的弱引用。
        if not(object and object:IsValid())then return false end
        -- 用途：显式调用反射函数，避免同名IsValid命中UE4SS包装的方法。
        local usable=library:CallFunction(fn,object)
        assert(type(usable)=='boolean','engine validity result unreadable')
        return usable
    end
    assert(service:usable(library)and not service:usable(nil),'engine validity controls failed')
    return service
end
return Lifecycle
