-- 用途：改键只能操作本轮已验收入口，不能通过JSON把禁用能力开放。
local root=assert(arg[1]);package.path=root..'/mod/PBZBossControl/Scripts/?.lua;'..package.path
local apply=require('keymap').apply
local config={controls={enter='F6',exit='F10'},skills={
    hit={id='skill01',key='F1',verified=true},blocked={id='attack01',key='F2',verified=false},
    lab={id='candidate',lab_only=true,verified=true}}}
apply(config,{controls={enter='F11'},skills={hit='Q',blocked='E',lab='F9',missing='R'}})
assert(config.controls.enter=='F11'and config.skills.hit.key=='Q')
assert(config.skills.blocked.verified==false and config.skills.blocked.key=='F2')
assert(config.skills.lab.key==nil and config.skills.missing==nil)
print('PASS keymap preserves disabled abilities and developer bank')
