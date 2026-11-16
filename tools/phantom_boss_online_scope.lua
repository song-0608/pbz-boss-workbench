-- Explicit online research lease. Cleanup has a separate, bounded purpose;
-- expiry is never extended and no offline=true attestation is manufactured.
local M={}
local keys={'mode','isolated','issued_at','expires_at','session_id','role',
    'exe_sha256','catalog_sha256','upstream_commit'}
local function finite(n) return type(n)=='number' and n==n and n>=0 and n<math.huge end
local function digest(s) return type(s)=='string' and #s==64 and s:match('^[0-9a-f]+$') end
function M.new(provider,expected,clock)
    assert(type(provider)=='function' and type(clock)=='function')
    assert(expected.role=='host' or expected.role=='guest','explicit online role required')
    assert(type(expected.session_id)=='string' and #expected.session_id<=48
        and expected.session_id:match('^[%w_%-]+$'),'online session ID required')
    assert(digest(expected.exe_sha256) and digest(expected.catalog_sha256))
    assert(type(expected.upstream_commit)=='string' and #expected.upstream_commit==40
        and expected.upstream_commit:match('^[0-9a-f]+$'))
    local now=clock();assert(finite(now),'invalid lease clock')
    local initial=provider();assert(type(initial)=='table')
    assert(initial.mode=='two-player-online-research' and initial.isolated==true and initial.offline~=true,
        'explicit isolated online lease required')
    assert(finite(initial.issued_at) and finite(initial.expires_at)
        and initial.issued_at<=now and initial.expires_at>now
        and initial.expires_at>initial.issued_at and initial.expires_at-initial.issued_at<=1200,
        'bounded current online lease required')
    for _,key in ipairs({'session_id','role','exe_sha256','catalog_sha256','upstream_commit'}) do
        assert(initial[key]==expected[key],'online lease identity mismatch: '..key)
    end
    local captured={};for _,key in ipairs(keys) do captured[key]=initial[key] end
    local self={revoked=false,closed=false,reason=nil}
    local previous=now
    function self:attest(restoration)
        assert(restoration==nil or type(restoration)=='boolean','explicit restoration purpose required')
        assert(not self.closed,'online scope closed')
        local current=clock();assert(finite(current) and current>=previous,'lease clock moved backwards')
        previous=current
        local grant=provider();assert(type(grant)=='table' and grant.offline~=true,'online lease unreadable')
        for _,key in ipairs(keys) do assert(grant[key]==captured[key],'online lease changed: '..key) end
        if restoration==true then
            assert(current<captured.expires_at+15,'online restoration deadline elapsed')
        else
            assert(not self.revoked and current<captured.expires_at,'online control lease revoked or expired')
        end
        local copy={};for key,value in pairs(captured) do copy[key]=value end
        copy.restore_only=self.revoked or current>=captured.expires_at
        return copy
    end
    function self:revoke(reason)
        self.revoked=true;self.reason=tostring(reason)
    end
    function self:close() self.revoked,self.closed=true,true end
    return self
end
return M
