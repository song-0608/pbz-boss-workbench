local root=assert(arg[1]);local Input=dofile(root..'/tools/player_action_input.lua')
local events,registered={},0
local g={Key={F1=112,LEFT_MOUSE_BUTTON=1},ModifierKey={SHIFT=16}}
g.RegisterKeyBind=function(key,modifiers,fn)
    if type(modifiers)=='function'then fn=modifiers;modifiers={}end
    local chord=tostring(key)..':'..table.concat(modifiers,',')
    assert(not events[chord],'native callback must not accumulate');events[chord]=fn;registered=registered+1
end
local old,new=0,0
local input=Input.new(g);input:bind('F1',function()old=old+1 end)
events['112:']();events['112:16']();assert(old==2 and registered==2)
assert(not events['112:17']and not events['112:18'],'Ctrl/Alt must remain unregistered')
assert(not pcall(input.bind,input,'F1',function()end),'duplicate owner binding rejected')
local replacement=Input.new(g);replacement:bind('F1',function()new=new+1 end)
input:close();events['112:']();events['112:16']()
assert(old==2 and new==2 and registered==2,'retired owner must preserve replacement')
replacement:bind('LEFT_MOUSE_BUTTON',function()new=new+1 end)
events['1:16']();assert(new==3 and registered==4)
replacement:close();events['1:16']();events['112:']();assert(new==3)
assert(not pcall(replacement.bind,replacement,'F1',function()end))
print('PASS bare/Shift skills, mouse variants, native focus path, bounded routes and owner cleanup')
