# 多 Boss 适配注册表与共享运行架构

2026-11-17，承接 `df4f1a2`。本轮推进其他 Boss 的离线适配准备，同时将角色差异从联机原生装配流程中拆出。没有启动 Steam 或游戏，没有安装候选或签发租约。

## 新一批角色

使用既有 104 个资源目录及 15 份来源记录，逐项复核来源哈希后生成 6 份独立适配清单。这里只使用观察到的内部资源标识，不推断游戏显示名或角色身份。

| 内部标识 | 角色类候选 | 配置候选 | 能力路径候选 | 当前结果 |
| --- | ---: | ---: | ---: | --- |
| `054_zuoshang` | 1 | 1 | 27 | 下一批身份元数据查询已生成 |
| `066_rentuzi` | 1 | 1 | 11 | 下一批身份元数据查询已生成 |
| `071_xianzhe` | 1 | 1 | 9 | 下一批身份元数据查询已生成 |
| `058_maddoctor` | 2 | 2 | 14 | 需要区分本体、精英或其他变体绑定 |
| `067_motian` | 2 | 3 | 36 | 需要区分本体与龙柱等配置绑定 |
| `076_zuoshang_p2` | 1 | 2 | 14 | 需要区分角色本体与龙柱配置 |

共整理 111 条能力路径候选，其中下一批三只角色有 47 条。路径数量不代表已授予、可释放或已验收技能。后三只角色没有按目录或排列顺序强行配对。

下一批只包含 3 个角色的 6 项身份查询，检查精确类、继承链、类默认对象的 Actor Config 和显示名。请求路径使用现有生成器的 Unreal 对象后缀规则，明确标记为待核对请求；它们不是已确认的类身份。本轮没有执行这些真实游戏查询。

## 已落地的架构调整

```mermaid
flowchart LR
    A[观察到的资源与来源哈希] --> B[每个 Boss 的适配清单]
    B --> C[最多三对的缺失身份查询批次]
    B --> D[多变体绑定待办]
    C --> E[独立身份、技能与实机验收]
    E --> F[可玩目录]
    F --> G[共享装配与恢复状态机]
    H[单独评审的 Boss 地形策略] --> G
```

- **发现与计划层**：`tools/boss_adapter_registry.py` 读取同版本资源目录和 `research/boss-adaptation/expansion-queue.json`，生成每只角色的类、配置、能力候选及未完成能力契约。新批次可通过数据清单调整顺序，不必复制装配代码。
- **批次层**：`tools/build_boss_adaptation_batch.py` 新增显式角色选择，限制一次最多三只无歧义角色。角色选择进入批次指纹，不同批次不会复用原三只角色的准备结果；默认选择也会跳过有歧义的类/配置组合。
- **运行差异层**：新增 `tools/phantom_boss_profile_policy.lua`，通过私有依赖加载器提供给原生装配器。共享装配器不再直接比较烟千岁 ID 来选择地形算法。已接受的三只普通角色使用通用算法，烟千岁继续使用已接受的九米、24 点净空算法。
- **运行流程层**：沿用同一套 Spawn、AI 登记、初始化、接管、恢复和销毁状态机。策略只在准备阶段求值，没有增加逐帧查询、重复资源扫描或额外计时器。
- **注册边界**：未知角色没有通用策略兜底，必须显式补充并评审。调用方得到策略副本，不能修改下一次装配的要求。准备中的六只角色仍为 `enabled=false`、`playable=false`，没有进入现有四 Boss 可玩目录。

## 一条后端验证入口

`tools/check_phantom_boss_backend.py` 已纳入新注册表、批次选择、策略层和下一批查询测试；`tools/verify_phantom_boss_backend.py` 独立复核源码、日志、候选及适配准备产物。新增查询测试覆盖成功、类身份不符和配置不符，仍使用测试替身。

完整通过 **530 组后端检查、67 份 Lua 编译及独立复核**。注册表可重复构建；篡改来源、候选清单、生成脚本，或将结果改写成实机通过时，复核会拒绝。脚本即使重新填写摘要，也必须与当前只读生成器输出逐字相符。

## 产物与复现

- 新角色准备报告：`evidence/adaptation/boss-adapter-expansion.json`。
- 6 份适配清单与注册表：`runtime/boss-expansion/d0bc3ded9baf0378665d`。
- 下一批查询包：`runtime/boss-expansion/d0bc3ded9baf0378665d/batches/offline-0ee3447c989783c9`。
- 当前联机后端候选：`runtime/online-candidates/bwb-phantompact-b7a815e2facc2dd953e7`。
- 双端静态包：`runtime/online-stages/8e134ec038c64423b09bf137af8bc4e0`，404 个文件、52 份研究存档条目、4 份快照副本；未安装、未启动、未签发租约。

```powershell
python tools/boss_adapter_registry.py
python tools/boss_adapter_registry.py --verify
python tools/check_phantom_boss_backend.py
python tools/verify_phantom_boss_backend.py
```

既有四 Boss 单机包及个人设置保持一致。当前完整联机组合的实机表现、第二端独立登录以及新增角色的真实身份、技能和操控验收仍未完成；继续保持 `complete_mod=false`、`runtime_acceptance_current=false`。本轮交付的是适配准备和架构实现，不宣称新增六只 Boss 已可玩。
