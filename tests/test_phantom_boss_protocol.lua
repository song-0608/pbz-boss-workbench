local root = assert(arg[1])
package.path = root .. '/tools/?.lua;' .. package.path
local protocol = require('phantom_boss_protocol')
local checks = 0
local function check(name, fn)
    fn(); checks = checks + 1; print('PASS ' .. name)
end
local SHA, BUILD = string.rep('a', 64), string.rep('b', 64)
local bosses = { ahua = { class_path = '/Boss/Ahua.Ahua_C', actions = { cut = '/Ability/Cut.Cut_C' } },
    youlong = { class_path = '/Boss/YouLong.YouLong_C', actions = { dodge = '/Ability/Dodge.Dodge_C' } } }
local function pair()
    local hq, gq, actions, cleared = {}, {}, {}, {}
    local function make(role, queue)
        return protocol.new { role = role, session = 'research_1', catalog = SHA, build = BUILD,
            bosses = bosses, send = function(kind, data)
                assert(kind == protocol.EVENT and #data < 850); queue[#queue + 1] = data
            end, on_action = function(...) actions[#actions + 1] = {...} end,
            on_clear = function(reason) cleared[#cleared + 1] = reason end }
    end
    local h, g = make('host', hq), make('guest', gq)
    h:select('ahua', 0); g:select('youlong', 0)
    h:set_link(true, 0); g:set_link(true, 0)
    local function drain(now)
        while #hq > 0 do g:receive(table.remove(hq, 1), 'host', now) end
        while #gq > 0 do h:receive(table.remove(gq, 1), 'guest', now) end
    end
    local function ready()
        h:tick(0); g:tick(0); drain(0)
        assert(not h.ready and not g.ready)
        h:tick(0.5); g:tick(0.5); drain(0.5)
        assert(h.ready and g.ready)
    end
    return h, g, hq, gq, actions, cleared, drain, ready
end
check('mutual ack and different Boss classes', function()
    local h,g,_,_,_,_,_,ready=pair(); ready()
    assert(h:remote_class()==bosses.youlong.class_path and g:remote_class()==bosses.ahua.class_path)
end)
check('one-way packets cannot unlock assembly', function()
    local h,g,hq=pair(); h:tick(0); assert(g:receive(hq[1],'host',0)); g:tick(0.5)
    assert(not h.ready and not g.ready)
end)
check('remote actions resolved only from pinned local catalog', function()
    local h,g,hq,_,actions,_,_,ready=pair(); ready()
    assert(h:action('cut')); assert(g:receive(hq[1],'host',0.6)); assert(#actions==1)
    assert(actions[1][1]=='ahua' and actions[1][3]==bosses.ahua.actions.cut)
    assert(not h:action('/Injected/Ability'))
end)
check('duplicate and late action have one visual effect', function()
    local h,g,hq,_,actions,_,_,ready=pair(); ready(); h:action('cut')
    local line=hq[1]; assert(g:receive(line,'host',0.6)); assert(not g:receive(line,'host',0.7))
    assert(#actions==1)
end)
check('boss change revokes readiness and needs new acknowledgement', function()
    local h,g,_,_,_,_,drain,ready=pair(); ready()
    h:select('youlong',0.6); assert(not h.ready and not h:action('dodge'))
    h:tick(0.6); drain(0.6); assert(not g.ready)
    g:tick(1); drain(1); assert(h.ready)
    h:tick(1.1); drain(1.1); assert(g.ready and g:remote_class()==bosses.youlong.class_path)
end)
check('retired world messages remain rejected after clear', function()
    local h,g,hq,_,_,cleared,drain,ready=pair(); ready(); h:action('cut'); local old=table.remove(hq,1)
    h:world_changed(0.6); h:tick(0.6); drain(0.6)
    assert(not g:receive(old,'host',0.7) and #cleared>0 and not g.ready)
end)
check('timeout revokes authority and heartbeat rate stays bounded', function()
    local h,g,hq,_,_,_,_,ready=pair(); ready(); local before=#hq
    for i=1,299 do h:tick(0.5+i*0.001) end
    assert(#hq==before); h:tick(3.5); assert(not h.ready and not h:remote_class())
    assert(not h:action('cut') and g.ready)
end)
check('reconnect requires fresh ack and old ack cannot unlock', function()
    local h,g,hq,gq,_,_,_,ready=pair(); ready(); g:tick(1); local old=gq[#gq]
    h:set_link(false,1); h:set_link(true,1.1); assert(not h.ready)
    assert(h:receive(old,'guest',1.1)); assert(not h.ready)
end)
check('sender role cannot be forged in payload', function()
    local h,g,hq=pair(); h:tick(0)
    assert(not g:receive(hq[1],'guest',0)); assert(not h:receive(hq[1],'guest',0))
end)
check('incompatible build, catalog and research sessions rejected', function()
    for _,replacement in ipairs({{'research_1','another_run'},{SHA,string.rep('c',64)},{BUILD,string.rep('d',64)}}) do
        local h,g,hq=pair(); h:tick(0)
        assert(not g:receive((hq[1]:gsub(replacement[1],replacement[2])),'host',0)); assert(not g.ready)
    end
end)
check('malformed, oversized, unknown and nonfinite packets refused', function()
    local h,g,hq=pair(); h:tick(0); local good=hq[1]
    local bad={'',good..' extra',good..'\n',string.rep('x',851),good:gsub('ahua','invented'),
        good:gsub('^1 H research_1 %d+','1 H research_1 1e999'),
        good:gsub('^1 H','9 H'),good:gsub(' 0 %-$',' 999 -'),good:gsub(' %-$',' forged')}
    for _,line in ipairs(bad) do assert(not g:receive(line,'host',0)) end
end)
check('unknown and pre-handshake actions cannot advance sequence watermark', function()
    local h,g,hq=pair(); h:tick(0); local hello=hq[1]
    local forged=hello:gsub('^1 H','1 A'):gsub(' %-$',' cut')
    assert(not g:receive(forged,'host',0)); assert(g:receive(hello,'host',0))
end)
check('identity cannot change under same generation', function()
    local h,g,hq,_,_,_,_,ready=pair(); ready(); h:tick(1)
    assert(not g:receive((hq[1]:gsub('ahua','youlong')),'host',1)); assert(g.ready)
end)
check('closed bridge never sends or accepts again', function()
    local h,g,hq,_,_,_,_,ready=pair(); ready(); h:action('cut'); h:close(); g:close()
    assert(not g:receive(hq[1],'host',1) and not h:action('cut') and not h.ready)
end)
check('delayed action cannot revive expired readiness before next tick', function()
    local h,g,hq,_,actions,_,_,ready=pair();ready();h:action('cut')
    assert(not g:receive(hq[1],'host',4));assert(not g.ready and #actions==0)
end)
check('catalog is copied and cannot be expanded after construction', function()
    local h=pair(); bosses.ahua.actions.injected='/Injected'
    assert(not h:action('injected')); bosses.ahua.actions.injected=nil
end)
print('PASS '..checks..' protocol groups; simulation only, no game or relay execution')
