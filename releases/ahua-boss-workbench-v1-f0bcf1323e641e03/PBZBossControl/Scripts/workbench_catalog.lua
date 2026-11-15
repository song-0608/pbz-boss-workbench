-- Only independently accepted profiles are selectable. Discovery records remain visible previews.
local Catalog={}
function Catalog.list()
    local result,seen={},{}
    for _,entry in ipairs(require('boss_catalog').list())do
        seen[entry.id]=true
        result[#result+1]={id=entry.id,name=entry.name,profile=entry.profile,playable=true,
            detail=entry.abilities..' 项独立能力 / '..entry.bindings_count..' 个技能绑定；确认后按 F6 接管'}
    end
    for _,entry in ipairs({
        {id='057_wanjun',name='巨锤客：万钧',count=13},
        {id='073_yanqiansui',name='琴女烟千岁',count=24},
        {id='056_youlong',name='056_YouLong',count=32},
    })do
        if not seen[entry.id]then result[#result+1]={id=entry.id,name=entry.name,playable=false,
            reason=entry.id=='056_youlong'and'类默认配置与候选配置不一致，保持锁定'or'身份已核实，独立操控和技能验收尚未通过',
            detail=entry.count..' 条能力路径候选；不等于已授予或可用技能'}end
    end
    return result
end
return Catalog
