-- 用途：执行真实实验脚本，确认能力列表稳定前不StopAI、初始化失败的重试重新等待静止。
local root=assert(arg[1]);local file=assert(io.open(root..'/mod/PBZBossControl/Experiments/spawn_lifecycle.lua','rb'))
local source=file:read('*a');file:close();local total=0
local module_file=assert(io.open(root..'/mod/PBZBossControl/Scripts/owned_arena.lua','rb'))
local module_source=module_file:read('*a');module_file:close()
local function fixture(expire_first,authority_delay,with_targets,remote,arena)
    local f={queue={},logs={},clock=0,stops=0,spawns=0,velocity_reads=0,captures=0,transforms={}}
    local function valid(o)function o:IsValid()return not self.invalid end;return o end
    local player=valid({AttributeSetBase={Health={CurrentValue=100}},CapsuleComponent={CapsuleHalfHeight=96,CapsuleRadius=45}})
    function player:GetFullName()return 'Player /Game/Test:PersistentLevel.Player'end
    function player:GetAddress()return 100 end
    function player:GetVelocity()
        f.velocity_reads=f.velocity_reads+1
        local moving=f.restored and f.retry_moving and f.retry_moving>0
        if moving then f.retry_moving=f.retry_moving-1 end
        return{X=moving and 10 or 0,Y=0,Z=0}
    end
    function player:K2_GetActorLocation()return{X=0,Y=0,Z=0}end
    function player:GetActorForwardVector()return{X=1,Y=0,Z=0}end
    local pc=valid({Pawn=player});function pc:GetFullName()return'Controller /Game/Test:PersistentLevel.Player'end
    local class=valid({})
    function class:GetCDO()return{CapsuleComponent={CapsuleHalfHeight=96,CapsuleRadius=42},['Actor Config']={GetCharacterName=function()return{ToString=function()return'新娘阿花'end}end,
        GetFullName=function()return'Config /Fixture/Ahua.Config'end}}end
    local maths=valid({MakeTransform=function(_,p,r,s)return{p=p,r=r,s=s}end})
    local statics=valid({})
    function statics:BeginDeferredActorSpawnFromClass(_,_,transform)
        f.spawns=f.spawns+1;local born=f.clock;local number=f.spawns
        f.transforms[number]=transform
        local items={}
        function items:GetArrayNum()return f.clock-born>=750 and 37 or 28 end
        local brain=valid({tick=true});function brain:StopLogic()end
        function brain:SetComponentTickEnabled(on)self.tick=on;f.brain_paused=not on end
        function brain:IsComponentTickEnabled()return self.tick end
        local game_ai=valid({bInitialized=true,bAIStarted=true})
        function game_ai:StopAI()
            assert(items:GetArrayNum()==37,'StopAI interrupted partial ability initialization')
            self.bAIStarted=false
            f.stops=f.stops+1
        end
        local ai=valid({BrainComponent=brain,SGameAIComponent=game_ai,tick=true});function ai:K2_DestroyActor()self.invalid=true end
        function ai:SetActorTickEnabled(on)self.tick=on;f.controller_paused=not on end
        function ai:IsActorTickEnabled()return self.tick end
        local actor=valid({AbilitySystemComponent=valid({ActivatableAbilities={Items=items}})})
        function actor:IsValid()return not self.invalid and not(expire_first and number==1 and f.clock-born>=500)end
        function actor:GetController()return ai end
        function actor:GetAddress()return number+100 end
        function actor:K2_GetActorLocation()assert(not self.invalid,'query on rejected target');return transform.p end
        function actor:GetFullName()return'Boss /Game/Test:PersistentLevel.Ahua'..number end
        function actor:HasAuthority()
            local ready=f.clock-born>=(authority_delay or 0)
            if not ready then f.no_authority_reads=(f.no_authority_reads or 0)+1 end
            return ready
        end
        function actor:K2_DestroyActor()if not f.reject_cleanup then self.invalid=true end end
        function actor:IsActorBeingDestroyed()return self.invalid end
        return actor
    end
    function statics:FinishSpawningActor(actor)
        if f.reject_finish=='all' or(f.reject_finish=='first'and f.spawns==1)or(f.reject_finish=='first_target'and f.spawns==2)then
            actor.invalid=true;f.finish_rejections=(f.finish_rejections or 0)+1
        end
        return actor
    end
    local protection={}
    function protection:capture()
        f.captures=f.captures+1
        if f.captures>1 then assert(f.retry_moving==0,'retry bypassed stationary gate')end
        return{restored=false}
    end
    function protection:apply()end
    function protection:restore(t)t.restored=true;f.restored=true;f.retry_moving=10 end
    local function schedule(delay,fn)f.queue[#f.queue+1]={delay=delay,fn=fn}end
    local env
    env=setmetatable({print=function(s)f.logs[#f.logs+1]=s end,FindAllOf=function()return{pc}end,
        ExecuteWithDelay=schedule,ExecuteInGameThreadWithDelay=schedule,ExecuteInGameThread=function(fn)fn()end,
        LoadAsset=function()return class end,StaticFindObject=function(path)return path:find('MathLibrary',1,true)and maths or statics end,
        require=function(name)
            if name=='owned_arena'then return assert(load(module_source,'@owned_arena_initialization','t',env))()end
            if name=='profiles.ahua'then return{identity_verified=true,exe_sha256='fixture',class_path='fixture-class',
                config_path='/Fixture/Ahua.Config',display_name='新娘阿花'}end
            if name=='ue_calls'then return{new=function()return{}end}end
            if name=='player_protection'then return{new=function()return protection end}end
            if name=='ue_arena_layout'then return{new=function()return function(p)return p end end}end
            if name=='arena_layout'then return{choose=function(_,_,_,_,_,_,_,rejected)
                local key=rejected['1:1']and'2:1'or'1:1'
                f.layout_keys=f.layout_keys or{};f.layout_keys[#f.layout_keys+1]=key
                return{boss={X=450,Y=0,Z=100},targets={{X=650,Y=key=='1:1'and 0 or 180,Z=100},
                    {X=650,Y=350,Z=100}},heading=0,key=key}
            end}end
            error('fixture stops before runtime assembly: '..name)
        end,
    },{__index=_G})
    local prefix='local experiment_protection_binding={binding_verified=true}\nlocal function experiment_attest()return{offline=true,isolated=true,exe_sha256="fixture",expires_at=os.time()+300}end\n'
    if with_targets then prefix='local experiment_combat_binding={binding_verified=true}\n'..prefix end
    if remote then prefix='local experiment_remote_binding={binding_verified=true}\n'..prefix end
    if arena then prefix='local experiment_arena_binding={binding_verified=true}\n'..prefix end
    assert(load(prefix..source,'@initialization_fixture','t',env))()
    function f:step()
        local row=table.remove(self.queue,1);if not row then return false end
        self.clock=self.clock+row.delay;row.fn();return true
    end
    return f
end
local function test(name,fn)local ok,why=pcall(fn);assert(ok,name..': '..tostring(why));total=total+1;print('PASS '..name)end
test('AI stop waits for stable full grants rather than bInitialized alone',function()
    local f=fixture(false)
    for i=1,80 do if not f:step()then break end;if f.stops>0 then break end end
    assert(f.stops==1 and f.clock>=4500,'initialization never reached stable readiness')
end)

test('owned remote AI stays dormant after complete grants before restoring the player',function()
    local f=fixture(false,nil,false,true)
    for i=1,80 do if not f:step()then break end;if f.stops>0 then break end end
    assert(f.stops==1 and f.clock>=4500 and f.brain_paused and f.controller_paused)
    assert(table.concat(f.logs,'\n'):find('OWNED_IDLE_AI_SUSPENDED=',1,true))
end)
test('expired owned actor retries only after player becomes stationary again',function()
    local f=fixture(true)
    for i=1,100 do if not f:step()then break end;if f.spawns==2 then break end end
    assert(f.spawns==2 and f.captures==2 and f.retry_moving==0)
    assert(table.concat(f.logs,'\n'):find('INITIALIZATION_RETRY=1',1,true))
end)
test('delayed local authority waits before control installation',function()
    local f=fixture(false,1250)
    for i=1,100 do if not f:step()then break end;if f.stops>0 then break end end
    assert(f.no_authority_reads>0 and f.stops==1)
    assert(not table.concat(f.logs,'\n'):find('ISSUE_START=',1,true))
end)
test('permanently missing authority never reaches AI pause or control',function()
    local f=fixture(false,math.huge)
    for i=1,180 do if not f:step()then break end end
    assert(f.no_authority_reads>0 and f.stops==0)
    assert(table.concat(f.logs,'\n'):find('INITIALIZATION_ATTEMPT_REJECTED=',1,true))
end)
test('construction rejection restores before bounded same-process retry',function()
    local f=fixture(false);f.reject_finish='first'
    for i=1,100 do if not f:step()then break end;if f.spawns==2 then break end end
    assert(f.finish_rejections==1 and f.spawns==2 and f.captures==2 and f.retry_moving==0 and f.stops==0)
    assert(not table.concat(f.logs,'\n'):find('ISSUE_START=',1,true))
end)
test('repeated construction rejection stops after three restored attempts',function()
    local f=fixture(false);f.reject_finish='all'
    for i=1,240 do if not f:step()then break end end
    local text=table.concat(f.logs,'\n')
    assert(f.spawns==3 and f.finish_rejections==3 and f.stops==0)
    assert(text:find('PREREQUISITE_RETRY_SAFE=true',1,true)and not text:find('ISSUE_START=',1,true))
end)
test('unacknowledged owned cleanup forbids retry',function()
    local f=fixture(false,math.huge);f.reject_cleanup=true
    for i=1,200 do if not f:step()then break end end
    assert(f.spawns==1 and f.stops==0)
    assert(table.concat(f.logs,'\n'):find('ISSUE_CLEANUP=',1,true))
end)
test('rejected first target is never queried and retry changes its local position',function()
    local f=fixture(false,nil,true);f.reject_finish='first_target'
    for i=1,220 do if not f:step()then break end;if f.spawns>=4 then break end end
    assert(f.spawns==4 and f.finish_rejections==1 and f.captures==2)
    assert(f.transforms[2].p.X==650 and f.transforms[2].p.Y==0)
    assert(f.transforms[4].p.X==650 and f.transforms[4].p.Y==180,'retry repeated the same rejected target location')
    assert(not table.concat(f.logs,'\n'):find('query on rejected target',1,true))
end)

test('navigation layout rejected by construction cannot be selected again on retry',function()
    local f=fixture(false,nil,true,false,true);f.reject_finish='first_target'
    for i=1,220 do if not f:step()then break end;if f.spawns>=4 then break end end
    assert(f.spawns==4 and f.layout_keys[1]=='1:1'and f.layout_keys[2]=='2:1')
    assert(f.transforms[2].p.Y==0 and f.transforms[4].p.Y==180)
    assert(table.concat(f.logs,'\n'):find('NAVIGATION_LAYOUT_REJECTED=1:1|stage=initialization',1,true))
end)
print('Practice initialization fixtures passed: '..total)
