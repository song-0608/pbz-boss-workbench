-- 用途：集中保存此构建的目标和按键；verified=false的技能不允许执行。
return {
    expected_exe_sha256 = "4415933ce33476f14c837abb61a1b60af8b78cd81783896501913a7aac69e423",
    boss_selection = "current_unlocked_boss", -- 只选当前已解锁对象；不编辑解锁进度。
    boss_display_name = "新娘阿花", -- 用途：真实资源显示名已确认；不代表实机操控通过。
    profile = "profiles.ahua", -- 用途：角色身份及技能绑定集中放在独立配置，不散落在输入代码中。
    controls = { enter = "F6", exit = "F10",menu_exit="ESCAPE" }, -- 用途：Esc先撤下Boss输入屏障，再按Esc可进入原游戏菜单。
    skills = {
        slot1 = { key = "F1", id = "skill_01", name = "阿花技能01", verified = false },
        slot2 = { key = "F2", name = "第二招待确认", verified = false },
        slot3 = { key = "F3", name = "第三招待确认", verified = false },
        slot4 = { key = "F4", name = "第四招待确认", verified = false },
    },
}
