local root=assert(arg[1]);local Native=dofile(root..'/tools/phantom_boss_workbench_native.lua')
local checks=0;local function check(name,fn)fn();checks=checks+1;print('PASS '..name)end
local PATH='/UltraVolumetrics/UltraVolumetrics/Core/PaintMode/Blueprint/W_PaintSize.W_PaintSize_C'
local function fixture()
    local s={objects={},next=1,imports=0,creates=0,brushes=0,positions=0,scales=0,world='W',removes=0}
    local function object(name)
        s.next=s.next+1;local o={address=s.next,name=name,valid=true,world=s.world}
        function o:IsValid()return self.valid end
        s.objects[name]=o;return o
    end
    s.pc=object('pc');s.class=object('class')
    local calls={reference=function(_,o)return {name=o.name,address=o.address}end,
        same=function(_,a,b)return a.address==b.address end}
    function calls:optional(r)
        local o=s.objects[r.name];if not o or not o.valid then return nil end
        assert(o.address==r.address,'identity replaced');return o
    end
    function calls:resolve(r)return assert(self:optional(r))end
    local deps={require=function(name)
        if name=='object_lifecycle'then return {new=function()return {usable=function(_,o)return o and o:IsValid()end}end}end
        assert(name=='ue_calls');return {new=function()return calls end}
    end}
    local render=object('/Script/Engine.Default__KismetRenderingLibrary')
    function render:ImportFileAsTexture2D(pc,path)
        assert(pc==s.pc and path:match('^E:/mod/art/bwb_workbench/menu%-[1-4]%-[0-4]%.png$'))
        s.imports=s.imports+1;if s.reject_import then return nil end
        return object('texture '..path)
    end
    local widgetlib=object('/Script/UMG.Default__WidgetBlueprintLibrary')
    function widgetlib:Create(pc,class,owner)
        assert(pc==s.pc and class==s.class and owner==pc);s.creates=s.creates+1
        local o=object('menu '..s.creates);s.widget=o
        o.Circle=object('image '..s.creates)
        function o.Circle:SetBrushFromTexture(_,resize)assert(not resize);s.brushes=s.brushes+1 end
        function o:AddToViewport(z)assert(z==990);self.screen=true;if s.fail_add then error('partial AddToViewport')end end
        function o:IsInViewport()return self.screen==true end
        function o:SetVisibility(v)self.visibility=v end
        function o:GetVisibility()return self.visibility end
        function o:SetAlignmentInViewport(p)assert(p.X==.5 and p.Y==.5)end
        function o:SetDesiredSizeInViewport(p)assert(p.X==1000 and p.Y==620)end
        function o:GetDesiredSize()return s.desired or {X=400,Y=400}end
        function o:SetPositionInViewport(p,dpi)assert(not dpi);s.position=p;s.positions=s.positions+1 end
        function o:SetRenderScale(p)s.scale=p;s.scales=s.scales+1 end
        function o:RemoveFromParent()s.removes=s.removes+1;if not s.reject_remove then self.screen=false end end
        return o
    end
    local layout=object('/Script/UMG.Default__WidgetLayoutLibrary')
    function layout:GetViewportSize()return s.viewport or {X=1920,Y=1080}end
    function layout:GetViewportScale()return s.dpi or 1 end
    local scope={attest=function(_,restore)assert(restore or not s.expired)end}
    local observer={identify=function(o,world)
        assert(o and o.valid and (not world or o.world==world),'World changed')
        return {world=o.world}
    end}
    local g={StaticFindObject=function(path)return s.objects[path]end,
        LoadAsset=function(path)assert(path==PATH);return s.class end}
    s.binding={binding_verified=true,widget_class=PATH,hit_test_invisible=3}
    function s:new()return Native.new({modRoot=function()return 'E:/mod/'end},scope,observer,deps,self.binding,g)end
    s.native=s:new();s.object=object;return s
