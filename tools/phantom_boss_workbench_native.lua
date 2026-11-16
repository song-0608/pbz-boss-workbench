-- Native UMG presentation using the pinned upstream W_PaintSize image widget.
-- No HUD hook, per-frame object scan, external window, mouse capture or texture
-- import on a combat frame. A current-process UI declaration is mandatory.
local M={}
local PATH='/UltraVolumetrics/UltraVolumetrics/Core/PaintMode/Blueprint/W_PaintSize.W_PaintSize_C'
local function finite(n)return type(n)=='number'and n==n and n>0 and n<100000 end
function M.new(api,scope,observer,dependencies,binding,g)
    g=g or _G
    assert(binding and binding.binding_verified==true and binding.widget_class==PATH
        and binding.hit_test_invisible==3,'current UMG workbench declarations required')
    local req=dependencies.require
    local life=req('object_lifecycle').new(g,binding)
    local usable=function(o)return life:usable(o)end
    local calls=req('ue_calls').new({find_exact=g.StaticFindObject,usable=usable})
    local function library(name)
        local o=g.StaticFindObject(name);assert(usable(o),'workbench library missing: '..name);return o
    end
    local self={textures={}}
    local widget_ref,world,owner_ref,last_texture,last_geometry
    local function widget()
        if not widget_ref then return nil end
        local o=calls:optional(widget_ref);assert(o,'owned workbench widget disappeared')
        observer.identify(o,world);return o
    end
    function self:close()
        scope:attest(true)
        local o=widget()
        if o then
            o:RemoveFromParent();assert(o:IsInViewport()==false,'workbench widget removal unverified')
        end
        widget_ref,world,owner_ref,last_texture,last_geometry=nil,nil,nil,nil,nil
        self.textures={};return true
    end
    function self:render(pc,opened,cursor,selected)
        scope:attest(false)
        if not opened then
            if widget_ref then return self:close()end
            return true
        end
        assert(type(cursor)=='number'and cursor==math.floor(cursor)and cursor>=1 and cursor<=4
            and type(selected)=='number'and selected==math.floor(selected)and selected>=1 and selected<=4,
            'bounded workbench art selection required')
        local current=observer.identify(pc)
        if world then
            assert(current.world==world and calls:same(pc,calls:resolve(owner_ref)),
                'workbench World or owning player changed')
        end
        local name='bwb_workbench/menu-'..cursor..'-'..selected..'.png'
        local texture=self.textures[name]
        if not usable(texture)then
            texture=library('/Script/Engine.Default__KismetRenderingLibrary'):ImportFileAsTexture2D(pc,api.modRoot()..'art/'..name)
            assert(usable(texture),'workbench texture import rejected');self.textures[name]=texture
        end
        local o=widget()
        if not o then
            local class=g.LoadAsset(PATH);assert(usable(class),'workbench image class unavailable')
            o=library('/Script/UMG.Default__WidgetBlueprintLibrary'):Create(pc,class,pc)
            assert(usable(o),'workbench widget creation rejected')
            -- Capture before any viewport setup so partial failures retain recovery.
            widget_ref=calls:reference(o);world=current.world;owner_ref=calls:reference(pc)
            observer.identify(o,world)
            o:AddToViewport(990);assert(o:IsInViewport()==true,'workbench not added to viewport')
            o:SetVisibility(3);assert(o:GetVisibility()==3,'workbench must be mouse transparent')
            o:SetAlignmentInViewport({X=.5,Y=.5})
            o:SetDesiredSizeInViewport({X=1000,Y=620})
        else assert(o:IsInViewport()==true,'stale workbench widget is not on screen')end
        if last_texture~=name then
            local image=o.Circle;assert(usable(image),'workbench image component unavailable')
            image:SetBrushFromTexture(texture,false)
            last_texture=name
        end
        local layout=library('/Script/UMG.Default__WidgetLayoutLibrary')
        local size,dpi=layout:GetViewportSize(pc),layout:GetViewportScale(pc)
        assert(size and finite(size.X)and finite(size.Y)and finite(dpi),'invalid workbench viewport')
        local width,height=size.X/dpi,size.Y/dpi
        local scale=math.min(1,(width-40)/1000,(height-40)/620)
        assert(scale>0,'workbench viewport too small')
        local desired=o:GetDesiredSize()
        if desired and finite(desired.X)and finite(desired.Y)then
            local geometry=table.concat({width,height,desired.X,desired.Y,scale},'|')
            if geometry~=last_geometry then
                o:SetPositionInViewport({X=width/2,Y=height/2},false)
                o:SetRenderScale({X=1000*scale/desired.X,Y=620*scale/desired.Y})
                last_geometry=geometry
            end
        end
        return true
    end
    return self
end
return M
