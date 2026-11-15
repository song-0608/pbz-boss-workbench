local root=assert(arg[1]);package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local Workbench=require('boss_workbench')
local selected='one';local restored,locked,unlocked,switches=0,0,0,0
local entries={{id='one',name='First',playable=true},{id='two',name='Second',playable=true},
 {id='pending',name='Preview',playable=false,reason='independent evidence missing'}}
local bench=Workbench.new({entries=function()return entries end,selected=function()return selected end})
local adapter={restore=function()restored=restored+1;return true end,
 lock=function()locked=locked+1;return true end,unlock=function()unlocked=unlocked+1;return true end,
 select=function(id)selected=id;switches=switches+1;return true end}
bench:set_adapter(adapter)
assert(bench:open()and restored==1 and locked==1)
assert(bench:open()and restored==1 and locked==1,'repeated F11 callback must not duplicate native owners')
bench:move(2);assert(not bench:confirm()and switches==0 and bench.opened)
assert(bench:text():find('independent evidence missing',1,true))
bench:move(-1);assert(bench:confirm()and selected=='two'and switches==1 and unlocked==1 and bench.busy)
assert(not bench:confirm()and not bench:move(1));bench:set_adapter(adapter)
assert(bench:open());assert(bench:confirm()and not bench:is_open()and switches==1)
adapter.restore=function()return false,'restoration failed'end
assert(not bench:open()and locked==2)
adapter.restore=function()return true end
adapter.lock=function()error('partial construction')end
local before=unlocked;assert(not bench:open()and unlocked==before+1 and not bench.opened)
adapter.lock=function()return true end
assert(bench:open());adapter.unlock=function()return false end
assert(not pcall(bench.close,bench),'failed restore cannot be reported as closed')
adapter.unlock=function()return true end;assert(bench:shutdown()and not bench:is_open())
print('PASS Boss workbench selection, preview quarantine, restore rollback and switch serialization')
