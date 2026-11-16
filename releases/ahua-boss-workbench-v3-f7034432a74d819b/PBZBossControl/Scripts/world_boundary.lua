-- 用途：场景销毁时只读核对旧World和所有被修改对象；不向新World套用旧恢复凭据。
local Boundary={}
local function reference(value)return type(value)=='table'and type(value.name)=='string'
    and type(value.address)=='number'and type(value.class)=='string'end

function Boundary.references(receipt)
    local refs,seen={},{}
    local function add(label,ref)
        if not ref then return end
        assert(reference(ref),'malformed world retirement reference: '..label)
        local key=ref.name..'|'..ref.address..'|'..ref.class
        if not seen[key]then refs[#refs+1]={label=label,ref=ref};seen[key]=true end
    end
    for _,key in ipairs({'world','player_controller','player','boss','ai','brain','asc','camera'})do add(key,receipt[key])end
    for index,ref in ipairs(receipt.owned_world_objects or{})do add('owned_world_objects.'..index,ref)end
    for group,keys in pairs({camera_rig={'camera','boss','boom','component'},
        input_barrier={'pc','owner','component'},player_protection={'player','movement'},
        remote_control={'pc','player','boss','ai','brain','game_ai'},combat={'component','targeting','boss','focus_controller'}})do
        local ticket=receipt[group]
        if ticket then for _,key in ipairs(keys)do add(group..'.'..key,ticket[key])end end
    end
    return refs
end

function Boundary.inspect(calls,receipt)
    assert(reference(receipt.world),'captured World reference required')
    local lookup=calls.retirement_optional or calls.optional
    local world=lookup(calls,receipt.world)
    local pc=lookup(calls,receipt.player_controller)
    local ambiguous_world=type(world)=='table'and world.retirement_ambiguous
    local ambiguous_pc=type(pc)=='table'and pc.retirement_ambiguous
    if world and pc and not ambiguous_world and not ambiguous_pc then
        local actual
        if calls.optional_world then actual=calls:optional_world(pc)else actual=calls:world(pc)end
        if actual and actual.name==receipt.world.name and actual.address==receipt.world.address
            and actual.class==receipt.world.class then return 'same' end
    end
    local surviving={}
    for _,row in ipairs(Boundary.references(receipt))do
        if lookup(calls,row.ref)then surviving[#surviving+1]=row.label end
    end
    if #surviving>0 then return 'pending',table.concat(surviving,',')end
    return 'retired'
end
return Boundary
