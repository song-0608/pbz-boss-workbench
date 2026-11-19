# 本机离线角色转换器

从已授权的本机PBZ资源副本中读取明确列出的资产，输出可编辑源；不会启动、安装或修改游戏。依赖 `.NET 10`、`CUE4Parse` 与 `CUE4Parse-Conversion 1.2.2.202611`；该NuGet版本对应上游提交 `e76778c10ed25860e11ec488750753224d067d87`。

构建输出、中间文件和原始素材放在E盘，避免将SDK或游戏素材纳入仓库：

```powershell
dotnet build tools/creative_asset_exporter/PBZCreativeExporter.csproj -c Release `
  -o 'E:\项目\PBZ-Boss操控研究\创作协作\资产导出工具\PBZCreativeExporter\bin' `
  -p:BaseIntermediateOutputPath='E:\项目\PBZ-Boss操控研究\创作协作\资产导出工具\PBZCreativeExporter\obj\'
```

调用参数为 `dotnet <转换器.dll> <Paks目录> <本机私有Crypto文件> <job.json> <全新输出目录>`。Crypto文件只在本机读取；不要把密钥写入命令行、日志、示例或Git。输出目录非空即拒绝。

job的字段：`mode: inspect|export|declarations`、`game: GAME_UE5_7`、`packages: [明确.uasset路径]`、`usmap: 本机精确映射路径`、`mesh_format: Gltf2|USD`、`export_materials: true|false`。每批1至64个明确路径；动画使用USD，Gltf2仅用于模型/贴图。骨骼资产不能只凭 `SK_`、`SM_` 前缀筛选，必须检查真实导出类型与SkinParts子目录。

`declarations` 要求本机精确映射，只使用CUE4Parse原生UObject序列化输出属性和引用，不运行蓝图或导出模型。每包声明上限16MiB，输出带包路径、声明摘要、作业摘要、映射摘要及转换器DLL摘要。原始属性留在E盘；`boss_disk_declarations.py` 负责64包分批、跳过已核验成功批次和保留失败，`boss_disk_skill_index.py` 解析原生时间线，`boss_disk_live_coverage.py` 与已关闭会话的原生证据精确关联。完整流程见仓库 `原生技能离线适配工作流.md`。声明只含序列化覆盖值，不能代替父类默认值、原生授予、伤害或实机验收。

## 本机原生依赖

- Oodle：通过已安装UE的SDK在本机构建 `oo2core_9_win64.dll`，放转换器输出目录。当前SDK为UE5.8的 `OodleDataCompression/Sdks/2.9.16`。源码、SDK及DLL不随仓库分发。
- ACL：必须使用上述精确CUE4Parse提交的 `CUE4Parse-Natives`；ACL子模块 `414689d5cff4286a7898487a46dc5e48005d38da`，RTM子模块 `d7982f2b2524feeb322f424b29cf43df30b5d5b7`。按照上游许可证在本机构建 `CUE4Parse-Natives.dll`，与转换器放在一起。MSVC需 `/LD /std:c++17 /O2 /EHsc /MD /DWIN_EXPORT /DWITH_ACL`，编译 `ACL/ACL.cpp` 与 `Features.cpp`，包含 `common`、ACL includes及RTM includes。
- 类型映射：本轮精确游戏版本为 `ProjectPBZ-5.7.4-302256+b7c82f11b864`。映射由既有隔离租约内一次 `DumpUSMAP(false)` 取得，摘要为 `b1f8cc13f5788f75242c00710b00bf5ee611265c0cc1ced8180348ccadac537a`。映射文件保留在E盘，不入Git。需要重新采集时使用 `creative_usmap_capture.py` 的现有准备与观察门槛，不改冻结源、不跳过Cloud-OFF检查或期限。

## 后续流水线

1. `creative_gltf_prepare.py` 校验网格/蒙皮、生成贴图大小受限的作者副本。
2. `creative_gltf_assemble.py` 按相同骨名和绑定矩阵合并真实部件，重映射骨骼索引；不匹配就停止。
3. `creative_usd_bind_animation.py` 把原生解码动画与真实绑定网格组合为USD；不造关键帧。
4. `creative_import_boss_assets.py`、`creative_import_usd_animations.py` 只允许独立后台工程执行原生导入。
5. `creative_boss_library_assets.py` 构建首版库；`creative_boss_library_revision.py` 补齐弦儿部件并新建v3展厅。保留旧证据，不改写失败记录。
6. `creative_boss_preview_capture.py` 在独立后台编辑器执行一次有期限的六角色渲染；捕获完成不自动标记人工视觉通过。
7. `creative_boss_library.py publish|verify` 使用既有提案与三方集成流程添加资源，拒绝覆盖作者改动。

转换成功、动画采样成功与画面观察是不同证据。它们都不能替代原版技能事件、伤害、3C或游戏内加载验收。打包文件、原始索引、密钥、映射、模型、第三方SDK和二进制均留本机。
