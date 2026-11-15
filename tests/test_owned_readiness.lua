local root=assert(arg[1]);package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local Ready=require('owned_readiness');local total=0
local expected={{X=450,Y=0,Z=100},{X=700,Y=0,Z=100},{X=650,Y=300,Z=100}}
local function fixture()
    local gate=Ready.new({X=0,Y=0,Z=100},expected);local rows={}
    for i,p in ipairs(expected)do rows[i]={health=9000,position={X=p.X,Y=p.Y,Z=p.Z},velocity={X=0,Y=0,Z=0}}end
    return gate,rows
end
local function test(name,fn)local ok,why=pcall(fn);assert(ok,name..': '..tostring(why));total=total+1;print('PASS '..name)end
local function rejects(gate,rows)assert(not pcall(gate.poll,gate,rows))end
test('five fresh stable samples before readiness',function()
    local g,r=fixture();for i=1,4 do assert(not g:poll(r))end;assert(g:poll(r))
end)
test('movement resets consecutive stability',function()
    local g,r=fixture();for i=1,4 do assert(not g:poll(r))end
    r[1].velocity.X=3;assert(not g:poll(r));r[1].velocity.X=0
    for i=1,3 do assert(not g:poll(r))end;assert(g:poll(r))
end)
test('changing health resets stability without overwriting health',function()
    local g,r=fixture();for i=1,4 do assert(not g:poll(r))end
    r[2].health=8999;assert(not g:poll(r));assert(r[2].health==8999)
end)
test('dead invalid and nonfinite health reject before readiness',function()
    for _,v in ipairs({0,-1,math.huge,0/0,'9000'})do local g,r=fixture();r[1].health=v;rejects(g,r)end
end)
test('drift fall and player proximity reject',function()
    for _,p in ipairs({{X=650,Y=0,Z=100},{X=450,Y=0,Z=-100},{X=200,Y=0,Z=100}})do
        local g,r=fixture();r[1].position=p;rejects(g,r)
    end
end)
test('nonfinite vectors and missing participants reject',function()
    local g,r=fixture();r[2].velocity.X=0/0;rejects(g,r)
    g,r=fixture();r[3]=nil;rejects(g,r)
end)
print('Owned readiness fixtures passed: '..total)
