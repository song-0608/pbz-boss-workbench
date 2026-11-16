local root=assert(arg[1]);local Native=dofile(root..'/tools/phantom_boss_visual_native.lua')
local asset='/PBZCombatAsset/ActorData/Mobs/Test/Walk.Walk'
local montage_path='/PBZCombatAsset/ActorData/Mobs/Test/Montage.Montage'
local checks=0;local function check(name,fn)fn();checks=checks+1;print('PASS '..name)end
local function fixture()
    local s={objects={},next=10,now=0,world='W',registered={},finds=0}
    local function object(name)
        s.next=s.next+1
        local o={address=s.next,name=name,valid=true,tick=true,collision=true}
        function o:IsValid()return self.valid end
        function o:GetAddress()return self.address end
        function o:GetFullName()return self.name end
        function o:GetClass()return self.class end
        function o:GetOwner()return self.owner end
        function o:GetAttachParent()return self.parent end
        function o:SetActorEnableCollision(v)self.collision=v end
        function o:GetActorEnableCollision()return self.collision end
        function o:SetActorTickEnabled(v)self.tick=v end
        function o:IsActorTickEnabled()return self.tick end
        function o:SetActorHiddenInGame(v)self.hidden=v end
        function o:SetComponentTickEnabled(v)self.tick=v end
        function o:IsComponentTickEnabled()return self.tick end
        function o:SetCollisionEnabled(v)self.collision=v end
        function o:GetCollisionEnabled()return self.collision end
        function o:SetGenerateOverlapEvents(v)self.overlap=v end
        function o:GetGenerateOverlapEvents()return self.overlap end
        function o:SetSkeletalMesh(v)self.mesh=v end
        function o:SetAnimationMode(v)self.mode=v end
        function o:GetAnimationMode()return self.mode end
        function o:SetPlaying(v)assert(v==false,'automatic playback forbidden');self.playing=v end
        function o:IsPlaying()return self.playing end
        function o:SetMaterial(i,m)self.materials=self.materials or {};self.materials[i]=m end
        function o:SetAnimation(v)self.animation=v end
        function o:SetPosition(time,notifies)assert(notifies==false,'notifies forbidden');self.position=time;s.poses=(s.poses or 0)+1 end
        function o:K2_SetActorLocationAndRotation(position,rotation,sweep)assert(sweep==false);self.position3=position;self.rotation=rotation end
        function o:K2_DestroyActor()self.valid=false;s.destroyed=(s.destroyed or 0)+1 end
        function o:IsActorBeingDestroyed()return not self.valid end
        function o:PlayAnimation()error('automatic playback forbidden')end
        function o:Montage_Play()error('montage notifies forbidden')end
        function o:TryActivateAbilityByClass()error('ability execution forbidden')end
        s.objects[name:match('^[^ ]+ (.+)$') or name]=o
        return o
    end
    local actor_class=object('Class /Script/Engine.Actor')
    local scene_class=object('Class /Script/Engine.SceneComponent')
    local mesh_class=object('Class /Script/Engine.SkeletalMeshComponent')
    local sequence_class=object('Class /Script/Engine.AnimSequence')
    local skeleton=object('Skeleton /Test/Skeleton')
    local mesh_asset=object('SkeletalMesh /Test/Mesh');mesh_asset.Skeleton=skeleton
    local material=object('Material /Test/Material')
    local sequence=object('AnimSequence '..asset);sequence.Skeleton=skeleton
    function sequence:IsA(cls)return cls==sequence_class end
    function sequence:GetPlayLength()return 2 end
    local source=object('SkeletalMeshComponent /Test/Default.Mesh')
    function source:GetSkeletalMeshAsset()return mesh_asset end
    function source:GetNumMaterials()return 1 end
    function source:GetMaterial(i)assert(i==0);return material end
    function source:GetRelativeTransform()return {relative=true}end
    local boss_class=object('Class /Test/Boss_C')
    function boss_class:GetCDO()return {Mesh=source}end
    local statics=object('GameplayStatics /Script/Engine.Default__GameplayStatics')
    local maths=object('KismetMathLibrary /Script/Engine.Default__KismetMathLibrary')
    function maths:MakeTransform(a,b,c)return {Translation=a,Rotation=b,Scale=c}end
    function statics:BeginDeferredActorSpawnFromClass(pc,cls)
        assert(cls==actor_class,'Boss blueprint must not be a visual body')
        local actor=object('Actor /Transient/Visual'..s.next);actor.class=actor_class
        function actor:AddComponentByClass(kind,manual,transform,deferred)
            assert(manual==false and deferred==false)
            local comp=object('Component /Transient/Component'..s.next);comp.owner=self
            if kind==scene_class then assert(not self.RootComponent);self.RootComponent=comp
            else assert(kind==mesh_class);comp.parent=self.RootComponent;s.mesh=comp end
            return comp
        end
        s.actor=actor;return actor
    end
    function statics:FinishSpawningActor(actor)
        assert(s.remembered==actor.address,'ownership must precede construction')
        if s.finish_error then error('construction failed')end
        return actor
    end
    local pc=object('Controller /Transient/PC')
    local body=object('Boss /Transient/Boss');body.class=boss_class
    function body:K2_GetActorLocation()return {X=10,Y=20,Z=30}end
    function body:K2_GetActorRotation()return {Yaw=90}end
    local montage=object('AnimMontage '..montage_path)
    local anim=object('AnimInstance /Transient/Anim')
    function anim:GetCurrentActiveMontage()return montage end
    function anim:Montage_GetPosition()return s.montage_position or .5 end
    body.Mesh={GetAnimInstance=function()return anim end}
    local calls={reference=function(_,o)return {name=o.name,address=o.address}end,
        resolve=function(_,row)local o=s.objects[row.name:match('^[^ ]+ (.+)$')];assert(o and o.valid and o.address==row.address);return o end,
        optional=function(_,row)local o=s.objects[row.name:match('^[^ ]+ (.+)$')];if not o or not o.valid then return nil end;assert(o.address==row.address);return o end,
        same=function(_,a,b)return a==b end}
    local deps={require=function(name)
        if name=='ue_calls' then return {new=function()return calls end}end
        assert(name=='object_lifecycle');return {new=function()return {usable=function(_,o)return o and o.valid or false end}end}
    end}
    local binding={binding_verified=true,single_node_mode=1,no_collision=0,manual_pose_no_notifies=true,
        animations={ahua={[asset]=2}},sampling={ahua={[montage_path]={{path=asset,at=0,start=.1,finish=1.6,rate=2,loops=1}}}}}
    local g={StaticFindObject=function(path)s.finds=s.finds+1;return s.objects[path]end,
        LoadAsset=function(path)if path=='/Test/Boss_C' then return boss_class end;assert(path==asset);return sequence end}
    local observer={snapshot=function()return {world=s.world}end,now=function()return s.now end,
        identify=function(o,expected)assert(not expected or expected==s.world);return {world=s.world,class=o==body and '/Test/Boss_C' or '/Script/Engine.Actor'}end}
    local scope={attest=function(_,restore)if s.expired and not restore then error('expired')end end}
    local peer={register=function(_,row,kind)assert(kind=='remote_ghost');s.registered[#s.registered+1]=row end,
        network_body=function()return body end}
    local api={getPlayer1=function()return pc end,coop={net={localMap=7}}}
    function s:create()return Native.new(api,scope,peer,observer,deps,binding,{bosses={ahua={class_path='/Test/Boss_C'}}},g)end
    function s:mount(n)
        return n.mount('ahua',s.world,function(row)s.remembered=row.actor.address;s.record=row end)
    end
    s.binding,s.sequence,s.asset,s.body= binding,sequence,mesh_asset,body
    return s
end
check('visual is a plain actor with inert components and no collision or automatic animation',function()
    local s=fixture();local n=s:create();local row=s:mount(n)
    assert(row==s.record and #s.registered==1 and s.actor.hidden and not s.actor.tick
        and not s.actor.collision and not s.mesh.tick and not s.mesh.overlap and s.mesh.collision==0 and not s.mesh.playing)
end)
check('pose update sets explicit time with notifies disabled and no ability execution',function()
    local s=fixture();local n=s:create();local row=s:mount(n)
    assert(n.update(row,{boss='ahua',animation=asset,time=.5,x=1,y=2,z=3,yaw=4},'W'))
    assert(s.poses==1 and s.mesh.position==.5 and not s.actor.hidden and s.actor.position3.X==1)
    assert(n.destroy(row) and s.destroyed==1)
end)
check('changed collision or enabled animation tick rejects an existing visual body',function()
    local s=fixture();local n=s:create();local row=s:mount(n);s.mesh.tick=true
    assert(not pcall(n.update,row,{boss='ahua',animation=asset,time=.5,x=1,y=2,z=3,yaw=4},'W'))
end)
check('partial native construction remains owned for destruction',function()
    local s=fixture();local n=s:create();s.finish_error=true
    assert(not pcall(s.mount,s,n) and s.record and n.destroy(s.record) and s.destroyed==1)
end)
check('absent binding rejects spawning and mismatched streamed sequence rejects posing',function()
    local s=fixture();s.binding.manual_pose_no_notifies=false;assert(not pcall(s.create,s))
    s=fixture();s.sequence.Skeleton={GetFullName=function()return 'Wrong skeleton'end}
    local n=s:create();local row=s:mount(n)
    assert(not pcall(n.update,row,{boss='ahua',animation=asset,time=.5,x=1,y=2,z=3,yaw=4},'W'))
    s=fixture();s.sequence.GetPlayLength=function()return 3 end;n=s:create()
    row=s:mount(n);assert(not pcall(n.update,row,{boss='ahua',animation=asset,time=.5,x=1,y=2,z=3,yaw=4},'W'))
end)
check('bounded captured montage sampling calculates sequence time without network asset paths',function()
    local s=fixture();local n=s:create();local f=n.sample('ahua')
    assert(f.animation==asset and math.abs(f.time-1.1)<.000001 and f.world=='W' and f.map==7)
    s.montage_position=10;f=n.sample('ahua');assert(f.animation=='-' and f.time==0)
end)
check('malformed sampling declarations reject instead of dividing or loading during frames',function()
    local s=fixture();s.binding.sampling.ahua[montage_path][1].rate=0
    assert(not pcall(s.create,s))
end)
check('expiry blocks new poses but retains the ability to clean owned actors',function()
    local s=fixture();local n=s:create();local row=s:mount(n);s.expired=true
    assert(not pcall(n.sample,'ahua'));assert(n.destroy(row))
end)
print('PASS '..checks..' visual native groups; fake engine contracts only, no game started')
