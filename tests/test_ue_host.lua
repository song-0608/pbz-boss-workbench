local root=assert(arg[1]);package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local previous=package.loaded.ue_input
package.loaded.ue_input={new=function()return{read=function()return{}end}end}
local Host=require('ue_host');local registered={};local callbacks={};local frame_callbacks={}
local function noop()end
local g={EngineTickAvailable=true,LoopInGameThreadAfterFrames=function(_,fn)frame_callbacks[#frame_callbacks+1]=fn;return #frame_callbacks end,
    CancelDelayedAction=function(id)frame_callbacks[id]=false end,ExecuteInGameThread=noop,FName=function(value)return value end,
    StaticFindObject=function()return{IsValid=function()return true end}end,
    RegisterKeyBind=function(key,fn)registered[#registered+1]=key;callbacks[key]=fn end,
    Key={INS=45,UP_ARROW=38,DOWN_ARROW=40,RETURN=13},print=noop}
local host=Host.new({}, {},g)
host.validate_keys({INS=true,UP_ARROW=true,DOWN_ARROW=true,RETURN=true})
assert(not pcall(host.validate_keys,{UP=true})and #registered==0)
host.bind_key('UP_ARROW',noop);assert(registered[1]==38)
local old_count,new_count=0,0
host.bind_key('INS',function()old_count=old_count+1 end)
callbacks[45]();assert(old_count==1)
local replacement=Host.new({}, {},g)
replacement.bind_key('INS',function()new_count=new_count+1 end)
host.release_keys();callbacks[45]()
assert(old_count==1 and new_count==1,'old host cleanup must preserve replacement route')
assert(#registered==2,'Boss reassembly must not accumulate native key callbacks')
replacement.release_keys();callbacks[45]();assert(new_count==1,'retired runtime callback must be released')
local down,closed=true,0
local release_host=Host.new({player_controller=function()return{IsInputKeyDown=function(_,key)
    assert(key.KeyName=='Escape');return down end}end},{},g)
local handle=release_host.after_key_release('ESCAPE',function()closed=closed+1 end)
local release_callback=frame_callbacks[handle]
release_callback();release_callback();assert(closed==0 and frame_callbacks[handle]==release_callback)
down=false;release_callback()
assert(closed==1 and frame_callbacks[handle]==false,'release timer must explicitly cancel itself')
release_callback();assert(closed==1,'a stale queued frame must not invoke the action twice')
local pending=release_host.after_key_release('INS',noop)
release_host.release_keys();assert(frame_callbacks[pending]==false)
package.loaded.ue_input=previous
print('PASS native workbench key enumeration and side-effect-free validation')
