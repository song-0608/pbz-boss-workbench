-- A LoadMap cleanup can retire a runtime before a queued role-change runs.
-- Never let that old request stop or destroy the next World's assembly.
local Reassembly={}
function Reassembly.schedule(api,expected,fn)
    assert(type(api.current)=='function'and type(api.defer)=='function'and type(fn)=='function',
        'reassembly scheduler API required')
    assert(expected and expected.running and api.current()==expected,'current live runtime required')
    return api.defer(250,function()
        if api.current()~=expected or not expected.running then return end
        fn()
    end)
end
return Reassembly
