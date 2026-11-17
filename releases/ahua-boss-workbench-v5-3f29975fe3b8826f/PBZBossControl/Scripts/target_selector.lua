-- 用途：只读筛选同场景、存活、敌对、在距离内的目标；每次按键重查，不缓存旧关卡对象。
local Selector={};Selector.__index=Selector
local function finite(n)return type(n)=='number'and n==n and math.abs(n)<math.huge end
local function position(p)return p and finite(p.X)and finite(p.Y)and finite(p.Z)end
function Selector.new(calls,native,options)
    options=options or{}
    for _,name in ipairs({'candidates','health','position','relation'})do assert(type(native[name])=='function','missing target reader: '..name)end
    if options.require_visibility then assert(type(native.visible)=='function','verified visibility reader required')end
    local radius,limit=options.radius or 3000,options.limit or 256
    assert(finite(radius)and radius>0 and math.type(limit)=='integer'and limit>0,'invalid target scan bounds')
    return setmetatable({calls=calls,native=native,radius=radius,limit=limit,hostile=options.hostile or 2},Selector)
end
function Selector:eligible(boss,player,target)
    local ok,distance=pcall(function()
        assert(target and target:IsValid(),'invalid target')
        if self.native.usable then assert(self.native.usable(target),'actor is being destroyed')end
        assert(not self.calls:same(target,boss)and not self.calls:same(target,player),'self or saved player')
        local a,b=self.calls:world(boss),self.calls:world(target)
        assert(a.address==b.address and a.name==b.name,'other world')
        local health=self.native.health(target);assert(finite(health)and health>0,'not living')
        assert(self.native.relation(boss,target)==self.hostile,'not hostile')
        local p,q=self.native.position(boss),self.native.position(target)
        assert(position(p)and position(q),'invalid position')
        local d=(p.X-q.X)^2+(p.Y-q.Y)^2+(p.Z-q.Z)^2
        assert(d<=self.radius^2,'outside target radius')
        if self.native.visible then assert(self.native.visible(boss,target)==true,'target visibility not verified')end
        return d
    end)
    return ok,distance -- 失败时保留pcall捕获的具体拒绝原因；调用方仍先检查ok。
end
function Selector:next(boss,player,current)
    local candidates=self.native.candidates()or{}
    -- 用途：数量过大时明确拒绝，避免只扫描前半列表却把遗漏说成“没有敌人”。
    if #candidates>self.limit then return nil,'target scan bound exceeded' end
    local rows,seen={},{}
    for _,target in ipairs(candidates)do
        local allowed,distance=self:eligible(boss,player,target)
        if allowed then
            local ref=self.calls:reference(target)
            local key=ref.name..'|'..tostring(ref.address)
            if not seen[key]then rows[#rows+1]={actor=target,ref=ref,key=key,distance=distance};seen[key]=true end
        end
    end
    -- 用途：稳定名称排序用于循环；首次无目标才选最近对象，移动不改变循环次序。
    table.sort(rows,function(a,b)return a.key<b.key end)
    if #rows==0 then return nil,self.native.visible and'no visible living hostile target within radius'or'no living hostile target within radius' end
    if current then
        for i,row in ipairs(rows)do
            if self.calls:same(row.actor,current)then
                if #rows==1 then return nil,'no alternate hostile target' end
                return rows[i%#rows+1].actor,nil,#rows
            end
        end
    end
    local nearest=rows[1]
    for _,row in ipairs(rows)do if row.distance<nearest.distance then nearest=row end end
    return nearest.actor,nil,#rows
end
return Selector
