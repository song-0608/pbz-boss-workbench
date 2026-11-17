-- 用途：玩家主入口由隔离启动器注入一次性声明；手工复制DLL不会绕过本轮离线/构建检查。
local launch=rawget(_G,'PBZBossControlLaunch')
if not launch then
    print('[PBZBossControl] DISABLED: start through the protected offline launcher\n')
    return
end
_G.PBZBossControlLaunch=nil
return require('player_entry').start(launch)
