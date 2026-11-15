-- 用途：输入屏障只属于自建镜头；验证部分失败清理和重复退出，不启动游戏。
local root=assert(arg[1]);package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local B=require('input_barrier');local n=0
local function fixture()
    local f={pc={},owner={},receipt={},disabled=0}
    local calls={reference=function(_,x)return x end,resolve=function(_,x)return x end}
    f.service=B.new(calls,{empty=function()return not f.owner.component end,
        enable=function(o) o.component=true;if f.fail then error('partial enable failure')end;o.blocked=true end,
        verify=function(o)return o.component and o.blocked end,
        disable=function(o)f.disabled=f.disabled+1;o.blocked=false end},{binding_verified=true})
    return f
end
local function test(name,fn)assert(pcall(fn),name);n=n+1;print('PASS '..name)end
test('fresh owned layer blocks and restores',function()local f=fixture();f.service:attach(f.pc,f.owner,f.receipt);assert(f.service:verify(f.receipt.input_barrier));f.service:detach(f.receipt.input_barrier);assert(not f.owner.blocked and f.disabled==1)end)
test('existing component preserved',function()local f=fixture();f.owner.component=true;assert(not pcall(function()f.service:attach(f.pc,f.owner,f.receipt)end));assert(not f.receipt.input_barrier and f.disabled==0)end)
test('partial enable retains cleanup responsibility',function()local f=fixture();f.fail=true;assert(not pcall(function()f.service:attach(f.pc,f.owner,f.receipt)end));assert(f.receipt.input_barrier);f.service:detach(f.receipt.input_barrier);assert(f.disabled==1)end)
test('repeated exit removes its own layer once',function()local f=fixture();f.service:attach(f.pc,f.owner,f.receipt);f.service:detach(f.receipt.input_barrier);f.service:detach(f.receipt.input_barrier);assert(f.disabled==1)end)
print('Input barrier fixtures: '..n..' passed; runtime input consumption remains separate.')
