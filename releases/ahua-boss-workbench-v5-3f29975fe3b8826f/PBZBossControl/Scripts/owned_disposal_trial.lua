-- 开发验收：同一游戏线程内，只销毁正在执行技能08的精确自建Actor。
-- 销毁后不再解引用Spec或技能实例；由现有失效对象恢复路径处理主角。
local Trial={}
function Trial.run(session,bridge,calls,owned,lifecycle,log)
    local id,count=require('death_trial_guard').activity(session,bridge,true)
    local boss=calls:resolve(session.receipt.boss)
    assert(calls:same(boss,calls:resolve(owned)),'exact owned disposal identity required')
    local definition=bridge:definition(id)
    local spec,active=bridge:spec(session.receipt,definition)
    assert(active==count and active>0,'disposal activity changed')
    local expected=spec.Ability:GetClass():GetFullName()
    assert(expected:match('^[^ ]+ (.+)$')==definition.class_path,'disposal class mismatch')
    local found
    for _,field in ipairs({'NonReplicatedInstances','ReplicatedInstances'})do
        local instances=spec[field];local size=instances:GetArrayNum()
        assert(math.type(size)=='integer'and size>=0 and size<=64,'bounded disposal instance list required')
        for i=1,size do
            assert(i<=instances:GetArrayNum(),'disposal instance list changed')
            local instance=instances[i]
            if lifecycle:usable(instance)and instance.bIsActive==true
                and instance:GetClass():GetFullName()==expected then
                assert(not found,'ambiguous disposal active instance');found=instance
            end
        end
    end
    assert(found and not found:GetFullName():find('Default__',1,true),'exact active non-CDO instance required')
    log('OWNED_DISPOSAL_ACTIVE_INSTANCE',id..'|active='..active..'|object='..found:GetFullName())
    log('OWNED_DISPOSAL_REQUEST',boss:GetFullName()..'|address='..boss:GetAddress())
    boss:K2_DestroyActor()
    assert(not lifecycle:usable(boss),'owned Actor remains engine-usable after destruction')
    log('OWNED_DISPOSAL_ENGINE_UNUSABLE',true)
    return true
end
return Trial
