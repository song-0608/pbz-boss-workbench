-- Read-only final gate for the exact three owned training actors, before exposing the player.
local Ready={};Ready.__index=Ready
local function finite(v)return type(v)=='number'and v==v and math.abs(v)<math.huge end
local function point(p)return p and finite(p.X)and finite(p.Y)and finite(p.Z)end
local function distance2(a,b)return(a.X-b.X)^2+(a.Y-b.Y)^2+(a.Z-b.Z)^2 end
function Ready.new(origin,expected)
    assert(point(origin)and type(expected)=='table'and #expected==3,'bounded owned layout required')
    return setmetatable({origin=origin,expected=expected,last={},stable=0},Ready)
end
function Ready:poll(rows)
    assert(type(rows)=='table'and #rows==3,'exact owned participants required')
    local settled=true;local next_rows={}
    for index,row in ipairs(rows)do
        assert(finite(row.health)and row.health>0,'owned participant is not alive: '..index..'|health='..tostring(row.health))
        assert(point(row.position)and point(row.velocity),'owned position/velocity unreadable: '..index)
        assert(distance2(row.position,self.expected[index])<=150^2,'owned participant drifted from verified spawn: '..index)
        local dx,dy=row.position.X-self.origin.X,row.position.Y-self.origin.Y
        assert(dx*dx+dy*dy>=250^2,'owned participant approached protected player: '..index)
        local old=self.last[index]
        if not old or old.health~=row.health or distance2(old.position,row.position)>4
            or row.velocity.X^2+row.velocity.Y^2+row.velocity.Z^2>=4 then settled=false end
        next_rows[index]={health=row.health,position={X=row.position.X,Y=row.position.Y,Z=row.position.Z}}
    end
    self.last=next_rows;self.stable=settled and self.stable+1 or 0
    return self.stable>=4
end
return Ready
