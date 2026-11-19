-- Development-only native cue adapter. Never creates a particle or changes a tag/faction.
local Bridge={};Bridge.__index=Bridge
local CLASS='/PBZCombatAsset/Prototypes/Actions/GAAction_WeaponParticle_BlueRedEye.GAAction_WeaponParticle_BlueRedEye_C'
Bridge.class_path=CLASS
local function same(a,b)
    return a and b and a.name==b.name and a.address==b.address and a.class==b.class
end
local function valid(object)return object and object:IsValid()==true end
function Bridge.new(control,g,contract,input_allowed,on_failure)
    assert(contract and contract.developer_only==true and contract.declaration_verified==true
        and contract.script_gate_verified==true and contract.avatar_binding_verified==true
        and contract.class_path==CLASS and contract.blueprint_post_hook_verified==true,
        'reviewed native cue declarations, script gate and Blueprint post hook required')
    assert(type(g.RegisterHook)=='function'and type(g.UnregisterHook)=='function'
        and type(input_allowed)=='function'and type(on_failure)=='function','cue host incomplete')
    local self=setmetatable({control=control,g=g,hooks={},enabled=false,failed=false,
        input_allowed=input_allowed,on_failure=on_failure},Bridge)
    local calls=control.calls
    local function exact(action)
        return valid(action)and action:GetClass():GetFullName()=='BlueprintGeneratedClass '..CLASS
            and not action:GetFullName():find('Default__',1,true)
    end
    local function eligible(action,owner)
        if not exact(action)or control.active_receipt~=owner then return false end
        control:check(owner)
        if not same(calls:world(action),owner.world)then return false end
        local avatar=action:GetAvatarActor()
        return valid(avatar)and calls:same(avatar,calls:resolve(owner.boss))==true
    end
    self.cues=require('boss_native_cues').new({
        owner=function(action)
            local r=control.active_receipt
            if not self.enabled or self.failed or not r or not r.input_enabled
                or self.input_allowed()~=true then return nil end
            if not eligible(action,r)or control:verify_control(r)~=true then return nil end
            return r
        end,
        eligible=eligible,
        reference=function(action)return calls:reference(action)end,
        resolve=function(ref)return calls:optional(ref)end,
        count=function(action)
            assert(exact(action),'exact native cue action required')
            local total=0
            for _,field in ipairs({'Cascade Comps','Niagara Comps'})do
                local array=action[field];local n=array:GetArrayNum()
                assert(math.type(n)=='integer'and n>=0 and n<=64,'bounded native cue array required')
                for i=1,n do
                    assert(i<=array:GetArrayNum(),'native cue array changed during read')
                    if valid(array[i])then total=total+1 end
                end
            end
            return total
        end,
        spawn=function(action,owner)
            assert(self.enabled and not self.failed and self.input_allowed()==true
                and owner.input_enabled and eligible(action,owner),'native cue spawn owner changed')
            -- Spaces are the exact reflected Blueprint function name, not a fabricated API.
            action['Spawn Particles'](action,calls:resolve(owner.boss));return true
        end,
        finish=function(action)action['End Particles'](action);return true end,
    })
    return self
end
function Bridge:dispatch(method,context)
    if not self.enabled then return end
    local ok,why=pcall(function()
        local action=context:get()
        if method=='on_begin'and self.failed then return end
        self.cues[method](self.cues,action)
    end)
    if not ok and not self.failed then
        self.failed=true -- Stop further spawns; native end/cleanup still owns outstanding actions.
        self.on_failure('native cue '..method,tostring(why))
    end
end
function Bridge:install()
    assert(not self.enabled and #self.hooks==0,'cue hooks already installed or cleanup pending')
    self.enabled=true
    local ok,why=pcall(function()
        for _,row in ipairs({{'Received_ActionBegin','on_begin'},{'Received_ActionEnd','on_end'}})do
            local path=CLASS..':'..row[1];local method=row[2]
            -- UE4SS registers the FIRST callback as the script-function POST hook.
            -- The optional third callback applies to native functions only.
            local pre,post=self.g.RegisterHook(path,function(context)self:dispatch(method,context)end)
            self.hooks[#self.hooks+1]={path=path,pre=pre,post=post}
            assert(math.type(pre)=='integer'and pre==post,'expected Blueprint script post hook ids')
        end
    end)
    if not ok then
        self.enabled=false
        local clean,errors=self:close()
        error(tostring(why)..(clean and''or' | cleanup: '..table.concat(errors,'; ')))
    end
    return true
end
function Bridge:cleanup()return self.cues:cleanup()end
function Bridge:close()
    self.enabled=false
    local clean,errors=self:cleanup()
    for i=#self.hooks,1,-1 do
        local row=self.hooks[i]
        local ok,why=pcall(self.g.UnregisterHook,row.path,row.pre,row.post)
        if ok then table.remove(self.hooks,i)else clean=false;errors[#errors+1]=tostring(why)end
    end
    return clean,errors
end
function Bridge:retire()
    self.enabled=false
    local calls=self.control.calls
    -- A class/name reused in the new World must not be touched. The bounded
    -- base retirement resolver can establish that the old action was destroyed.
    assert(type(calls.retirement_optional)=='function','retirement resolver required')
    for _,item in pairs(self.cues.pending)do
        assert(calls:retirement_optional(item.reference)==nil,'old native cue action still registered')
    end
    self.cues.pending={};self.cues.size=0
    return self:close()
end
return Bridge
