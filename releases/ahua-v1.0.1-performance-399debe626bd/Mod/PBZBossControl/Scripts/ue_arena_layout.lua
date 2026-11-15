local Native={}
function Native.new(g,binding,pc)
    assert(binding and binding.binding_verified==true,'current navigation contract required')
    local class=g.StaticFindObject('/Script/NavigationSystem.NavigationSystemV1')
    assert(class and class:IsValid(),'navigation class missing')
    local library=class:GetCDO()
    local system=library:GetNavigationSystem(pc)
    assert(system and system:IsValid(),'current World has no navigation system')
    return function(point)
        local out={X=0,Y=0,Z=0}
        local result=library:K2_ProjectPointToNavigation(pc,point,out,nil,nil,{X=100,Y=100,Z=250})
        assert(type(result)=='boolean','navigation result unreadable')
        if not result then return nil end
        assert(type(out.X)=='number'and type(out.Y)=='number'and type(out.Z)=='number','navigation output vector unreadable')
        return out
    end
end
return Native
