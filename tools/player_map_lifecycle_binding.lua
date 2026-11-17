-- Inserted inside Arena.start after wait_for_player is defined, before any timer.
if experiment_player_entry then
    local travel=require('map_travel_guard').new({runtime=function()return runtime end,attest=guard,log=log,
        same_world=function(world,reference)
            return valid(world)and assembly_calls
                and assembly_calls:same(world,assembly_calls:resolve(reference))
        end})
    map_lifecycle=require('player_map_lifecycle').attach(_G,{
        attest=guard,log=log,
        reference=function(world)
            if not valid(world)then return nil end
            return {name=world:GetFullName(),address=world:GetAddress(),class=world:GetClass():GetFullName()}
        end,
        invalidate=function()readiness_query:invalidate()end,
        suspend=function(world)
            -- Retire first, including initialization/settle and queued begin calls.
            assembly_tasks:retire()
            if assembly_world then
                assert(valid(world)and assembly_calls:same(world,assembly_calls:resolve(assembly_world)),
                    'LoadMap World differs from current partial or ready assembly')
            end
            travel:before(world)
            if actor or runtime or setup_ticket then assert(cleanup(),'preload owned cleanup not verified')end
            actor,ai,target_actor,target_ai,session,runtime,setup_protection,setup_ticket=nil,nil,nil,nil,nil,nil,nil,nil
            extra_targets={};initialized_owned={};spawn_attempts=0;initialization_deadline=nil;rejected_layouts={}
            assembly_world,assembly_calls=nil,nil
            gate_started,stationary_polls=0,0
            readiness_player,readiness_health,health_stable_polls=nil,nil,nil
            log('MAP_TRAVEL_IDLE_CLEANED',true)
        end,
        resume=function()
            -- Post only restarts the existing stationary/health/readiness checks.
            assembly_tasks:defer(1000,wait_for_player)
        end,
    })
end
