-- Cosmetic actor only: Engine.Actor + SceneComponent + SkeletalMeshComponent.
-- Never spawn a Boss blueprint here, create an AI, grant/activate an ability,
-- call Montage_Play, or run animation notifies.
local M={}
local function clone(t)if type(t)~='table' then return t end;local n={};for k,v in pairs(t)do n[k]=clone(v)end;return n end
function M.new(api,scope,peer,observer,dependencies,binding,config,g)
    g=g or _G
    assert(binding and binding.binding_verified==true and binding.single_node_mode==1
        and binding.no_collision==0 and binding.manual_pose_no_notifies==true,
        'current native visual declarations and manual-pose contract required')
    assert(type(binding.animations)=='table' and type(binding.sampling)=='table')
    local req=dependencies.require
    local lifecycle=req('object_lifecycle').new(g,binding)
    local usable=function(o)return lifecycle:usable(o)end
    local calls=req('ue_calls').new({find_exact=g.StaticFindObject,usable=usable})
    local statics=g.StaticFindObject('/Script/Engine.Default__GameplayStatics')
    local maths=g.StaticFindObject('/Script/Engine.Default__KismetMathLibrary')
    local actor_class=g.StaticFindObject('/Script/Engine.Actor')
    local scene_class=g.StaticFindObject('/Script/Engine.SceneComponent')
    local mesh_class=g.StaticFindObject('/Script/Engine.SkeletalMeshComponent')
    local sequence_class=g.StaticFindObject('/Script/Engine.AnimSequence')
    for _,o in ipairs({statics,maths,actor_class,scene_class,mesh_class,sequence_class})do assert(usable(o))end
    local animations,sampling=clone(binding.animations),clone(binding.sampling)
    local self={animations=animations}
    local cache={}
    local function segments_valid(id,segments)
        assert(type(segments)=='table' and #segments<=32,'captured montage segment bound')
        for _,s in ipairs(segments)do
            assert(type(s)=='table' and animations[id] and animations[id][s.path]
                and type(s.at)=='number' and s.at==s.at and s.at>=0 and s.at<600
                and type(s.start)=='number' and s.start>=0 and s.start==s.start
                and type(s.finish)=='number' and s.finish>s.start and s.finish<=animations[id][s.path]
                and type(s.rate)=='number' and s.rate==s.rate and math.abs(s.rate)>=.01 and math.abs(s.rate)<=10
                and type(s.loops)=='number' and s.loops==math.floor(s.loops) and s.loops>=1 and s.loops<=100,
                'invalid captured montage segment')
        end
    end
    for id,montages in pairs(sampling)do
        assert(config.bosses[id] and type(montages)=='table')
        for path,segments in pairs(montages)do assert(type(path)=='string' and #path<=256);segments_valid(id,segments)end
    end
    local function assets(id)
        if cache[id] then return cache[id] end
        assert(config.bosses[id],'visual Boss absent from catalog')
        local class=g.LoadAsset(config.bosses[id].class_path);assert(usable(class))
        local source=class:GetCDO().Mesh;assert(usable(source))
        local mesh=source:GetSkeletalMeshAsset();assert(usable(mesh) and usable(mesh.Skeleton))
        local materials={};local count=source:GetNumMaterials()
        assert(type(count)=='number' and count==math.floor(count) and count>=0 and count<=32,'visual material bound')
        for i=0,count-1 do materials[i+1]=source:GetMaterial(i);assert(usable(materials[i+1]))end
        local total=0
        for path,duration in pairs(assert(animations[id],'captured animation catalog required'))do
            total=total+1;assert(total<=256,'visual animation catalog bound')
            assert(type(path)=='string' and #path<=256 and type(duration)=='number'
                and duration==duration and duration>0 and duration<=600,'invalid captured sequence')
        end
        assert(total>0,'at least one captured Boss sequence required for visual acceptance')
        local row={mesh=mesh,materials=materials,sequences={},relative=source:GetRelativeTransform(),lookup_at=0}
        cache[id]=row;return row
    end
    local function sequence_for(id,path)
        local a=assets(id);local old=a.sequences[path]
        if old and usable(old) then return old end
        local now=observer.now()
        if now<a.lookup_at then return nil end
        a.lookup_at=now+.25 -- at most four exact unloaded-sequence lookups per second
        -- Never synchronously LoadAsset from a received pose. Only assets which
        -- the game has already streamed can be posed on the rendering callback.
        local sequence=g.StaticFindObject(path)
        if not usable(sequence) then return nil end
        assert(sequence:IsA(sequence_class)==true and usable(sequence.Skeleton)
            and sequence.Skeleton:GetFullName()==a.mesh.Skeleton:GetFullName(),'visual sequence skeleton/class mismatch')
        assert(math.abs(sequence:GetPlayLength()-assert(animations[id][path]))<.001,'captured sequence duration changed')
        a.sequences[path]=sequence;return sequence
    end
    local function same_world(actor,world)return observer.identify(actor,world).world==world end
    local function resolve(record,restoring)
        scope:attest(restoring)
        local actor=calls:resolve(record.actor);assert(same_world(actor,record.world))
        return actor
    end
    self.mount=function(id,world,remember)
        scope:attest(false)
        local snapshot=observer.snapshot();assert(snapshot.world==world,'visual spawn World changed')
        local pc=api.getPlayer1();assert(same_world(pc,world))
        local a=assets(id)
        local transform=maths:MakeTransform({X=0,Y=0,Z=0},{Pitch=0,Yaw=0,Roll=0},{X=1,Y=1,Z=1})
        local actor=statics:BeginDeferredActorSpawnFromClass(pc,actor_class,transform,1,nil,0)
        assert(usable(actor) and calls:same(actor:GetClass(),actor_class),'visual spawn must be the plain Engine.Actor')
        local row={actor=calls:reference(actor),world=world,boss=id}
        remember(row) -- ownership survives partial construction failures
        peer:register(observer.identify(actor,world),'remote_ghost')
        actor:SetActorEnableCollision(false);actor:SetActorTickEnabled(false);actor:SetActorHiddenInGame(true)
        assert(calls:same(statics:FinishSpawningActor(actor,transform,0),actor))
        local root=actor:AddComponentByClass(scene_class,false,transform,false);assert(usable(root))
        local mesh=actor:AddComponentByClass(mesh_class,false,a.relative,false);assert(usable(mesh))
        row.root,row.mesh=calls:reference(root),calls:reference(mesh)
        assert(calls:same(actor.RootComponent,root) and calls:same(mesh:GetAttachParent(),root)
            and calls:same(mesh:GetOwner(),actor),'visual component ownership changed')
        mesh:SetComponentTickEnabled(false);mesh:SetCollisionEnabled(0);mesh:SetGenerateOverlapEvents(false)
        mesh:SetSkeletalMesh(a.mesh,true);mesh:SetAnimationMode(1,true);mesh:SetPlaying(false)
        for i,material in ipairs(a.materials)do mesh:SetMaterial(i-1,material)end
        assert(actor:GetActorEnableCollision()==false and actor:IsActorTickEnabled()==false
            and mesh:IsComponentTickEnabled()==false and mesh:GetCollisionEnabled()==0
            and mesh:GetGenerateOverlapEvents()==false and mesh:GetAnimationMode()==1
            and mesh:IsPlaying()==false,'visual actor is not inert')
        return row
    end
    self.update=function(row,frame,world)
        assert(row.world==world and frame.boss==row.boss,'visual identity changed')
        local actor=resolve(row,false);local mesh=calls:resolve(row.mesh)
        assert(calls:same(mesh:GetOwner(),actor) and mesh:IsComponentTickEnabled()==false
            and actor:GetActorEnableCollision()==false and mesh:GetCollisionEnabled()==0
            and mesh:GetGenerateOverlapEvents()==false and mesh:GetAnimationMode()==1 and mesh:IsPlaying()==false,
            'visual animation/collision changed')
        assert(frame.animation=='-' or animations[row.boss][frame.animation],'uncaptured animation')
        local sequence=frame.animation~='-' and sequence_for(row.boss,frame.animation) or nil
        local animation=sequence and frame.animation or '-'
        if row.animation~=animation then
            mesh:SetAnimation(sequence);mesh:SetPlaying(false);row.animation=animation
        end
        if sequence then mesh:SetPosition(frame.time,false)end -- false is mandatory: no notifies
        actor:K2_SetActorLocationAndRotation({X=frame.x,Y=frame.y,Z=frame.z},{Pitch=0,Yaw=frame.yaw,Roll=0},false,{},true)
        actor:SetActorHiddenInGame(false)
        return true
    end
    self.destroy=function(row)
        scope:attest(true)
        local actor=calls:optional(row.actor)
        if not actor then return true end
        assert(same_world(actor,row.world),'refuse cleanup of a substituted visual World')
        actor:SetActorHiddenInGame(true);actor:K2_DestroyActor()
        return not usable(actor) or actor:IsActorBeingDestroyed()==true
    end
    self.sample=function(id)
        scope:attest(false)
        local body=peer:network_body();if not body then return nil end
        local observed=observer.identify(body)
        if observed.class~=config.bosses[id].class_path then return nil end
        local location,rotation=body:K2_GetActorLocation(),body:K2_GetActorRotation()
        local frame={world=observed.world,map=api.coop.net.localMap,x=location.X,y=location.Y,z=location.Z,
            yaw=rotation.Yaw,animation='-',time=0}
        local anim=body.Mesh:GetAnimInstance()
        if not usable(anim) then return frame end
        local montage=anim:GetCurrentActiveMontage();if not usable(montage) then return frame end
        local path=montage:GetFullName():match('^[^ ]+ (.+)$')
        local segments=sampling[id] and sampling[id][path]
        if not segments then return frame end
        segments_valid(id,segments)
        local position=anim:Montage_GetPosition(montage)
        local selected
        for _,segment in ipairs(segments)do
            local length=segment.finish-segment.start
            local span=length*segment.loops/math.abs(segment.rate)
            if position>=segment.at and position<segment.at+span then
                if selected then return frame end -- blended/ambiguous tracks are not a single-node pose
                local elapsed=(position-segment.at)*math.abs(segment.rate)%length
                selected={path=segment.path,time=segment.rate>0 and segment.start+elapsed or segment.finish-elapsed}
            end
        end
        if selected and animations[id] and animations[id][selected.path] then
            frame.animation,frame.time=selected.path,selected.time
        end
        return frame
    end
    return self
end
return M
