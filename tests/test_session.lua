-- 这些测试只验证独立控制会话逻辑，不代表PBZ实机接管或技能已经成功。
local project = assert(arg[1], "project directory required")
package.path = project .. "/mod/PBZBossControl/Scripts/?.lua;" .. package.path
local Session = require("session")
local count = 0

local function fixture() -- 用途：用明确的模拟对象测试错误恢复，不在真实游戏里试错。
    local b = { c = { isolated = true, offline = true, exe_sha256 = "test-build", world_id = "world-1", boss_available = true },
        captures = 0, mutations = 0, restored = 0, starts = 0, allowed = true, finished = false }
    function b:context() return self.c end
    function b:capture() self.captures = self.captures + 1; return { player_id = "player-1", boss_id = "boss-1" } end
    function b:take_control(_) self.mutations = self.mutations + 1; return true end
    function b:verify_control(_) return true end
    function b:can_start_skill(_, _) return self.allowed end
    function b:start_skill(_, _) self.starts = self.starts + 1; return "token-1" end
    function b:is_skill_finished(_, _) return self.finished end
    function b:cancel_skills(_) return true end
    function b:restore(_) self.restored = self.restored + 1; return true end
    function b:verify_restored(_) return true end
    local config = { expected_exe_sha256 = "test-build", skills = { slot1 = { id = "mock-skill", verified = true } } }
    return Session.new(b, config), b, config
end

local function test(name, callback)
    local ok, why = pcall(callback)
    if not ok then error(name .. ": " .. tostring(why)) end
    count = count + 1; print("PASS " .. name)
end

test("missing isolation performs no mutation", function()
    local s,b=fixture(); b.c.isolated=false; assert(not s:enter()); assert(b.captures==0 and b.mutations==0)
end)
test("online context performs no mutation", function()
    local s,b=fixture(); b.c.offline=false; assert(not s:enter()); assert(b.mutations==0)
end)
test("wrong build rejected", function()
    local s,b=fixture(); b.c.exe_sha256="different"; assert(not s:enter()); assert(b.captures==0)
end)
test("unknown boss rejected", function()
    local s,b=fixture(); b.c.boss_available=false; assert(not s:enter()); assert(b.captures==0)
end)
test("capture failure cannot mutate", function()
    local s,b=fixture(); function b:capture() error("read failure") end; assert(not s:enter()); assert(b.mutations==0 and s.state=="OFF")
end)
test("partial takeover failure restores", function()
    local s,b=fixture(); function b:take_control() self.mutations=self.mutations+1;error("partial failure") end
    assert(not s:enter());assert(b.restored==1 and s.state=="OFF")
end)
test("takeover verification failure restores", function()
    local s,b=fixture(); function b:verify_control() return false end
    assert(not s:enter());assert(b.restored==1 and s.state=="OFF")
end)
test("enter and repeated enter are deterministic", function()
    local s,b=fixture();assert(s:enter());assert(s.state=="ACTIVE");assert(not s:enter());assert(b.captures==1)
end)
test("unverified skill blocked", function()
    local s,b,c=fixture();c.skills.slot1.verified=false;assert(s:enter());assert(not s:skill("slot1"));assert(b.starts==0)
end)
test("game cooldown rules respected", function()
    local s,b=fixture();assert(s:enter());b.allowed=false;assert(not s:skill("slot1"));assert(b.starts==0)
end)

test("native activation rejection does not discard possession", function()
    local s,b=fixture();assert(s:enter());function b:start_skill() return false end
    assert(not s:skill("slot1"));assert(s.state=="ACTIVE" and b.restored==0 and not s.current_skill)
end)
test("skill reentry blocked until actual finish", function()
    local s,b=fixture();assert(s:enter());assert(s:skill("slot1"));assert(not s:skill("slot1"));assert(s:poll());assert(s.current_skill)
    b.finished=true;assert(s:poll());assert(s.current_skill==nil);assert(s:skill("slot1"));assert(b.starts==2)
end)
test("world change rejects stale restoration", function()
    local s,b=fixture();assert(s:enter());b.c.world_id="world-2";assert(not s:restore("exit"));assert(s.state=="FAULTED" and b.restored==0)
end)
test("skill start error triggers restoration", function()
    local s,b=fixture();assert(s:enter());function b:start_skill() error("start failed") end
    assert(not s:skill("slot1"));assert(s.state=="OFF" and b.restored==1)
end)
test("failed restoration remains faulted", function()
    local s,b=fixture();assert(s:enter());function b:verify_restored() return false end
    assert(not s:restore("exit"));assert(s.state=="FAULTED" and s.receipt~=nil)
end)
test("exit clears skill and restores once", function()
    local s,b=fixture();assert(s:enter());assert(s:skill("slot1"));assert(s:restore("exit"));assert(s.state=="OFF" and not s.receipt and not s.current_skill)
    assert(s:restore("exit again"));assert(b.restored==1)
end)
test("missing bridge refused", function()
    assert(not pcall(Session.new,{},{}))
end)
test('depleted boss restores even with no current skill',function()
    local s,b=fixture();function b:control_health()return false,'boss health depleted'end
    assert(s:enter());assert(not s:poll());assert(s.state=='OFF'and b.restored==1 and b.starts==0)
end)
test('health query failure blocks new skill and attempts restoration',function()
    local s,b=fixture();assert(s:enter());function b:control_health()error('attribute destroyed')end
    assert(not s:skill('slot1'));assert(s.state=='OFF'and b.restored==1 and b.starts==0)
end)
test('health-triggered restoration failure keeps the receipt faulted',function()
    local s,b=fixture();assert(s:enter());function b:control_health()return false end
    function b:verify_restored()return false end
    assert(not s:poll());assert(s.state=='FAULTED'and s.receipt)
end)
test("real entry is disabled and registers no keys", function()
    local n=0;RegisterKeyBind=function()n=n+1 end;ExecuteInGameThread=function()error("must not run")end
    dofile(project .. "/mod/PBZBossControl/Scripts/main.lua");assert(n==0)
end)
print("PBZ control-core mock tests: " .. count .. " passed; PBZ runtime integration is NOT verified")
