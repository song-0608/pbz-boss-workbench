# 自己适配的 UE4SS：真实通过了什么，先学哪几行

## 已完成的真实结果

通用源码自行编译的 UE4SS，配合本项目从原版指令推导的 GUObjectArray 签名与布局配置，已在固定 PBZ build 26367565 中完成初始化，并在两个不同游戏进程中通过同一份只读 Lua 测试。两次游戏都正常退出，主体退出码均为 0。

两次测试使用同一个离线研究 Steam 会话，不能写成“两次独立 Steam 客户端冷启动”，也不能推导为跨游戏版本兼容。没有向正式安装目录部署 DLL。

验收日志记录：

```text
PBZ_READONLY_SMOKE:ACTOR=Class /Script/Engine.Actor
PBZ_READONLY_SMOKE:PROPERTY_COUNT=80
PBZ_READONLY_SMOKE:JUMP_MAX_COUNT=1
PBZ_READONLY_SMOKE:MOVEMENT=CharacterMovementComponent /Script/Engine.Default__Character:CharMoveComp
PBZ_READONLY_SMOKE:WORLD=World /Game/Maps/ServerCheck.ServerCheck
PBZ_READONLY_SMOKE:PASS
```

这里的 Character 是引擎默认对象，World 是启动阶段已存在的 ServerCheck 世界。没有声称已经读到当前玩家、战斗地图或 Boss 实例。

证据：`evidence/official-validation/20261112-234911/` 中的 `UE4SS-lua-first-pass.log`、`UE4SS-lua-second-pass.log`、`two-game-launches-lua-pass.json`、两份 `normal-exit` 记录和主菜单截图。收尾报告核对 56 个已发现正式文件：相对实验开始无变化。37 份历史备份完整；正式文件与早晨备份已有 12 项差异是此前存在的，未自动回档。

## UE4SS 到底是什么

UE4SS 的核心是 DLL 和脚本运行环境。你通常通过启动已配置研究加载器的游戏，让它随游戏载入，不是双击 UE4SS.dll 打开一个普通软件。

本项目的链条是：原版游戏程序 → 研究箱中的 dwmapi 加载器 → 自己编译的 UE4SS.dll → 解析引擎对象与类型 → 在游戏线程执行 Lua。Live Viewer 是可选界面，本轮没有验收它。

现阶段不要把研究配置拖进正式游戏目录。当前“打开研究工作台.cmd”用于查看研究进度和资料；受控游戏测试仍通过带断网、备份与收尾检查的研究工具进行。

## 你的第一个十分钟训练

打开 `adaptation/pbz-26367565/Mods/PBZReadOnlySmoke/Scripts/main.lua`，按顺序只读下面几个位置：

1. `print(...START...)`：证明文件开始运行。它本身不代表适配成功。
2. `ExecuteWithDelay(2000, ...)`：等待两秒；单位是毫秒。
3. `ExecuteInGameThread(...)`：将对象访问交给游戏线程执行。
4. `StaticFindObject("/Script/Engine.Actor")`：找的是类定义，不是场景中的敌人。
5. `assert(actor:IsValid(), ...)`：对象不存在就停止，不继续使用无效对象。
6. `character.JumpMaxCount`：读取属性；代码中没有给它赋新值。
7. `character.CharacterMovement`：读取默认角色的移动组件对象。
8. `FindFirstOf("World")`：寻找运行中的世界对象。
9. `print(...PASS...)`：前面的检查都成功才执行到这里。

本轮只需要你能用自己的话解释这九项。注释是用途提示，真正理解的标准是能说出“删掉这一行会少验证什么”。

主文件与验收哈希绑定，练习改代码先复制到自己的草稿目录，不直接改已验证版本。第一个练习可以只有一行 `print("这是我的第一条研究日志\n")`；先在自制靶场测试，再纳入 PBZ 受控实验。

## 实际解决过的适配问题

- 对象数组：通用签名无匹配，从统计指令推导 AOB，通过 RIP 相对位移解析目标，再用对象索引、分块、类指针交叉验证。
- 反射结构：数组字段重排，FField 的 Next/Owner 互换，FFieldClass 的名称/构造器与 CastFlags/Id 互换。
- 类与函数：UStruct 派生尾部后移，默认对象与函数参数信息的旧偏移失效。旧偏移读到“非空地址”仍可能是代码地址。
- 初始化崩溃：通用删除监听器偏移实际指向临界区；由原版添加监听器指令确认数组真实位置。
- Lua 绑定：此源码版本的属性遍历对返回 false 存在重复弹栈路径；本脚本返回 nil 继续遍历。源码 get_bool 会移除栈项，这是代码层原因，不能继续靠改游戏偏移解决。

配置中部分尾部字段仍按连续位移推导；功能测试只覆盖已列出的路径，没有把 59 个配置键都宣称为逐项实测。

## 已读到的 AI 线索

只读反射元数据确认存在 `/Script/ProjectPBZ.AIScript_TargetSelector_opt`，其声明包含 SwitchTargetCooldown、LastSwitchTime、FoundActor、TargetDistance 等字段；存在 PBZCharacter、PBZCharacter_Player、PBZPlayerController、PBZGameplayAbility、PBZAbilitySystemComponent 等类。

这些是实际声明，不是猜的类名。但仅凭声明不能确认当前 Boss 用了哪套逻辑、技能何时能调用，或一个字段是否对应完整仇恨系统。下一步需要在已确认隔离的战斗副本里观察真实实例与变化。

## 简历与口述草稿

在你能自己复现和解释上述流程后，可使用下面的事实版描述：

> UE5 单机游戏运行时适配与 AI 观测研究（个人学习项目）
> 基于通用 UE4SS 源码完成构建，针对固定游戏版本推导并验证对象数组 AOB 与 RIP 相对寻址，修正对象数组及反射结构布局；编写只读 Lua 验收脚本，验证类、属性链、整数/对象属性与 World 查找，在两次游戏进程启动中复现结果；通过离线沙盒与文件哈希对比隔离实验，建立 AI 目标选择及角色/技能系统的反射观察线索。

当前不能追加“已实现 Boss 操控”“所有技能按键化”“多人同步已完成”。这些需要后续实机证据。

面试一分钟可以这样讲：

> 我的目标是理解游戏 AI，所以先解决运行时观察工具的适配。通用版能加载，却找不到对象数组。我根据原版的统计指令写签名，再检查对象的索引和类指针，避免找到假地址。之后发现反射成员有重排，分层验证类名、属性链和实际属性读取。工具在两个游戏进程中通过同一份 Lua 测试后，才转向游戏自己的选目标和技能类。Boss 控制仍在开发，我会把已验证结果与待实现功能分开说明。
