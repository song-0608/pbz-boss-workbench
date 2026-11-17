local directory=assert(arg[1])..'/PBZCoop/Scripts/'
local dependencies=dofile(directory..'bwb_local_dependencies.lua')(directory)
local Policy=dependencies.policy
local checks=0
local function check(name,fn)fn();checks=checks+1;print('PASS '..name)end
check('all accepted profiles have independently declared terrain policies',function()
    local catalog=dependencies.require('boss_catalog');local count=0
    for _,entry in ipairs(catalog.list())do
        assert(Policy.resolve(catalog.profile(entry.id)).layout_module);count=count+1
    end
    assert(count==4)
end)
check('ordinary profiles share the generic terrain engine',function()
    for _,id in ipairs({'ahua_guitoudao','057_wanjun','056_youlong'})do
        assert(Policy.resolve({id=id}).layout_module=='arena_layout')
    end
end)
check('YanQianSui retains the accepted nine-meter and twenty-four-sample rule',function()
    local rule=Policy.resolve({id='073_yanqiansui'})
    assert(rule.layout_module=='yanqiansui_clearance_core'and rule.clearance_cm==900 and rule.clearance_samples==24)
end)
check('unknown Bosses cannot inherit another terrain policy',function()
    local loaded=0
    assert(not pcall(Policy.choose,{id='054_zuoshang'},function()loaded=loaded+1 end))
    assert(loaded==0 and not pcall(Policy.resolve,{})and not pcall(Policy.resolve,nil))
end)
check('a caller cannot mutate another assembly terrain requirements',function()
    local rule=Policy.resolve({id='073_yanqiansui'});rule.clearance_cm=1;rule.layout_module='other'
    assert(Policy.resolve({id='073_yanqiansui'}).clearance_cm==900)
    assert(Policy.resolve({id='073_yanqiansui'}).layout_module=='yanqiansui_clearance_core')
end)
check('shared planner forwards original native terrain arguments',function()
    local a,b={},{}
    local result=Policy.choose({id='057_wanjun'},function(name)
        assert(name=='arena_layout');return {choose=function(x,y,n)assert(x==a and y==b and n==7);return a end}
    end,a,b,7)
    assert(result==a)
end)
check('terrain rejection preserves its diagnostic without changing the result',function()
    local result,why=Policy.choose({id='073_yanqiansui'},function()
        return {choose=function()return nil,'not enough flat space'end}
    end)
    assert(result==nil and why=='not enough flat space')
end)
check('special terrain acceptance requires both reviewed measurements',function()
    for _,layout in ipairs({{clearance_cm=899,clearance_samples=24},{clearance_cm=900,clearance_samples=23}})do
        assert(not pcall(Policy.choose,{id='073_yanqiansui'},function()return {choose=function()return layout end}end))
    end
    assert(Policy.choose({id='073_yanqiansui'},function()return {choose=function()
        return {clearance_cm=900,clearance_samples=24}
    end}end))
end)
print('PASS '..checks..' profile policy groups; pure planning, no game started')
