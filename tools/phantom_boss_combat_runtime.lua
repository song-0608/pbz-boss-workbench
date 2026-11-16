-- Dedicated combat composition. Do not initialize the upstream story, inventory,
-- travel, local-player or PvP modules, even when their INI options are off.
return function(api,directory,globals)
    local g=globals or _G
    api.lang=dofile(directory..'lang.lua')(directory)
    api.game=dofile(directory..'pbz.lua')(api)
    -- pbz.lua defines these lazily; removing them before coop initialization also
    -- prevents future call sites from installing backpack/pickup/rest hooks.
    local removed={
        'bagSummary','mergeBag','receiveGift','grantLoot','addCurrency','watchCurrency',
        'watchPickups','watchChests','watchStones','watchFlowers','hookFlowers','hookGifts',
        'hookPiles','hookRest','hookSit','watchGear','watchItemFx','ownLook','dressGhost',
        'takeRemotePickup','pickupCount','pickupSharesDue','showPickupTips','successTags',
        'guardFormations','flowerTaken','partnerOpened','hostOpened','stoneKicked',
        'oweBoss','downBoss','watchOwed','dropOwed','payOwed','owedState','noteDown',
    }
    for _,name in ipairs(removed)do api.game[name]=nil end
    api.game.commands={} -- no unlockall/items/spawn/debug command channel
    api.game.pickupShares,api.game.tipsWanted=nil,nil
    -- Legacy kill synchronization has unconditional reward calls. Return an empty
    -- result without invoking the game's loot table, backpack or currency APIs.
    api.game.rollLoot=function()return 0,{},0 end
    api.game.offerChestsAgain=function()end
    -- coop checks these two local split-screen predicates while joining a fight.
    -- This composition never creates a second local player or a travel panel.
    api.localcoop={bellMenuUp=function()return false end,screenUp=function()return false end}
    -- autostart's optional presentation callbacks; none register a timer or input.
    api.partner={teleport=false,start=function()end,goOnLink=function()end}
    api.onlinepanel={start=function()end}
    api.coop=dofile(directory..'coop.lua')(api)
    api.status=dofile(directory..'status.lua')(api)
    api.moves=dofile(directory..'moves.lua')(api)
    api.puppets=dofile(directory..'puppets.lua')(api)
    api.hitfx=dofile(directory..'hitfx.lua')(api)
    -- Keep a small inspection surface; no command-file evaluator or debug keys.
    g.PBZ={net=api.coop.net,coop=api.coop,game=api.game,link=api.link,
        getPlayer1=api.getPlayer1,version=api.version}
    api.bossWorkbench=dofile(directory..'bwb_startup.lua')(api,directory)
    g.PBZ.bossWorkbench=api.bossWorkbench
    local ok,why=pcall(function()dofile(directory..'autostart.lua')(api)end)
    if not ok then
        api.bossWorkbench:close()
        error('combat transport initialization failed: '..tostring(why))
    end
    return api.bossWorkbench
end
