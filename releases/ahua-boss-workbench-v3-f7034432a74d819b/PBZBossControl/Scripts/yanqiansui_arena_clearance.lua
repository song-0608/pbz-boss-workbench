-- One bounded initialization trace. The frozen search makes all decisions.
local Core=require('yanqiansui_clearance_core')
local Trace={}
local function number(v)return type(v)=='number'and v==v and math.abs(v)<math.huge end
local function point(p)return type(p)=='table'and number(p.X)and number(p.Y)and number(p.Z)end
local function xyz(p)
    if not point(p)then return 'unavailable'end
    return string.format('%.3f,%.3f,%.3f',p.X,p.Y,p.Z)
end
function Trace.choose(project,origin,forward,...)
    local rows={}
    local function observe(desired)
        local value=project(desired)
        rows[#rows+1]='wanted='..xyz(desired)..'|actual='..xyz(value)
        return value
    end
    local results=table.pack(pcall(Core.choose,observe,origin,forward,...))
    assert(#rows<=192,'terrain trace must retain the frozen navigation budget')
    if type(print)=='function'then
        local lines={'PBZ_TERRAIN_TRACE:BEGIN=origin:'..xyz(origin)..'|forward:'..xyz(forward)}
        for index,row in ipairs(rows)do lines[#lines+1]='PBZ_TERRAIN_TRACE:QUERY='..index..'|'..row end
        lines[#lines+1]='PBZ_TERRAIN_TRACE:END=queries:'..#rows..'|accepted:'..tostring(results[1]and results[2]~=nil)
        print(table.concat(lines,'\n')..'\n')
    end
    if not results[1]then error(results[2],0)end
    return table.unpack(results,2,results.n)
end
return Trace
