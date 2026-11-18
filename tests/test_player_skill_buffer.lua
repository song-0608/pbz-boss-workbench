local Buffer=require('player_skill_buffer');local Session=require('session');local now=100
local function fixture()
    local b={finished=false,allowed=true,starts=0,world='w'}
    function b:context()return{isolated=true,offline=true,exe_sha256='fixture',world_id=self.world,boss_available=true}end
    function b:capture()return{}end
    function b:take_control()return true end
    function b:verify_control()return true end
    function b:can_start_skill()return self.allowed end
    function b:start_skill()self.starts=self.starts+1;return'token-'..self.starts end
    function b:is_skill_finished()return self.finished end
    function b:cancel_skills()return true end
    function b:restore()return true end
    function b:verify_restored()return true end
    local s=Session.new(b,{expected_exe_sha256='fixture',skills={a={id='a',verified=true}}})
    local reports={};Buffer.attach(s,{now=function()return now end,ttl=0.18,
        on_result=function(slot,ok)reports[#reports+1]={slot,ok}end})
    assert(s:enter());return s,b,reports
end
local s,b,reports=fixture();assert(s:skill('a'));assert(not s:request_skill('a'));assert(b.starts==1 and #reports==0)
assert(s:flush_buffered_skill());assert(b.starts==1,'native active ability cannot overlap')
b.finished=true;now=100.1;assert(s:poll());assert(s:flush_buffered_skill());assert(b.starts==2 and #reports==1 and reports[1][2])
assert(s:flush_buffered_skill());assert(b.starts==2,'one request cannot repeat')
for _,kind in ipairs({'expired','backwards','nonfinite','restore','input loss','replacement','world'})do
    now=100;s,b=fixture();assert(s:skill('a'));s:request_skill('a')
    if kind=='expired'then now=100.181 elseif kind=='backwards'then now=99 elseif kind=='nonfinite'then now=0/0
    elseif kind=='restore'then assert(s:restore('F10'))
    elseif kind=='input loss'then s:clear_buffered_skill('focus')
    elseif kind=='replacement'then s.receipt={}
    else s.world_id='changed'end
    s.current_skill=nil;assert(s:flush_buffered_skill());assert(b.starts==1 and not s.buffered_skill,kind)
end
now=100;s,b,reports=fixture();assert(s:skill('a'));s:request_skill('a');b.finished=true;b.allowed=false;now=100.1
assert(s:poll());assert(s:flush_buffered_skill());assert(b.starts==1 and #reports==1 and not reports[1][2]);b.allowed=true
assert(s:flush_buffered_skill());assert(b.starts==1,'native rejection cannot auto-retry')
for i=1,100 do assert(s:request_skill('a'));assert(s:poll())end
assert(b.starts==101,'software must not stop accepting skills after two uses')
print('PASS exact native completion, short single request, expiry/focus/restore/world invalidation, no resource bypass and 100 repeated native-approved activations')
