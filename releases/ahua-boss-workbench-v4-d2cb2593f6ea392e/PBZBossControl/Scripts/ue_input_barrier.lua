-- 用途：只操作自建Actor的EnableInput/DisableInput及其反射属性，按键仍由UE4SS和原始键状态读取。
local Native={}
function Native.new(binding)
    assert(binding and binding.binding_verified,'current input barrier contract required')
    local function valid(x)return x and x:IsValid()end
    return{
        empty=function(owner)return not valid(owner.InputComponent)end,
        enable=function(owner,pc)
            owner.bBlockInput=true;owner.InputPriority=10000;owner:EnableInput(pc)
        end,
        verify=function(owner)
            local input=owner.InputComponent
            return owner.bBlockInput==true and owner.InputPriority==10000 and valid(input)
            -- 用途：组件内部优先级和阻断位不参与反射；此处只证明原生创建成功，消费行为另做实机输入验证。
        end,
        disable=function(owner,pc)owner:DisableInput(pc)end,
    }
end
return Native
