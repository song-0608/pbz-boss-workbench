local module=assert(arg[1]);local Workbench=assert(loadfile(module))()
local selected='ahua';local locked,unlocked,switched,checked=0,0,0,0
local mode='denied'
local bench=Workbench.new({entries=function()return{
    {id='ahua',name='阿花',playable=true},{id='073_yanqiansui',name='烟千岁',playable=true},
    {id='locked',name='未适配',playable=false,reason='尚未适配'}}end,selected=function()return selected end})
local adapter={restore=function()return true end,lock=function()locked=locked+1;return true end,
    unlock=function()unlocked=unlocked+1;return true end,
    select=function(id)selected=id;switched=switched+1;return true end,
    check_selection=function(id)
        checked=checked+1;assert(id=='073_yanqiansui')
        if mode=='error'then error('native read failed')end
        return mode=='ready','移至开阔地面'
    end}
bench:set_adapter(adapter);assert(bench:open());bench:move(1)
assert(not bench:confirm()and bench.opened and not bench.busy)
assert(unlocked==0 and switched==0 and selected=='ahua'and checked==1)
assert(bench:text():find('移至开阔地面',1,true))
mode='error';assert(not bench:confirm()and bench.opened and unlocked==0 and switched==0)
assert(not bench:text():find('native read failed',1,true),'hide native implementation details')
bench:move(1);assert(not bench:confirm()and checked==2,'locked rows never query terrain')
bench:move(-2);assert(bench:confirm()and unlocked==1 and checked==2,'same Boss just closes')
assert(bench:open());bench:move(1);mode='ready';assert(bench:confirm())
assert(unlocked==2 and switched==1 and selected=='073_yanqiansui'and bench.busy)
assert(not bench:confirm()and checked==3,'busy confirmation cannot run extra queries')
print('PASS preflight: rejected/error selection preserves current assembly and input owner; valid choice switches once')
