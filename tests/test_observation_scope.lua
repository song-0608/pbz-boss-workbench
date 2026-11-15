-- 用途：复现F10后旧延迟回调与再次接管；确认只停止旧采样，当前回调仍暴露真实错误。
local root=assert(arg[1]);package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local Scope=require('observation_scope');local count=0
local function test(name,fn)local ok,why=pcall(fn);assert(ok,name..': '..tostring(why));count=count+1;print('PASS '..name)end
test('F10 release ends old observer before accessing released receipt',function()
    local s={state='ACTIVE',receipt={camera_rig={}}};local scope=Scope.capture(s)
    s.state='OFF';s.receipt=nil
    local reads=0;local function delayed()if not scope:current()then return end;reads=reads+1;assert(s.receipt.camera_rig)end
    delayed();assert(reads==0)
end)
test('old observer cannot attach itself to a new control receipt',function()
    local s={state='ACTIVE',receipt={}};local old=Scope.capture(s)
    s.receipt={};local current=Scope.capture(s)
    assert(not old:current() and current:current())
end)
test('restoring blocks reads even while receipt still exists',function()
    local s={state='ACTIVE',receipt={}};local scope=Scope.capture(s);s.state='RESTORING';assert(not scope:current())
end)
test('active observer does not suppress real callback failure',function()
    local s={state='ACTIVE',receipt={}};local scope=Scope.capture(s)
    local function delayed()if not scope:current()then return end;error('real active failure')end
    assert(not pcall(delayed))
end)
print('Observation scope fixtures passed: '..count)
