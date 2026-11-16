local candidate=assert(arg[1]);local payload=assert(arg[2])
local profiles=candidate..'/PBZBossControl/Scripts/?.lua;'
package.path=profiles..package.path
local calls,queued,lines,mode=0,nil,{},'flat'
local function valid(o)o.IsValid=function()return true end;return o end
local player=valid({CapsuleComponent=valid({CapsuleHalfHeight=96,CapsuleRadius=42})})
function player:GetAddress()return 101 end
local reads=0
function player:K2_GetActorLocation()
    reads=reads+1
    return{X=mode=='moving'and reads>1 and 1 or 0,Y=0,Z=96}
end
function player:GetActorForwardVector()return{X=1,Y=0,Z=0}end
local pc=valid({Pawn=player})
function pc:GetFullName()return'BP_PlayerController_C /Game/Map.Map:PersistentLevel.Player'end
function FindAllOf(name)
    assert(name=='PBZPlayerController')
    return mode=='ambiguous'and{pc,pc}or{pc}
end
function ExecuteInGameThread(fn)assert(not queued);queued=fn end
function LoadAsset(path)
    local selected
    for _,name in ipairs({'profiles.ahua','profiles.yanqiansui'})do
        local p=require(name)
        if p.class_path==path then selected=p end
    end
    assert(selected,'only exact approved class metadata may be read')
    local config=valid({})
    function config:GetFullName()return'ActorConfig '..selected.config_path end
    function config:GetCharacterName()return{ToString=function()return selected.display_name end}end
    local defaults=valid({['Actor Config']=config,CapsuleComponent=valid({CapsuleHalfHeight=110,CapsuleRadius=48})})
    return valid({GetCDO=function()return defaults end})
end
local library={}
function library:GetNavigationSystem(context)assert(context==pc);return valid({})end
function library:K2_ProjectPointToNavigation(context,p,out,nav,filter,extent)
    assert(context==pc and extent.X==100 and extent.Y==100 and extent.Z==250)
    calls=calls+1
    if mode=='missing' then return false end
    out.X=p.X;out.Y=p.Y;out.Z=0;return true
end
function StaticFindObject(path)
    assert(path=='/Script/NavigationSystem.NavigationSystemV1')
    return valid({GetCDO=function()return library end})
end
local original_print=print
print=function(s)lines[#lines+1]=s end
local function run(next_mode)
    mode=next_mode;calls=0;queued=nil;reads=0;lines={}
    for _,name in ipairs({'arena_layout','yanqiansui_clearance_core','yanqiansui_arena_clearance',
        'ue_arena_layout','boss_selection_preflight','boss_catalog','profiles.ahua','profiles.yanqiansui'})do package.loaded[name]=nil end
    assert(loadfile(payload))()
    assert(calls==0 and queued,'all navigation must wait for the game thread')
    queued()
    assert(calls<=192 and pc.Pawn==player)
    return table.concat(lines,'\n')
end
local output=run('flat')
assert(calls==27 and output:find('PBZ_STARTUP_TERRAIN:TOKEN=123|accepted=true|position_unchanged=true',1,true))
output=run('missing');assert(output:find('accepted=false|position_unchanged=true',1,true))
output=run('ambiguous');assert(calls==0 and output:find('PBZ_STARTUP_TERRAIN:ERROR=123|',1,true))
output=run('moving');assert(output:find('player moved during readonly preflight',1,true)and not output:find('TOKEN=123|accepted=',1,true))
print=original_print
print('PASS startup preflight: game-thread one shot, exact classes, 27 normal / <=192 queries, no spawn or movement, refusal and identity/motion errors')