end
check('closed workbench performs no object lookup import or widget creation',function()
    local s=fixture();for _=1,100 do assert(s.native:render(s.pc,false,1,1))end
    assert(s.imports==0 and s.creates==0 and s.brushes==0)
end)
check('first open creates a native mouse-transparent centered widget',function()
    local s=fixture();assert(s.native:render(s.pc,true,2,1))
    assert(s.imports==1 and s.creates==1 and s.widget.screen and s.widget.visibility==3)
    assert(s.position.X==960 and s.position.Y==540 and s.scale.X==2.5 and s.scale.Y==1.55)
end)
check('unchanged frames reuse texture brush and geometry',function()
    local s=fixture();s.native:render(s.pc,true,1,1)
    for _=1,100 do s.native:render(s.pc,true,1,1)end
    assert(s.imports==1 and s.creates==1 and s.brushes==1 and s.positions==1 and s.scales==1)
end)
check('cursor changes import bounded art and reuse previous cached textures',function()
    local s=fixture();s.native:render(s.pc,true,1,1);s.native:render(s.pc,true,4,1);s.native:render(s.pc,true,1,1)
    assert(s.imports==2 and s.creates==1 and s.brushes==3)
end)
check('small viewport and DPI keep the full panel inside margins',function()
    local s=fixture();s.viewport={X=1280,Y=720};s.dpi=1.25;s.native:render(s.pc,true,1,1)
    assert(s.position.X==512 and s.position.Y==288)
    assert(400*s.scale.X<=984 and 400*s.scale.Y<=536.00001)
end)
check('closing removes viewport widget and reopening creates a new owner',function()
    local s=fixture();s.native:render(s.pc,true,1,1);assert(s.native:render(s.pc,false,1,1))
    assert(not s.widget.screen and s.removes==1);s.native:render(s.pc,true,1,1)
    assert(s.creates==2 and s.native:close()and s.native:close()and s.removes==2)
end)
check('partial construction failure keeps its recovery reference',function()
    local s=fixture();s.fail_add=true;assert(not pcall(s.native.render,s.native,s.pc,true,1,1))
    assert(s.widget.screen and s.native:close()and not s.widget.screen and s.removes==1)
end)
check('unacknowledged removal retains ownership for a later recovery retry',function()
    local s=fixture();s.native:render(s.pc,true,1,1);s.reject_remove=true
    assert(not pcall(s.native.close,s.native)and s.widget.screen)
    s.reject_remove=false;assert(s.native:close()and not s.widget.screen)
end)
check('changed World and substituted identity refuse stale widget mutation',function()
    local s=fixture();s.native:render(s.pc,true,1,1);s.pc.world='other'
    assert(not pcall(s.native.render,s.native,s.pc,true,2,1)and s.imports==1 and s.brushes==1)
    s.pc.world='W';s.widget.address=999
    assert(not pcall(s.native.close,s.native)and s.removes==0)
end)
check('lease expiry forbids new UI but permits captured widget recovery',function()
    local s=fixture();s.native:render(s.pc,true,1,1);s.expired=true
    assert(not pcall(s.native.render,s.native,s.pc,true,2,1)and s.native:close())
end)
check('invalid bounds imports and declarations are rejected',function()
    local s=fixture();assert(not pcall(s.native.render,s.native,s.pc,true,5,1)and s.imports==0)
    s.reject_import=true;assert(not pcall(s.native.render,s.native,s.pc,true,1,1)and s.creates==0)
    s.binding.binding_verified=false;assert(not pcall(s.new,s))
end)
check('stale viewport cannot be reused and invalid geometry is not applied',function()
    local s=fixture();s.native:render(s.pc,true,1,1);s.widget.screen=false
    assert(not pcall(s.native.render,s.native,s.pc,true,1,1)and s.creates==1)
    s=fixture();s.viewport={X=0/0,Y=720}
    assert(not pcall(s.native.render,s.native,s.pc,true,1,1)and s.positions==0)
    assert(s.native:close())
end)
check('recovery art has no equipped Boss and cannot accept an out-of-range selection',function()
    local s=fixture();assert(s.native:render(s.pc,true,3,0)and s.imports==1)
    assert(s.objects['texture E:/mod/art/bwb_workbench/menu-3-0.png'])
    assert(not pcall(s.native.render,s.native,s.pc,true,3,-1))
end)
print('PASS '..checks..' workbench native groups; fake UMG objects, no engine or game launched')
