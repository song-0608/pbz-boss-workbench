-- 用途：验证目标切换必须真实回读、等待中禁止出招、失败回退及退出清理。
local root=assert(arg[1]);package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local Session=require('session');local Bridge=require('control_bridge');local count=0
local function fixture()
    local a={name='a'};local b={name='b'}
    function a:GetFullName()return self.name end;b.GetFullName=a.GetFullName
    local f={a=a,b=b,query=a,eligible=true}
    local calls={resolve=function(_,r)assert(r and not r.invalid,'stale target');return r end,
        reference=function(_,r)return r end}
    local combat={native={clear_target=function()f.query=nil end,set_focus=function()end}}
    function combat:request_target(ticket,target)ticket.selected_target=target;f.requested=target;return true end
    function combat:verify_target(ticket)return f.query==ticket.selected_target end
    local bridge=setmetatable({calls=calls,api={combat=combat,target_selector={
        next=function()return b,nil,2 end,eligible=function()return f.eligible end}}},Bridge)
    function bridge:check()return true end;function bridge:verify_control()return true end
    function bridge:world_boundary()return'same'end
    function bridge:context()return{isolated=true,offline=true,exe_sha256='fixture',world_id='one',boss_available=true}end
    function bridge:capture()return{boss={},player={},combat={selected_target=a,targeting={}},input_enabled=true}end
    function bridge:take_control()return true end;function bridge:can_start_skill()return true end
    function bridge:start_skill()return 'skill' end;function bridge:is_skill_finished()return false end
    function bridge:cancel_skills()return true end;function bridge:restore()return true end;function bridge:verify_restored()return true end
    f.session=Session.new(bridge,{expected_exe_sha256='fixture',skills={one={id='one',verified=true}}})
    assert(f.session:enter());return f
end
local function test(name,fn)local ok,why=pcall(fn);assert(ok,name..': '..tostring(why));count=count+1;print('PASS '..name)end
test('request is pending until actual query matches',function()local f=fixture();local s=f.session;assert(s:cycle_target());assert(s.pending_target);assert(s:poll());assert(s.pending_target);f.query=f.b;assert(s:poll());assert(not s.pending_target and not s.receipt.target_transition)end)
test('pending switch blocks skill and repeat requests',function()local f=fixture();local s=f.session;assert(s:cycle_target());assert(not s:skill('one'));assert(not s:cycle_target())end)
test('active skill blocks switch before mutation',function()local f=fixture();local s=f.session;assert(s:skill('one'));assert(not s:cycle_target());assert(not f.requested)end)
test('timeout requests old target and clears pending',function()local f=fixture();local s=f.session;s:cycle_target();for i=1,90 do s:poll()end;assert(not s.pending_target and f.requested==f.a and s.state=='ACTIVE')end)
test('lost requested object rolls back without fault',function()local f=fixture();local s=f.session;s:cycle_target();f.b.invalid=true;assert(not s:poll());assert(not s.pending_target and f.requested==f.a)end)
test('dead previous target clears target rather than selecting it',function()local f=fixture();local s=f.session;s:cycle_target();f.eligible=false;assert(not s:poll());assert(s.receipt.combat.selected_target==nil and f.query==nil)end)
test('exit clears pending target state',function()local f=fixture();local s=f.session;s:cycle_target();assert(s:restore('test exit'));assert(s.state=='OFF'and not s.pending_target)end)
test('partial native target write triggers restoration',function()local f=fixture();local s=f.session;function s.bridge.api.combat:request_target()error('partial target write')end;assert(not s:cycle_target());assert(s.state=='OFF')end)
print('Target transition fixtures passed: '..count)
