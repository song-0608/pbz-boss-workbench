-- Developer-only route between two packages already observed through native
-- travel. The ordinary player launcher never enables scene_transition_trial.
local Trial={}
local valley='/Game/Maps/B02/PBZ_Xigu_WP'
local forest='/Game/Maps/B03/PBZ_Fujizhilin_WP'
function Trial.destination(current)
    if current==valley then return forest end
    if current==forest then return valley end
    error('cross-map trial requires an observed valley/forest package')
end
return Trial
