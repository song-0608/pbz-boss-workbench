-- 用途：真实调度许可、子能力收尾和失败保留责任的本地逻辑测试；不冒充实机。
local root=assert(arg[1]);package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local Trial=require('combo_scheduler');local total=0
local function test(name,fn)local ok,why=pcall(fn);assert(ok,name..': '..tostring(why));total=total+1;print('PASS '..name)end
local function fixture(id)
    id=id or'attack_01'
    local contract=require('subtree_contracts')[id]
    local parent_class=contract and contract.class or Trial.class
    local f={rows={},logs={},cancelled={},brain=false}
    local function ability(key)
        local c={GetFullName=function()return 'Class '..key end}
        local a={IsValid=function()return true end,GetClass=function()return c end,IsA=function()return true end,GetAddress=function()return key end}
        a.ComboTreeWithWeight={ForEach=function(_,fn)
            for tree,weight in pairs(contract and contract.trees or{[Trial.tree]=1})do
                fn({get=function()return{IsValid=function()return true end,GetFullName=function()return 'BehaviorTree '..tree end}end},{get=function()return weight end})
            end
        end}
        return a
    end
    f.rows[1]={Ability=ability(parent_class),ActiveCount=0}
    f.leaf=next(contract and contract.leaves or Trial.native_leaves)
    f.rows[2]={Ability=ability(f.leaf),ActiveCount=0}
    f.make_ability=ability
    f.rows[3]={Ability=ability('/Fixture/Passive.Passive_C'),ActiveCount=1}
    f.items=setmetatable({GetArrayNum=function()return #f.rows end},{__index=function(_,i)return f.rows[i]end})
    local calls={resolve=function(_,x)return x end,stop_brain=function()f.tree_stopped=true end}
    local remote={scheduler_trial=true,begin_scheduler=function(_,t,requested,seconds)assert(requested==id and seconds==25);t.scheduler=true;f.brain=true end,
        end_scheduler=function(_,t)t.scheduler=nil;f.brain=false;return true end,brain_suspended=function()return not f.brain end,
        native={set_brain_tick=function(_,value)f.brain=value end}}
    f.receipt={asc={ActivatableAbilities={Items=f.items}},remote_control={ai={},brain={IsRunning=function()return not f.tree_stopped end}}}
    f.cancel=function(spec)f.cancelled[#f.cancelled+1]=spec;if f.reject_cancel then return false end;spec.ActiveCount=0;return true end
    f.service=Trial.new(calls,remote,f.cancel,function(k,v)f.logs[#f.logs+1]={k,v}end)
    f.begin=function()return f.service:begin(f.receipt,id,{class_path=parent_class})end
    return f
end
test('unrelated skills do not open scheduler',function()local f=fixture();assert(not f.service:begin(f.receipt,'skill_01',{}));assert(not f.brain and not f.receipt.combo_trial)end)
test('zero parent before observing activity is not a natural completion',function()local f=fixture();f.begin();assert(not f.service:poll(f.receipt,0)and f.brain)end)
test('parent finish waits for child then closes scheduling',function()
    local f=fixture();f.begin();f.rows[1].ActiveCount=1;f.rows[2].ActiveCount=1;assert(not f.service:poll(f.receipt,1))
    f.rows[1].ActiveCount=0;assert(not f.service:poll(f.receipt,0));f.rows[2].ActiveCount=0
    assert(f.service:poll(f.receipt,0)and not f.brain and not f.receipt.combo_trial);assert(#f.cancelled==0)
end)
test('cancellation catches children without touching preexisting passive',function()
    local f=fixture();f.begin();f.rows[1].ActiveCount=1;f.rows[2].ActiveCount=1
    assert(f.service:cancel_all(f.receipt));assert(#f.cancelled==2 and f.cancelled[1]==f.rows[2]and f.tree_stopped)
    assert(f.rows[3].ActiveCount==1 and not f.brain and not f.receipt.combo_trial)
end)
test('uncancellable child preserves failed trial responsibility',function()
    local f=fixture();f.begin();f.rows[2].ActiveCount=1;f.reject_cancel=true
    assert(not pcall(f.service.cancel_all,f.service,f.receipt));assert(f.receipt.combo_trial and not f.brain and f.rows[2].ActiveCount==1)
end)
test('unexpected grants and changed identities are rejected',function()
    local f=fixture();f.begin();f.rows[4]={Ability=f.rows[2].Ability,ActiveCount=0}
    assert(not pcall(f.service.poll,f.service,f.receipt,0));f.rows[4]=nil
    f.rows[2]=nil;assert(not pcall(f.service.poll,f.service,f.receipt,0))
end)
test('engine-granted exact known leaf is tracked and cancelled without a Mod grant',function()
    local f=fixture();f.begin();local key
    for candidate in pairs(Trial.native_leaves)do if candidate~=f.leaf then key=candidate;break end end
    local a={IsValid=function()return true end,GetAddress=function()return 999 end,
        GetClass=function()return{GetFullName=function()return 'Class '..key end}end}
    f.rows[4]={Ability=a,ActiveCount=1}
    assert(not f.service:poll(f.receipt,1)and f.receipt.combo_trial.baseline[key].native_leaf)
    assert(f.service:cancel_all(f.receipt));assert(f.rows[4].ActiveCount==0)
end)
test('unknown tree fails before brain permission',function()
    local f=fixture();f.rows[1].Ability.ComboTreeWithWeight={ForEach=function()end}
    assert(not pcall(f.begin));assert(not f.brain and not f.receipt.combo_trial)
end)

test('both reflected HomingFlower parents retain parent-child natural and cancel rules',function()
    for _,id in ipairs({'homing_flower','homing_flower_hard'})do
        local f=fixture(id);assert(f.begin())
        f.rows[1].ActiveCount=1;f.rows[2].ActiveCount=1;assert(not f.service:poll(f.receipt,1))
        f.rows[1].ActiveCount=0;assert(not f.service:poll(f.receipt,0))
        f.rows[2].ActiveCount=0;assert(f.service:poll(f.receipt,0)and not f.brain)
        f=fixture(id);assert(f.begin());f.rows[1].ActiveCount=1;f.rows[2].ActiveCount=1
        assert(f.service:cancel_all(f.receipt)and #f.cancelled==2 and f.rows[3].ActiveCount==1)
    end
end)

test('HomingFlower cannot borrow another parent native-leaf grant permissions',function()
    local f=fixture('homing_flower');assert(f.begin())
    local key=Trial.class
    f.rows[4]={Ability={IsValid=function()return true end,GetAddress=function()return 777 end,
        GetClass=function()return{GetFullName=function()return'Class '..key end}end},ActiveCount=1}
    assert(not pcall(f.service.poll,f.service,f.receipt,1))
    assert(f.receipt.combo_trial and f.brain)
end)
test('preexisting unrelated grants cannot activate under a different parent permission',function()
    local f=fixture('homing_flower')
    f.rows[2].Ability=f.make_ability(Trial.class)
    assert(f.begin());f.rows[1].ActiveCount=1;f.rows[2].ActiveCount=1
    assert(not pcall(f.service.poll,f.service,f.receipt,1))
    assert(f.receipt.combo_trial and f.brain)
end)
print('Combo scheduler fixtures: '..total..' passed; runtime verification separate.')
