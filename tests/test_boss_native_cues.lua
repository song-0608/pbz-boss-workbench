local root=assert(arg[1],'project required')
package.path=root..'/tools/?.lua;'..package.path
local Cues=require('boss_native_cues')
local total=0
local function test(name,fn)fn();total=total+1;print('PASS '..name)end
local function fixture()
    local f={action={name='Action A',address=32,class='CueClass',count=0},owned=true,spawns=0,ends=0}
    local a={owner=function()return'lease|world|boss'end,eligible=function()return f.owned end,
        reference=function(x)return{name=x.name,address=x.address,class=x.class}end,
        resolve=function()return f.action end,count=function(x)return x.count end,
        spawn=function(x)f.spawns=f.spawns+1;x.count=1;return true end,
        finish=function(x)f.ends=f.ends+1;x.count=0;return true end}
    f.adapter=a;f.cues=Cues.new(a);return f
end
test('unowned action and original visible cues are untouched',function()
    local f=fixture();f.owned=false;assert(not f.cues:on_begin(f.action));assert(f.spawns==0)
    f.owned=true;f.action.count=1;assert(not f.cues:on_begin(f.action));assert(f.spawns==0)
end)
test('native begin fallback spawns once and original end is not duplicated',function()
    local f=fixture();assert(f.cues:on_begin(f.action));assert(not f.cues:on_begin(f.action));assert(f.spawns==1)
    f.action.count=0;assert(f.cues:on_end(f.action));assert(f.ends==0 and f.cues.size==0)
    assert(f.cues:on_begin(f.action));assert(f.spawns==2)
end)
test('restore ends only components tracked by the current controller',function()
    local f=fixture();assert(f.cues:on_begin(f.action));assert(f.cues:cleanup())
    assert(f.ends==1 and f.action.count==0 and f.cues.size==0);assert(f.cues:cleanup());assert(f.ends==1)
end)
test('partial spawn failure retains cleanup responsibility',function()
    local f=fixture();f.adapter.spawn=function(x)x.count=1;error('partial native spawn')end
    assert(not pcall(f.cues.on_begin,f.cues,f.action));assert(f.cues.size==1)
    assert(f.cues:cleanup());assert(f.ends==1 and f.cues.size==0)
end)
test('reused action identity or changed world is never cleaned through old owner',function()
    for _,mode in ipairs({'identity','world'})do
        local f=fixture();assert(f.cues:on_begin(f.action))
        if mode=='identity'then f.action.address=64 else f.owned=false end
        assert(not f.cues:cleanup());assert(f.ends==0 and f.cues.size==1)
    end
end)
test('destroyed action retires without a native call',function()
    local f=fixture();assert(f.cues:on_begin(f.action));f.action=nil
    assert(f.cues:cleanup());assert(f.ends==0 and f.cues.size==0)
end)
test('empty native spawn never becomes a visual success',function()
    local f=fixture();f.adapter.spawn=function()return true end
    assert(not f.cues:on_begin(f.action));assert(f.cues.size==1)
    assert(f.cues:cleanup())
end)
test('failed native end is retained for retry',function()
    local f=fixture();assert(f.cues:on_begin(f.action));f.adapter.finish=function()return false end
    assert(not f.cues:cleanup());assert(f.cues.size==1)
    f.adapter.finish=function(x)x.count=0;return true end
    assert(f.cues:cleanup());assert(f.cues.size==0)
end)
test('end notification retains failed cleanup rather than losing ownership',function()
    local f=fixture();assert(f.cues:on_begin(f.action));f.adapter.finish=function()return false end
    assert(not pcall(f.cues.on_end,f.cues,f.action));assert(f.cues.size==1)
    f.adapter.finish=function(x)x.count=0;return true end
    assert(f.cues:on_end(f.action));assert(f.cues.size==0)
end)
print('Native cue lifecycle fixtures: '..total..'; visual behavior remains unverified')
