-- Basic in-game selection panel, rendered by the existing nonactivating companion overlay.
local Picker={}
function Picker.render(entries,cursor,selected,message,busy)
    assert(type(entries)=='table'and #entries>0 and #entries<=128,'bounded picker roster required')
    assert(math.type(cursor)=='integer'and entries[cursor],'valid picker cursor required')
    local playable=0
    for _,entry in ipairs(entries)do
        assert(type(entry.id)=='string'and type(entry.name)=='string'and type(entry.playable)=='boolean','typed picker entry required')
        if entry.playable then playable=playable+1 end
    end
    local rows={'Boss 工作台  |  Insert 开关',
        string.format('角色选择    可操控 %d    适配中 %d',playable,#entries-playable)}
    if busy then rows[#rows+1]='正在恢复主角并安全切换，请稍候'
    else
        rows[#rows+1]='↑ / ↓ 浏览  |  Enter 选择  |  Esc 返回'
        local first=math.min(math.max(1,cursor-3),math.max(1,#entries-6))
        for index=first,math.min(#entries,first+6)do
            local entry=entries[index]
            local state=entry.playable and(entry.id==selected and'当前角色'or'可选择')or'适配中'
            rows[#rows+1]=(index==cursor and'▶ 'or'   ')..entry.name..'  ['..state..']'
        end
        local current=entries[cursor]
        rows[#rows+1]=string.format('─ %d / %d ─ %s',cursor,#entries,current.name)
        if current.detail then rows[#rows+1]=current.detail end
        rows[#rows+1]=current.playable and'Enter 确认后按 F6 接管；中键锁敌，F7切换目标'
            or(current.reason or'身份与技能验收尚未完成')
    end
    if message and message~=''then rows[#rows+1]=message end
    return table.concat(rows,'\n')
end
return Picker
