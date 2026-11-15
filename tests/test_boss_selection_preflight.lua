local root=assert(arg[1]);package.path=root..'/tools/?.lua;'..root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local Check=require('boss_selection_preflight');local queries=0;local flat=true
package.loaded.ue_arena_layout={new=function()return function(p)
    queries=queries+1
    if not flat and math.abs(p.Y)>150 then return nil end
    return{X=p.X,Y=p.Y,Z=0}
end end}
local profile={identity_verified=true,exe_sha256='build',class_path='/Class',config_path='/Config',
    display_name='fixture',training_target_profile='fixture_target'}
package.loaded.boss_catalog={profile=function(id)assert(id=='073_yanqiansui');return profile end}
package.loaded.fixture_target=profile
local function obj(v)v=v or{};v.IsValid=function()return true end;return v end
local capsule=obj{CapsuleHalfHeight=96,CapsuleRadius=45}
local config=obj{GetFullName=function()return'Fixture /Config'end,
    GetCharacterName=function()return{ToString=function()return'fixture'end}end}
local defaults=obj{CapsuleComponent=capsule,['Actor Config']=config}
local globals={LoadAsset=function(path)assert(path=='/Class');return obj{GetCDO=function()return defaults end}end}
local player=obj{CapsuleComponent=capsule,GetAddress=function()return 1 end,
    K2_GetActorLocation=function()return{X=0,Y=0,Z=96}end,
    GetActorForwardVector=function()return{X=1,Y=0,Z=0}end}
local pc=obj{Pawn=player}
local function valid(v)return v and v:IsValid()end
local function verify(id)return Check.verify(globals,{},pc,player,id or'073_yanqiansui',valid,'build')end
assert(verify('ahua')and queries==0,'other Boss paths do not query navigation')
assert(verify()and queries==27,'flat selection is bounded and read-only')
queries=0;flat=false;local ok,why=verify()
assert(not ok and why:find('9米',1,true)and queries<=192,'narrow terrain preserves refusal')
flat=true;pc.Pawn=obj{GetAddress=function()return 2 end};assert(not pcall(verify),'stale player refused')
pc.Pawn=player;profile.config_path='/Wrong';assert(not pcall(verify),'wrong class/config refused')
profile.config_path='/Config';profile.exe_sha256='foreign';assert(not pcall(verify),'wrong build refused')
print('PASS native preflight: no other-Boss navigation, exact identity/player, bounded terrain and no spawning')
