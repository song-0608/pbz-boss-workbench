-- Simulated native scheduling and live-grant boundary checks, never runtime acceptance.
local root,candidate,definition_path=assert(arg[1]),assert(arg[2]),assert(arg[3])
package.path=candidate..'/?.lua;'..root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local definition=assert(loadfile(definition_path))()
local Candidate=require('boss_candidate');local Scheduler=require('combo_scheduler')
local contract=require('subtree_contracts').skill_01
local total=0
local function test(name,fn)local ok,why=pcall(fn);assert(ok,name..': '..tostring(why));total=total+1;print('PASS '..name)end
local function fixture()
    local f={rows={},logs={},brain=false,cancelled={}}
    local config={IsValid=function()return true end,GetFullName=function()return 'ActorConfig '..definition.config_path end,
        GetCharacterName=function()return{ToString=function()return definition.display_name end}end}
    local boss_class={IsValid=function()return true end,IsA=function()return true end,
        GetFullName=function()return 'Class '..definition.class_path end,GetCDO=function()return{IsValid=function()return true end,['Actor Config']=config}end}
    local function ability(path)
        return {IsValid=function()return true end,GetAddress=function()return path end,
            IsA=function(_,kind)return kind=='/Script/GameplayAbilities.GameplayAbility' or kind=='/Script/SGameAI.RunSubtreeAbility' end,
            GetClass=function()return{GetFullName=function()return 'Class '..path end}end,
            ComboTreeWithWeight={ForEach=function(_,fn)for tree,weight in pairs(contract.trees)do
                fn({get=function()return{IsValid=function()return true end,GetFullName=function()return 'BehaviorTree '..tree end}end},
                   {get=function()return weight end})
            end end}}
    end
    local parent=ability(definition.parent_class)
    f.rows={{Ability=parent,ActiveCount=0},{Ability=ability('/Fixture/Passive.Passive_C'),ActiveCount=1}}
    local items=setmetatable({GetArrayNum=function()return #f.rows end},{__index=function(_,i)return f.rows[i]end})
    local parent_class={IsValid=function()return true end,IsA=function()return true end,
        GetFullName=function()return 'Class '..definition.parent_class end,GetCDO=function()return parent end}
    f.load=function(path)if path==definition.class_path then return boss_class elseif path==definition.parent_class then return parent_class end;error('unexpected load')end
    f.grant={boss_candidate=definition.id,developer_combo_only=true,developer_combo_evidence_sha256=definition.dependency_report_sha256,exe_sha256='fixture'}
    local function log(k,v)f.logs[#f.logs+1]={k,v}end
    f.prepare=function()return Candidate.prepare(definition.id,f.grant,f.load,log)end
    f.bind=function(profile)return Candidate.bind_granted(profile,items,function(o)return o and o:IsValid()end,log)end
    f.receipt={boss={GetClass=function()return boss_class end},asc={ActivatableAbilities={Items=items}},
        remote_control={ai={},brain={IsRunning=function()return not f.stopped end}}}
    local remote={scheduler_trial=true,
        begin_scheduler=function(_,t,id,seconds)assert(id=='skill_01' and seconds==25);f.brain=true;t.scheduler=true end,
        end_scheduler=function(_,t)f.brain=false;t.scheduler=nil;return true end,brain_suspended=function()return not f.brain end,
        native={set_brain_tick=function(_,enabled)f.brain=enabled end}}
    local calls={resolve=function(_,reference)return reference end,stop_brain=function()f.stopped=true end}
    f.scheduler=Scheduler.new(calls,remote,function(spec)
        if f.reject_cancel then return false end
        f.cancelled[#f.cancelled+1]=spec;spec.ActiveCount=0;return true
    end,log)
    f.begin=function()return f.scheduler:begin(f.receipt,'skill_01',{class_path=definition.parent_class})end
    f.ability=ability;f.config=config;f.parent=parent;f.boss_class=boss_class
    return f
end
test('native parent only binds after the entire exact idle grant scan',function()
    local f=fixture();local profile=f.prepare();f.bind(profile)
    assert(profile.skills.skill_01.class_path==definition.parent_class and profile.playable==false)
    assert(not profile.skills.heavy_01 and profile.developer_native_combo)
    for _,mode in ipairs({'missing','duplicate','active','wrong_type'})do
        f=fixture();profile=f.prepare();local marker={};profile.skills=marker
        if mode=='missing'then table.remove(f.rows,1)
        elseif mode=='duplicate'then f.rows[3]={Ability=f.parent,ActiveCount=0}
        elseif mode=='active'then f.rows[1].ActiveCount=1
        else f.parent.IsA=function()return false end end
        assert(not pcall(f.bind,profile) and profile.skills==marker,'partial binding escaped: '..mode)
    end
end)
test('wrong evidence or Actor defaults cannot prepare',function()
    local f=fixture();f.grant.developer_combo_only=false;assert(not pcall(f.prepare))
    f=fixture();f.grant.developer_combo_evidence_sha256='changed';assert(not pcall(f.prepare))
    f=fixture();f.config.GetFullName=function()return 'ActorConfig foreign' end;assert(not pcall(f.prepare))
end)
test('five repetitions wait for all engine-granted children and return to baseline',function()
    local f=fixture()
    for attempt=1,5 do
        assert(f.begin() and f.brain);f.rows[1].ActiveCount=1
        assert(not f.scheduler:poll(f.receipt,1))
        for leaf in pairs(contract.leaves)do
            local row
            for _,spec in ipairs(f.rows)do if spec.Ability:GetAddress()==leaf then row=spec end end
            if not row then row={Ability=f.ability(leaf),ActiveCount=0};f.rows[#f.rows+1]=row end
            row.ActiveCount=1;assert(not f.scheduler:poll(f.receipt,1));row.ActiveCount=0
        end
        f.rows[1].ActiveCount=0
        assert(f.scheduler:poll(f.receipt,0) and not f.brain and not f.receipt.combo_trial)
        assert(f.rows[2].ActiveCount==1)
    end
    assert(#f.cancelled==0)
end)
test('parent zero waits for a still-active child',function()
    local f=fixture();assert(f.begin());f.rows[1].ActiveCount=1
    f.rows[3]={Ability=f.ability(next(contract.leaves)),ActiveCount=1}
    assert(not f.scheduler:poll(f.receipt,1));f.rows[1].ActiveCount=0
    assert(not f.scheduler:poll(f.receipt,0));f.rows[3].ActiveCount=0
    assert(f.scheduler:poll(f.receipt,0))
end)
test('parent finishing without any observed native leaf is not a successful combo',function()
    local f=fixture();assert(f.begin());assert(not f.scheduler:poll(f.receipt,0))
    f.rows[1].ActiveCount=1;assert(not f.scheduler:poll(f.receipt,1));f.rows[1].ActiveCount=0
    assert(not f.scheduler:poll(f.receipt,0) and f.receipt.combo_trial)
    assert(f.scheduler:cancel_all(f.receipt) and not f.receipt.combo_trial)
end)
test('cancellation closes children and native parent but leaves passive alone',function()
    local f=fixture();assert(f.begin());f.rows[1].ActiveCount=1
    f.rows[3]={Ability=f.ability(next(contract.leaves)),ActiveCount=1}
    assert(f.scheduler:cancel_all(f.receipt) and f.stopped and not f.brain and not f.receipt.combo_trial)
    assert(#f.cancelled==2 and f.rows[2].ActiveCount==1)
    local observed=0
    for _,row in ipairs(f.logs)do
        if row[1]=='COMBO_CANCEL_BEGIN'then
            observed=observed+1;assert(row[2]=='skill_01|parent_active=1|active_children=1')
        end
    end
    assert(observed==1,'cancellation must log its fresh activity snapshot exactly once')
end)
test('cancel evidence does not reuse earlier child activity',function()
    local f=fixture();assert(f.begin());f.rows[1].ActiveCount=1
    f.rows[3]={Ability=f.ability(next(contract.leaves)),ActiveCount=1}
    assert(not f.scheduler:poll(f.receipt,1))
    f.rows[1].ActiveCount=0;f.rows[3].ActiveCount=0
    assert(f.scheduler:cancel_all(f.receipt))
    local observed=false
    for _,row in ipairs(f.logs)do
        if row[1]=='COMBO_CANCEL_BEGIN'then
            assert(row[2]=='skill_01|parent_active=0|active_children=0');observed=true
        end
    end
    assert(observed)
end)
test('failed cancellation retains responsibility for recovery',function()
    local f=fixture();assert(f.begin());f.rows[1].ActiveCount=1;f.reject_cancel=true
    assert(not pcall(f.scheduler.cancel_all,f.scheduler,f.receipt))
    assert(f.receipt.combo_trial and not f.brain and f.rows[1].ActiveCount==1)
end)
test('changed Actor CDO tree or active child fails before scheduling',function()
    for _,mode in ipairs({'actor','config','tree','child','unregistered'})do
        local f=fixture()
        if mode=='actor'then f.boss_class.GetFullName=function()return 'Class foreign' end
        elseif mode=='config'then f.config.GetFullName=function()return 'ActorConfig foreign' end
        elseif mode=='tree'then f.parent.ComboTreeWithWeight={ForEach=function()end}
        elseif mode=='child'then f.rows[3]={Ability=f.ability(next(contract.leaves)),ActiveCount=1}end
        local ok
        if mode=='unregistered'then ok=pcall(f.scheduler.begin,f.scheduler,f.receipt,'attack_01',{class_path=Scheduler.class})
        else ok=pcall(f.begin)end
        assert(not ok and not f.brain and not f.receipt.combo_trial,mode)
    end
end)
test('unexpected native grant retains recovery ticket',function()
    local f=fixture();assert(f.begin());f.rows[3]={Ability=f.ability('/Foreign/Attack.Attack_C'),ActiveCount=1}
    assert(not pcall(f.scheduler.poll,f.scheduler,f.receipt,0) and f.receipt.combo_trial)
end)
test('a different nonzero native tree weight cannot borrow the closed graph',function()
    local f=fixture()
    f.parent.ComboTreeWithWeight={ForEach=function(_,fn)for tree,weight in pairs(contract.trees)do
        fn({get=function()return{IsValid=function()return true end,GetFullName=function()return 'BehaviorTree '..tree end}end},
           {get=function()return weight+1 end})
    end end}
    assert(not pcall(f.begin) and not f.brain and not f.receipt.combo_trial)
end)
test('an engine-granted leaf may retire only after a real idle snapshot',function()
    local f=fixture();assert(f.begin());f.rows[1].ActiveCount=1
    local leaf=next(contract.leaves)
    f.rows[3]={Ability=f.ability(leaf),ActiveCount=1}
    assert(not f.scheduler:poll(f.receipt,1))
    f.rows[3].ActiveCount=0;assert(not f.scheduler:poll(f.receipt,1))
    f.rows[3]=nil;assert(not f.scheduler:poll(f.receipt,1))
    assert(f.receipt.combo_trial.baseline[leaf].retired)
    f.rows[1].ActiveCount=0
    assert(f.scheduler:poll(f.receipt,0) and not f.brain and not f.receipt.combo_trial)
end)
test('idle retirement permits a fresh same-class native grant without retaining old specs',function()
    local f=fixture();assert(f.begin());f.rows[1].ActiveCount=1
    local leaf=next(contract.leaves)
    f.rows[3]={Ability=f.ability(leaf),ActiveCount=1};assert(not f.scheduler:poll(f.receipt,1))
    f.rows[3].ActiveCount=0;assert(not f.scheduler:poll(f.receipt,1))
    f.rows[3]=nil;assert(not f.scheduler:poll(f.receipt,1))
    local replacement=f.ability(leaf);replacement.GetAddress=function()return 'new-native-object' end
    f.rows[3]={Ability=replacement,ActiveCount=1};assert(not f.scheduler:poll(f.receipt,1))
    local before=f.receipt.combo_trial.baseline[leaf]
    assert(before.address=='new-native-object' and not before.retired and before.spec==nil)
    assert(f.scheduler:cancel_all(f.receipt) and f.rows[3].ActiveCount==0 and f.rows[2].ActiveCount==1)
end)
test('active disappearance preexisting grant removal and unretired identity change stay rejected',function()
    for _,mode in ipairs({'active','preexisting','identity'})do
        local f=fixture();local leaf=next(contract.leaves)
        if mode=='preexisting'then f.rows[3]={Ability=f.ability(leaf),ActiveCount=0}end
        assert(f.begin());f.rows[1].ActiveCount=1
        if mode~='preexisting'then f.rows[3]={Ability=f.ability(leaf),ActiveCount=1}end
        assert(not f.scheduler:poll(f.receipt,1))
        if mode=='identity'then f.rows[3].Ability.GetAddress=function()return 'unverified-replacement' end
        else f.rows[3]=nil end
        assert(not pcall(f.scheduler.poll,f.scheduler,f.receipt,1) and f.receipt.combo_trial,mode)
        assert(f.brain,'read-only rejection must preserve the scheduler recovery responsibility')
    end
end)
print('Native combo adapter fixtures: '..total..' passed; no game acceptance.')
