-- Player-facing Boss chooser. All native work stays behind the current assembly adapter.
local Workbench={};Workbench.__index=Workbench
function Workbench.new(options)
    assert(type(options)=='table'and type(options.entries)=='function'
        and type(options.selected)=='function','workbench catalog required')
    local cursor=1
    for index,entry in ipairs(options.entries())do if entry.id==options.selected()then cursor=index end end
    return setmetatable({options=options,opened=false,busy=false,cursor=cursor,message='',revision=0},Workbench)
end
function Workbench:set_adapter(adapter)
    assert(not self.opened,'close workbench before replacing its native adapter')
    assert(type(adapter)=='table'and type(adapter.restore)=='function'and type(adapter.lock)=='function'
        and type(adapter.unlock)=='function'and type(adapter.select)=='function','workbench adapter incomplete')
    self.adapter=adapter;self.busy=false
end
function Workbench:is_open()return self.opened or self.busy end
function Workbench:changed(message)
    self.message=message or '';self.revision=self.revision+1
end
function Workbench:open()
    if self.busy then return false,'正在切换角色'end
    if self.opened then return true end
    local ready,why=self.adapter.restore('open Boss workbench')
    if ready~=true then self:changed('恢复主角未完成，工作台保持关闭');return false,why end
    local ok,locked,problem=pcall(self.adapter.lock)
    if not ok or locked~=true then
        assert(self.adapter.unlock()==true,'workbench rollback failed')
        return false,ok and problem or locked
    end
    self.opened=true;self:changed('选择角色后按 Enter；Insert 或 Esc 返回')
    return true
end
function Workbench:close()
    if self.busy then return false,'正在切换角色'end
    if not self.opened then return true end
    assert(self.adapter.unlock()==true,'workbench input restoration failed')
    self.opened=false;self:changed();return true
end
function Workbench:shutdown()
    if self.adapter then assert(self.adapter.unlock()==true,'workbench shutdown restoration failed')end
    self.opened=false;self.busy=false;self:changed();return true
end
function Workbench:toggle()if self.opened then return self:close()else return self:open()end end
function Workbench:move(delta)
    if not self.opened or self.busy then return false end
    local entries=self.options.entries();assert(#entries>0 and #entries<=128,'bounded Boss catalog required')
    self.cursor=((self.cursor-1+delta)%#entries)+1;self:changed();return true
end
function Workbench:confirm()
    if not self.opened or self.busy then return false end
    local entry=assert(self.options.entries()[self.cursor],'workbench selection unavailable')
    if entry.playable~=true then self:changed(entry.reason or'此角色仍在适配，暂不可接管');return false,self.message end
    if entry.id==self.options.selected()then return self:close()end
    if self.adapter.check_selection then
        local ok,ready,reason=pcall(self.adapter.check_selection,entry.id)
        if not ok or ready~=true then
            self:changed(ok and (reason or '当前位置无法切换，请返回后重试') or '角色检查未完成，请返回后重试')
            return false,self.message
        end
    end
    assert(self.adapter.unlock()==true,'workbench input restoration failed')
    self.opened=false;self.busy=true;self:changed('正在安全切换角色…')
    local ok,result,why=pcall(self.adapter.select,entry.id)
    if not ok or result~=true then self.busy=false;self:changed('切换未完成：'..tostring(ok and why or result));return false,self.message end
    return true
end
function Workbench:text()
    return require('player_boss_picker').render(self.options.entries(),self.cursor,self.options.selected(),self.message,self.busy)
end
return Workbench
