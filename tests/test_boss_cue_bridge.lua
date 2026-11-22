local root=assert(arg[1]);package.path=root..'/tools/?.lua;'..package.path
local Adapter=require('boss_cue_bridge')
local total=0
local function test(name,fn)fn();total=total+1;print('PASS '..name)end
local function array(values)
    values=values or{};values.GetArrayNum=function(self)return #self end;return values
end
local function fixture()
    local f={focused=true,controlled=true,same_world=true,spawns=0,ends=0,errors={},hooks={},removed={}}
    local world={name='World One',address=1,class='World'}
    local boss={name='Boss One',address=2,class='Boss'}
    local r={world=world,boss=boss,input_enabled=true}
    local action={name='Action One',address=3,class='BlueprintGeneratedClass '..Adapter.class_path}
    function action:IsValid()return not self.dead end
    function action:GetFullName()return self.name end
    function action:GetClass()return{GetFullName=function()return self.class end}end
    function action:GetAvatarActor()return f.avatar end
    action['Cascade Comps']=array();action['Niagara Comps']=array()
    local spawn_particles={IsValid=function()return true end}
    local end_particles={IsValid=function()return true end}
    local function spawn(...)
        assert(select('#',...)==1 and (...)==boss);f.spawns=f.spawns+1
        action['Niagara Comps'][1]={IsValid=function()return true end}
        if f.spawn_error then error('partial native spawn')end
    end
    local function finish(...)
        assert(select('#',...)==0)
        if f.end_error then error('native cleanup refused')end
        f.ends=f.ends+1;action['Niagara Comps']=array();action['Cascade Comps']=array()
    end
    function action:CallFunction(fn,...)
        assert(self==action)
        if fn==spawn_particles then return spawn(...)end
        assert(fn==end_particles);return finish(...)
    end
    boss.IsValid=function()return true end;f.avatar=boss
    local calls={}
    function calls:reference(o)return{name=o.name,address=o.address,class=o.class}end
    function calls:world()return f.same_world and world or{name='World Two',address=99,class='World'}end
    function calls:same(a,b)return a==b end
    function calls:resolve(ref)assert(ref==boss);return boss end
    function calls:optional(ref)
        if action.dead then return nil end
        assert(ref.name==action.name and ref.address==action.address,'action identity changed');return action
    end
    function calls:retirement_optional(ref)return self:optional(ref)end
    local b={calls=calls,active_receipt=r,check=function(_,receipt)assert(receipt==r);return{}end,
        verify_control=function()return f.controlled end}
    local g={}
    function g.StaticFindObject(path)
        if path==Adapter.class_path..':Spawn Particles'then return spawn_particles end
        if path==Adapter.class_path..':End Particles'then return end_particles end
        error('unexpected reflected function lookup')
    end
    function g.RegisterHook(path,callback,third)
        assert(third==nil,'Blueprint post must be the first callback')
        if f.register_error and path:find('Received_ActionEnd',1,true)then error('second hook failed')end
        local n=#f.hooks+1;f.hooks[n]={path=path,callback=callback};return n,n
    end
    function g.UnregisterHook(path,pre,post)
        assert(pre==post and f.hooks[pre].path==path)
        if f.unregister_error then error('unregister failed')end
        f.removed[#f.removed+1]=path
    end
    local contract={developer_only=true,declaration_verified=true,script_gate_verified=true,
        avatar_binding_verified=true,class_path=Adapter.class_path,blueprint_post_hook_verified=true}
    f.contract=contract;f.action=action;f.receipt=r;f.bridge=b
    f.attach=function()return Adapter.new(b,g,contract,function()return f.focused end,
        function(label,why)f.errors[#f.errors+1]=label..'|'..why end)end
    f.cue=f.attach();assert(f.cue:install())
    f.begin=function()f.hooks[1].callback({get=function()return action end})end
    f.finish=function()f.hooks[2].callback({get=function()return action end})end
    return f
end
test('only reviewed Blueprint post hooks can attach',function()
    local f=fixture();assert(#f.hooks==2)
    for _,field in ipairs({'developer_only','declaration_verified','script_gate_verified',
        'avatar_binding_verified','blueprint_post_hook_verified','class_path'})do
        local old=f.contract[field];f.contract[field]=false
        assert(not pcall(f.attach));f.contract[field]=old
    end
end)
test('native begin and end preserve owner and do not duplicate original particles',function()
    local f=fixture();f.begin();f.begin();assert(f.spawns==1)
    f.action['Niagara Comps']=array() -- Original Received_ActionEnd has already cleared its arrays.
    f.finish();assert(f.ends==0 and f.cue.cues.size==0)
    f.begin();assert(f.spawns==2);assert(f.cue:close());assert(f.ends==1 and #f.removed==2)
end)
test('unowned background inactive wrong-class and new-world actions cannot spawn',function()
    for _,mode in ipairs({'avatar','focus','input','control','class','world','CDO'})do
        local f=fixture()
        if mode=='avatar'then f.avatar={IsValid=function()return true end}
        elseif mode=='focus'then f.focused=false
        elseif mode=='input'then f.receipt.input_enabled=false
        elseif mode=='control'then f.controlled=false
        elseif mode=='class'then f.action.class='OtherCue'
        elseif mode=='world'then f.same_world=false
        else f.action.name='Default__Cue'end
        f.begin();assert(f.spawns==0 and #f.errors==0,mode)
    end
end)
test('pre-existing original cue remains untouched',function()
    local f=fixture();f.action['Cascade Comps'][1]={IsValid=function()return true end}
    f.begin();assert(f.spawns==0);assert(f.cue:close());assert(f.ends==0)
end)
test('partial spawn faults once and preserves cleanup even after input suspension',function()
    local f=fixture();f.spawn_error=true;f.begin();f.begin()
    assert(f.spawns==1 and #f.errors==1 and f.cue.failed)
    f.focused=false;f.receipt.input_enabled=false
    assert(f.cue:close());assert(f.ends==1 and f.cue.cues.size==0)
end)
test('new owner or world cannot consume old cleanup receipt',function()
    for _,mode in ipairs({'owner','world','identity'})do
        local f=fixture();f.begin()
        if mode=='owner'then f.bridge.active_receipt={}
        elseif mode=='world'then f.same_world=false else f.action.address=4 end
        assert(not f.cue:close());assert(f.ends==0 and f.cue.cues.size==1 and #f.removed==2)
    end
end)
test('destroyed action needs no native cleanup',function()
    local f=fixture();f.begin();f.action.dead=true;assert(f.cue:close());assert(f.ends==0)
end)
test('registration failure removes the first hook and disables queued callbacks',function()
    local f=fixture();assert(f.cue:close());f.register_error=true
    assert(not pcall(f.cue.install,f.cue));assert(not f.cue.enabled and #f.cue.hooks==0)
    f.begin();assert(f.spawns==0)
end)
test('failed native cleanup and hook removal remain retryable',function()
    local f=fixture();f.begin();f.end_error=true;f.unregister_error=true
    assert(not f.cue:close());assert(f.cue.cues.size==1 and #f.cue.hooks==2)
    f.end_error=false;f.unregister_error=false;assert(f.cue:close())
    assert(f.cue.cues.size==0 and #f.cue.hooks==0)
end)
test('retirement requires actual action disposal and never mutates the replacement World',function()
    local f=fixture();f.begin();f.same_world=false
    assert(not pcall(f.cue.retire,f.cue));assert(f.ends==0 and f.cue.cues.size==1)
    f.action.dead=true;assert(f.cue:retire());assert(f.ends==0 and f.cue.cues.size==0 and #f.removed==2)
end)
print('Native cue bridge fixtures: '..total..'; runtime visuals remain unverified')
