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
        {id='056_youlong',name='发狂的水行帮主：游龙',count=32},
    })do
        if not seen[entry.id]then result[#result+1]={id=entry.id,name=entry.name,playable=false,
            reason='身份已核实，独立操控和技能验收尚未通过',
            detail=entry.count..' 条能力路径候选；不等于已授予或可用技能'}end
    end
    for _,entry in ipairs({{["id"]="054_zuoshang",["name"]="054_ZuoShang（资源候选）",["playable"]=false,["reason"]="等待合批身份与技能元数据核验",["detail"]="1个角色类候选 / 1个配置候选 / 27项能力元数据请求；尚不可接管",["stage"]="metadata_ready"},{["id"]="066_rentuzi",["name"]="066_RenTuZi（资源候选）",["playable"]=false,["reason"]="等待合批身份与技能元数据核验",["detail"]="1个角色类候选 / 1个配置候选 / 11项能力元数据请求；尚不可接管",["stage"]="metadata_ready"},{["id"]="071_xianzhe",["name"]="071_XianZhe（资源候选）",["playable"]=false,["reason"]="等待合批身份与技能元数据核验",["detail"]="1个角色类候选 / 1个配置候选 / 9项能力元数据请求；尚不可接管",["stage"]="metadata_ready"},{["id"]="058_maddoctor",["name"]="058_MadDoctor（资源候选）",["playable"]=false,["reason"]="主身/阶段配置待核对",["detail"]="2个角色类候选 / 2个配置候选 / 14项能力元数据请求；尚不可接管",["stage"]="variant_binding_required"},{["id"]="067_motian",["name"]="067_MoTian（资源候选）",["playable"]=false,["reason"]="主身/阶段配置待核对",["detail"]="2个角色类候选 / 3个配置候选 / 36项能力元数据请求；尚不可接管",["stage"]="variant_binding_required"},{["id"]="076_zuoshang_p2",["name"]="076_ZuoShang_P2（资源候选）",["playable"]=false,["reason"]="主身/阶段配置待核对",["detail"]="1个角色类候选 / 2个配置候选 / 14项能力元数据请求；尚不可接管",["stage"]="variant_binding_required"}})do
        if not seen[entry.id]then result[#result+1]=entry;seen[entry.id]=true end
    end
    return result
end
return Catalog
