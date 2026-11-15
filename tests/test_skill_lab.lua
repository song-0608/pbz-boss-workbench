-- 用途：验证候选白名单、重复授予拒绝和技能中换项禁令；不替代实机伤害验收。
local root=assert(arg[1]);package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local Lab=require('skill_lab');local Runtime=require('runtime');local count=0
local function test(name,fn)local ok,why=pcall(fn);assert(ok,name..': '..tostring(why));count=count+1;print('PASS '..name)end
local function path(c)return '/PBZCombatAsset/ActorData/Mobs/042_AHua/Ability/GuiTouDao/Abilities/'..c.asset..'.'..c.asset:match('([^/]+)$')..'_C'end
local function fixture()
    local profile,config={skills={}},{skills={}}
    local slots=Lab.configure(profile,config,{path(Lab.candidates[2]),path(Lab.candidates[3])})
    local s={state='ACTIVE',config=config}
    function s:skill(slot)self.called=slot;return true end
    return Lab.new(s,slots),s,profile,config
end
test('exact granted classes only; no gameplay claim',function()
    local lab,s,p,c=fixture();assert(#lab.slots==2 and p.skills.skill_04.gameplay_verified==false)
    assert(not p.skills.attack_01 and c.skills.lab_skill_04.lab_only and not c.skills.lab_skill_04.key)
end)
test('same suffix outside approved package is refused',function()
    assert(not pcall(Lab.configure,{skills={}},{skills={}},{'/Other/GA_AHua_Attack_01.GA_AHua_Attack_01_C'}))
end)
test('duplicate grants cannot become candidate',function()
    local p,c={skills={}},{skills={}};Lab.configure(p,c,{path(Lab.candidates[2]),path(Lab.candidates[2]),path(Lab.candidates[3])})
    assert(not p.skills.skill_04 and p.skills.skill_06)
end)
test('selection wraps; cast uses actual session rules',function()
    local lab,s=fixture();assert(lab:selected()=='lab_skill_04');assert(lab:next());assert(lab:cast())
    assert(s.called=='lab_skill_06');assert(lab:next());assert(lab:selected()=='lab_skill_04')
end)
test('selection blocked during skill or target readback',function()
    local lab,s=fixture();s.current_skill='token';assert(not lab:next());s.current_skill=nil;s.pending_target=true
    assert(not lab:next());assert(lab:selected()=='lab_skill_04')
end)
test('selection blocked outside active control',function()
    local lab,s=fixture();s.state='OFF';assert(not lab:next())
end)
test('unsafe attack stays quarantined even when uniquely granted',function()
    assert(not pcall(Lab.configure,{skills={}},{skills={}},{path(Lab.candidates[1])}))
end)
test('scheduler flag opens only exact developer parent and never bypasses runtime block',function()
    local p,c={skills={}},{skills={}}
    Lab.configure(p,c,{path(Lab.candidates[1])},{},true)
    assert(p.skills.attack_01 and p.skills.attack_01.gameplay_verified==false and c.skills.lab_attack_01.lab_only)
    assert(not pcall(Lab.configure,{skills={}},{skills={}},{path(Lab.candidates[1])},{[path(Lab.candidates[1])]=true},true))
end)
test('tree leaf references remain developer only and require unique actual grants',function()
    local p,c={skills={}},{skills={}}
    local a,b=Lab.candidates[5],Lab.candidates[6]
    Lab.configure(p,c,{path(a),path(b),path(b)})
    assert(p.skills.skill_08 and not p.skills.skill_05_hard)
    assert(p.skills.skill_08.gameplay_verified==false and c.skills.lab_skill_08.lab_only)
    assert(not c.skills.lab_skill_08.key and not p.skills.attack_01)
end)
test('confirmed player skill evidence survives developer assembly',function()
    local p={skills={skill_06={class_path=path(Lab.candidates[3]),gameplay_verified=true,evidence='fixture'}}}
    Lab.configure(p,{skills={}},{path(Lab.candidates[3])})
    assert(p.skills.skill_06.gameplay_verified and p.skills.skill_06.evidence=='fixture')
end)
test('lab key collisions fail before host registers any key',function()
    local lab,s,p,c=fixture();c.controls={enter='F6',exit='F10'};c.skill_lab.next_key='F6'
    local bridge={};for _,name in ipairs({'context','capture','take_control','verify_control','can_start_skill','start_skill','is_skill_finished','cancel_skills','restore','verify_restored'})do bridge[name]=function()return true end end
    local registered=0;local host={on_game_thread=function()end,bind_key=function()registered=registered+1 end,every_frame=function()end,cancel_frame=function()end,read_input=function()end,log=function()end}
    local runtime=Runtime.new(bridge,c,host);assert(not pcall(runtime.start,runtime));assert(registered==0)
end)
test('runtime classified subtree is excluded even if unique and explicitly listed',function()
    local p,c={skills={}},{skills={}};local a,b=Lab.candidates[10],Lab.candidates[11]
    Lab.configure(p,c,{path(a),path(b)},{[path(a)]=true})
    assert(not p.skills.skill_07 and p.skills.skill_09 and #c.skill_lab.slots==1)
end)
print('Skill lab fixtures: '..count..' passed; no runtime gameplay claim.')
