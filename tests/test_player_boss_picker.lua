local root=assert(arg[1]);local Picker=dofile(root..'/tools/player_boss_picker.lua')
local entries={}
for i=1,10 do entries[i]={id='boss-'..i,name='Boss '..i,playable=i<=4,detail='detail-'..i,reason='pending-'..i}end
local text=Picker.render(entries,9,'boss-1','',false)
assert(text:find('可操控 4',1,true)and text:find('适配中 6',1,true))
assert(text:find('▶ Boss 9',1,true)and text:find('detail-9',1,true)and text:find('pending-9',1,true))
assert(not text:find('Enter 确认后按 F6',1,true),'preview cannot display playable controls')
assert(not text:find('Boss 1  [',1,true),'seven-row viewport must follow cursor')
text=Picker.render(entries,1,'boss-1','message',false)
assert(text:find('当前角色',1,true)and text:find('Enter 确认后按 F6',1,true)and text:find('message',1,true))
text=Picker.render(entries,1,'boss-1','',true)
assert(text:find('正在恢复主角并安全切换',1,true)and not text:find('▶',1,true))
assert(not pcall(Picker.render,{},1,'one','',false))
print('PASS ten-entry selection panel, cursor paging, current Boss, metadata quarantine and switching state')
