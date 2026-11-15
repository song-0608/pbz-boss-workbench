# 自编译UE4SS与靶场验证

2026年11月12日：本人接受Epic邀请后，本机已能读取EpicGames/UnrealEngine与Re-UE4SS/UEPseudo。锁定的Unreal依赖已下载，通用UE4SS首次自主编译成功。

## 实际产物

物理目录：`D:\mod文档\build\ue4ss-ascii\Game__Shipping__Win64\bin`。

- `UE4SS.dll`：核心运行时，SHA-256 `27ca1098104e231ab40e89cc9f87643647fcb3937a8aa832b57e180df96bcff7`。
- `UE4SS.pdb`：对应调试符号，IDE断点和调用栈分析时使用。
- `dwmapi.dll`：本机从源码生成的代理加载器，SHA-256 `3c49d48565a0fb86241c18705728b83420e6fa0ab9dbf6b6cc1750a442ff921f`。
- 配套代理PDB和两个C++工具Mod也已生成，尚未进行其功能验收。

主源码提交 `560411f18512b6c9395285e55624de4b91a2c45b`；Unreal依赖提交 `c3dcec82c6356daffd754d4470bf1315584116ba`。主源码使用固定提交归档，没有主仓Git历史，因此DLL内嵌SHA显示unknown；实际来源、归档哈希及产物哈希另行留证，不能伪称内嵌提交已验证。

## 编译过程与已修正问题

初次生成VS工程成功，但MSBuild执行Rust自定义命令时在中文路径报“系统找不到指定的路径”并卡住。改用已存在的 `E:\ue4ss` 英文联接，重新建立独立生成目录，复用已下载的依赖源码后编译通过。这个入口实际指向D盘，并非另外复制资料。

重复构建：在 `D:\mod文档` 的PowerShell运行：

```powershell
.\tools\Build-UE4SS.ps1 -WorkspaceAlias E:\ue4ss
```

日志在 `D:\mod文档\evidence\setup`。编译有上游警告，不等于零警告构建。

## 自制靶场真实验证

测试对象为自制UE5.8.1 Development打包程序，使用NullRHI，不是PBZ。沿用此前按匹配PDB推导的本地StaticConstructObject签名及最小Hook配置。

1. 核对实际加载模块路径为本次自编译DLL。
2. Lua打印START，证明入口运行。
3. 在游戏线程查找并读取 `/Script/Engine.Actor` 类的全名。
4. 找到World实例并读取全名。
5. 全部通过后打印PASS，保持观察后结束本测试进程，并撤除临时代理。

首次启动命令曾被UE把 `--ue4ss-path` 后面的DLL路径误判为地图，已修正为先明确指定 `/Engine/Maps/Entry`。第二次真实测试通过，不是mock。

中文注释脚本：`D:\mod文档\mods\SelfBuildSmoke\Scripts\main.lua`。
重复测试：`D:\mod文档\tools\test_selfbuilt_ue4ss.py`。
证据：`D:\mod文档\evidence\setup\selfbuilt-ue4ss-verification.json`、`D:\mod文档\evidence\selfbuilt-ue4ss\latest-result.json`。

## 结论范围

已完成“获授权依赖→通用源码自主编译→代理加载→Lua→只读反射对象”链路。未验证完整Hook集合、图形界面、正常退出、PBZ兼容性或Boss控制。测试日志仍有禁用可选Hook和FObjectPtrProperty相关警告，应保留这些限制。

下一阶段继续PBZ研究环境的真实设置写入隔离，再使用自编译通用DLL只读初始化，依据真实扫描失败项逐一研究签名及布局。
