-- Execute the pinned, patched upstream Lua with fake UObjects. This exercises the
-- actual exported cache references and event/report/puppet entry points, not a
-- reimplementation of the upstream synchronizer. No native relay or game runs.
local root,candidate=assert(arg[1]),assert(arg[2])
local fence=dofile(root..'/tools/phantom_boss_enemy_fence.lua')
local checks=0
local function check(name,fn) fn();checks=checks+1;print('PASS '..name) end
local function actor(addr,name)
    return {address=addr,name=name or ('Actor_'..addr),world='W',class='/Boss/A.A_C',
        GetAddress=function(self)return self.address end,
        GetFName=function(self)return {ToString=function()return self.name end}end}
end
local function env()
    local e={events={},writes=0,freed={},timers={}}
    _G.LoopInGameThreadWithDelay=function(ms,fn)e.timers[#e.timers+1]=fn;return #e.timers end
    local api={version='1.7.3',log=function()end,valid=function(o)return type(o)=='table' end,
        getPlayer1=function()return nil,nil end,game={},link={now=function()return 1 end,
        event=function(line)e.events[#e.events+1]=line end,quick=function(line)e.events[#e.events+1]=line end}}
    local game=api.game
    game.freeCopy=function(addr,forget)assert(forget==true);e.freed[addr]=true end
    for _,key in ipairs({'setHealth','setMinHealth','setPosture','kill','startAI','stopAI','playMove','applyDamage'}) do
        game[key]=function()e.writes=e.writes+1;error('unexpected engine mutation: '..key)end
    end
    game.isDead=function()return false end
    api.coop=dofile(candidate..'/upstream-local-patches/coop.lua')(api)
    local coop=api.coop
    e.owned={}
    local function owned(a,addr)
        local row=e.owned[addr]
        return row and a.address==row.address and a.name==row.name and a.class==row.class and a.world==row.world or false
    end
    e.fence=fence.new(coop,game,owned)
    api.bossWorkbench={allow_enemy_name=function(_,name)return e.fence:allow_name(name)end,
        allow_enemy_event=function(_,...)return e.fence:allow_event(...)end,
        allow_enemy_actor=function(_,a,addr)return not (a and owned(a,addr or a:GetAddress()))end}
    api.puppets=dofile(candidate..'/upstream-local-patches/puppets.lua')(api)
    e.api,e.coop,e.view=api,coop,coop.workbenchEnemyState()
    e.boss,e.other=actor(11),actor(22)
    local v,n=e.view,e.view.net
    v.names.owned=e.boss;v.names.normal=e.other
    v.seen.owned={addr=11,hp=100};v.seen.normal={addr=22,hp=50}
    v.reach.list={e.other,e.boss,e.other};v.reach.addrs={22,11,22};v.reach.at=3
    v.reach.near[11]={actor=e.boss,addr=11};v.reach.near[22]={actor=e.other,addr=22}
    v.round.queue={{actor=e.other,addr=22},{actor=e.boss,addr=11},{actor=e.other,addr=22}}
    v.round.at=3;v.round.seen={owned={addr=11},normal={addr=22}};v.round.held={[11]=e.boss,[22]=e.other}
    n.enemyNumbers={owned=7,normal=8};n.announced={[7]=true,[8]=true};n.linesSent={[7]={},[8]={}}
    n.enemyNames={[7]={name='owned'},[8]={name='normal'}}
    n.matchSticky={owned=11,normal=22};n.heldAlive={[11]=e.boss,[22]=e.other}
    n.aside={[11]={actor=e.boss},[22]={actor=e.other}};n.deadBodies={[11]=true,[22]=true}
    for _,key in ipairs({'remoteEnemies','guestRuns','guestLines','mine','hitHere','lethalPending',
        'pendingDeaths','hostKilled','partnerBosses','hostSeen','fightOf'}) do
        n[key]={owned={marker='owned'},normal={marker='normal'}}
    end
    for _,key in ipairs({'seen','since','retryAt'}) do v.handover[key]={owned={},normal={}} end
    function e:take()
        -- Capture a value identity, not a mutable wrapper to simulate UObject reuse.
        self.owned[11]={address=11,name=self.boss.name,class=self.boss.class,world=self.boss.world}
        self.fence:purge(self.owned[11])
    end
    return e
end
check('actual upstream cache view follows current names and seen tables',function()
    local e=env();assert(e.coop.enemies()==e.view.names)
    assert(e.coop.enemyActor('owned')==e.boss)
    e:take();assert(e.coop.enemyActor('owned')==nil and e.coop.enemyActor('normal')==e.other)
end)
check('ownership removes identity, damage, handover and death records only for that actor',function()
    local e=env();e:take();local v,n=e.view,e.view.net
    for _,key in ipairs({'remoteEnemies','guestRuns','guestLines','mine','hitHere','lethalPending',
        'pendingDeaths','hostKilled','partnerBosses','hostSeen','fightOf'}) do
        assert(n[key].owned==nil and n[key].normal.marker=='normal',key)
    end
    assert(v.seen.owned==nil and v.seen.normal.hp==50)
    for _,key in ipairs({'seen','since','retryAt'}) do
        assert(v.handover[key].owned==nil and v.handover[key].normal)
    end
    assert(e.writes==0)
end)
check('in-flight arrays compact in parallel without skipping the next normal enemy',function()
    local e=env();e:take();local v=e.view
    assert(#v.reach.list==2 and #v.reach.addrs==2 and v.reach.at==2)
    assert(v.reach.list[v.reach.at]==e.other and v.reach.addrs[v.reach.at]==22)
    assert(#v.round.queue==2 and v.round.at==2 and v.round.queue[v.round.at].actor==e.other)
    assert(v.reach.near[11]==nil and v.reach.near[22].actor==e.other)
end)
check('numeric enemy announcements and line caches retire together',function()
    local e=env();e:take();local n=e.view.net
    assert(n.enemyNumbers.owned==nil and n.enemyNames[7]==nil and n.announced[7]==nil and n.linesSent[7]==nil)
    assert(n.enemyNumbers.normal==8 and n.enemyNames[8].name=='normal' and n.announced[8] and n.linesSent[8])
    e.coop.handlers.N('7 owned Boss_C');assert(n.enemyNames[7]==nil)
    e.coop.handlers.NQ('7 normal Enemy_C');assert(n.enemyNames[7].name=='normal')
end)
check('late reliable death, damage, ownership and fight events cannot mutate owned bodies',function()
    local e=env();e:take();e.view.net.enabled=true;e.view.net.role='client'
    for _,case in ipairs({{'K','owned'},{'GK','owned'},{'D','owned 20 0 L'},
        {'LR','owned 10'},{'RUN','owned 1'},{'B','owned'},{'BEATEN','owned'},{'HAS','owned'},{'NOT','owned'}}) do
        e.coop.handlers[case[1]](case[2])
    end
    assert(e.writes==0 and #e.events==0 and e.view.net.mine.owned==nil)
end)
check('owned hits produce no report while an ordinary enemy hit still reaches native link',function()
    local e=env();e:take();e.api.puppets=nil;e.view.net.enabled=true;e.view.net.role='client'
    e.coop.reportHit('owned',e.boss,20,0,false);assert(#e.events==0)
    e.coop.reportHit('normal',e.other,20,0,false)
    assert(#e.events==1 and e.events[1]:find('D normal ',1,true))
    assert(e.view.net.hitHere.normal==true and e.writes==0)
end)
check('outgoing stale enemy announcements blocked without blocking identity heartbeats',function()
    local e=env();e:take();e.view.net.enabled=true
    e.coop.sendEvent('N',7,'owned','Boss_C');e.coop.sendEvent('K','owned')
    assert(#e.events==0)
    e.coop.sendEvent('BWB1','1 H session');e.coop.sendEvent('N',8,'normal','Enemy_C')
    assert(#e.events==2)
end)
check('puppet removal forgets native picker cache without releasing AI or changing health',function()
    local e=env();e.api.puppets.follow('owned',e.boss,{});e.api.puppets.follow('normal',e.other,{})
    assert(e.api.puppets.follows(11) and e.api.puppets.follows(22))
    e:take();assert(not e.api.puppets.follows(11) and e.api.puppets.follows(22))
    assert(e.freed[11] and not e.freed[22] and e.writes==0)
    e.api.puppets.follow('owned',e.boss,{})
    e.coop.handlers.A('owned /Evil/Ability_C /Evil/Montage 0 host')
    assert(not e.api.puppets.follows(11) and e.writes==0)
end)
check('same address reused with another identity retains its live mapping and puppet',function()
    local e=env();local reused=actor(11,'NewActor');e.view.names.owned=reused
    e.api.puppets.follow('owned',reused,{})
    e.view.reach.list={reused};e.view.reach.addrs={11};e.view.reach.at=1
    e.view.reach.near[11]={actor=reused,addr=11};e:take()
    assert(e.view.names.owned==reused and e.api.puppets.follows(11))
    assert(#e.view.reach.list==1 and e.view.reach.near[11].actor==reused)
    assert(e.view.net.matchSticky.owned==11 and e.view.seen.owned.hp==100 and not e.freed[11])
    assert(e.fence:allow_name('owned') and e.writes==0)
end)
check('unproven sticky aliases drop only the stale address association',function()
    local e=env();e.view.net.matchSticky.unknown=11;e.view.net.remoteEnemies.unknown={Hp=321}
    e:take();assert(e.view.net.matchSticky.unknown==nil and e.view.net.remoteEnemies.unknown.Hp==321)
    assert(e.fence:allow_name('unknown'))
end)
check('repeat purge is idempotent and new World clears only the quarantine',function()
    local e=env();e:take();e:take();assert(e.fence.blocked_count==1)
    assert(not e.fence:allow_name('owned'));e.fence:reset()
    assert(e.fence.blocked_count==0 and e.fence:allow_name('owned') and e.view.names.normal==e.other)
end)
check('real adapter ownership transition purges the actual upstream tables and puppet',function()
    local e=env();e.api.puppets.follow('owned',e.boss,{})
    e.api.game.listEnemies=function()return {e.boss,e.other},{11,22}end
    e.api.game.enemiesSoFar=e.api.game.listEnemies
    local callback
    local host={now=function()return 1 end,log=function()end,on_revoke=function()end,
        identify=function(a)return {address=a.address,name=a.name,class=a.class,world=a.world}end,
        snapshot=function()return {body=e.boss,world='W'}end,
        schedule=function(_,fn)callback=fn;return function()end end}
    local config={role='host',session='test',catalog_sha256=string.rep('a',64),exe_sha256=string.rep('b',64),
        runtime_acceptance_current=false,bosses={boss={class_path=e.boss.class,actions={}}}}
    local adapter=dofile(root..'/tools/phantom_boss_adapter.lua')
    local protocol=dofile(root..'/tools/phantom_boss_protocol.lua')
    e.api.bossWorkbench=adapter.attach(e.api,config,host,protocol,fence)
    callback()
    assert(e.view.names.owned==nil and e.view.names.normal==e.other)
    assert(not e.api.puppets.follows(11) and e.api.puppets.follows(22)==false)
    assert(e.api.bossWorkbench.owned_count==1 and #e.api.game.listEnemies()==1 and e.writes==0)
    e.api.bossWorkbench:close()
end)
check('in-flight aliases remain quarantined after the main mapping rotated away',function()
    local e=env();e.view.names.owned=nil
    e.view.round.queue[2].name='old_alias'
    e.view.net.aside[11].name='aside_alias'
    e.view.net.mirrorOn={mirror_alias={actor=e.boss,addr=11}}
    e:take()
    assert(not e.fence:allow_name('old_alias') and not e.fence:allow_name('aside_alias'))
    assert(not e.fence:allow_name('mirror_alias') and e.view.net.mirrorOn.mirror_alias==nil)
end)
check('legacy peer ability packets cannot activate or grant abilities on the controlled body',function()
    local e=env();e.view.net.ghost=e.boss;e.view.net.enabled=true
    e.coop.handlers.M('/Arbitrary/Attack.Attack_C 0')
    e.coop.sendEvent('M','/Arbitrary/Attack.Attack_C',0)
    assert(e.writes==0 and #e.events==0)
end)
print('PASS '..checks..' enemy fence groups; patched upstream Lua executed with fake engine, no relay/game')
