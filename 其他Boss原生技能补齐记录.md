# 其他 Boss 原生技能补齐记录

2026-11-18。此记录是后端适配里程碑；已安装版本仍为六角色工作台 v5。

## 已定位的遗漏

| 角色 | 历史真实授予中遗漏的技能 | 本轮 CDO 结论 | 当前状态 |
| --- | --- | --- | --- |
| 弦儿 | Skill_01、CA | 均为独立叶能力 | 两项攻击实验候选；未通过伤害与重复释放验收 |
| 魔渊 | Dodge_F_02、Dodge_R_02 | 均为独立叶能力 | 两项闪避实验候选；尚无已适配攻击 |

原始授予来自已正常关闭的会话 `20261117-190547`、`20261117-194042`。提取只接受唯一角色身份之后、下一次装配边界之前的实际授予，拒绝重复、跨装配拼接与外角色身份。

本轮会话 `20261118-185553` 只读核对四项能力，全部为 leaf；没有装配 Boss、手动授予或施放技能。关闭核对确认研究箱为空，加载器移除，56 项正式文件、主机配置与注册表无变化。固定溪谷起点自动恢复，无需手动传送。

## 可复用流程

`tools/boss_native_grant_followup.py` 冻结历史授予对应的元数据请求；`tools/native_grant_metadata_workflow.py` 分阶段装配只读脚本、签发十秒焦点检查、捕获原始结果、关闭后收集并独立重放凭据。输入由 computer-use 的窗口级 API 执行；工具本身不发按键、不启动游戏。

本次元数据包：`research/boss-adaptation/native-grant-followups/adc62361d82826f37842`。

关闭凭据：`research/boss-adaptation/native-grant-metadata-receipts/20261118-185553-adc62361d82826f37842.json`。

核验命令需使用本机 Python，并带 `-B -X utf8`：

```text
tools/native_grant_metadata_workflow.py verify research/boss-adaptation/native-grant-metadata-receipts/20261118-185553-adc62361d82826f37842.json
tools/check_native_grant_followups.py
```

下一批元数据使用 `stage → reload-gate → 一次原生 Ctrl+R → capture → 关闭核对 → collect`。不使用旧 catalog 验证器冒认这些原生授予路径，也不修改旧凭据。

## 冻结实验候选

- 弦儿：`research/boss-adaptation/developer-bundles/native-grant-071_xianzhe-25e29c3614cad7a2`；流程 `runtime/developer-workflows/native-grant-071_xianzhe-af309df717ace5c5`。
- 魔渊：`research/boss-adaptation/developer-bundles/native-grant-067_motian-5ccfc469f429501e`；流程 `runtime/developer-workflows/native-grant-067_motian-5dbc4e7744d56416`。

两个实验池各两项，复用已核定的角色身份与原生叶能力绑定器。装配时仍须验证当前进程 CDO、当前原生唯一且空闲的授予实例；拒绝手动授予、subtree、重复与活动实例。魔渊两项仅为闪避，不计作攻击技能。实验包不安装、不自动部署、不注册到玩家菜单。

新工具回归共 13 项 Python 测试与两个生成候选的 Lua 集成检查通过。Lua 检查使用假原生对象，验证精确绑定、只绑定实际授予项和失败原子性，不作为引擎动作证明。报告：`evidence/adaptation/native-grant-followups-offline-311694de7d8bb7f4.json`。共享元数据流程 22 项既有回归亦通过。

## 未完成的验收

下一次集中实机先验弦儿两个攻击候选的真实授予、逐技能自然结束和活动取消、命中伤害、同招至少三至五次重复释放，再决定是否扩展玩家配置。魔渊仍需攻击能力的真实授予与依赖适配，不能以两项闪避代替完整角色。

六角色 3C 当前候选另有 41 组离线回归；历史候选的部分实机记录独立保留，见 `角色3C调校开发记录.md`。持续步速、自由转镜头、跨图与整体流畅度仍未完成最终验收。本轮没有把这些开发候选标为最终交付。

## 分离后台准备与窗口重载

`tools/native_grant_ui_stage.py` 新增独立流程，解决旧开发装配器在写入脚本后直接发送重载按键的问题。旧工具、旧候选与冻结凭据保持原样；新生成目录只含无输入的准备脚本和精确 Boss 门槛模块，不带旧按键批处理器。

| 角色 | 现有实验池 | 新流程 |
| --- | --- | --- |
| 弦儿 | Skill_01、CA 两项攻击候选 | `runtime/developer-workflows/native-grant-ui-071_xianzhe-dc9f98a8b4db6b3e` |
| 魔渊 | 前闪、右闪两项候选 | `runtime/developer-workflows/native-grant-ui-067_motian-9e80f7525a7bcfa3` |

离线入口为 `tools/check_native_grant_ui_stage.py`。本批合计 23 项 Python 回归通过，其中 10 项覆盖新流程，其余覆盖既有原生授予、元数据凭据和候选。报告：`evidence/adaptation/native-grant-ui-stage-offline-cdd09f92c23fd697-1795004190338323000.json`。全部使用假会话、临时文件和离线生成，没有启动游戏、写入真实研究箱或发送输入。

后续集中实机按以下阶段执行；Python 仍须带 `-B -X utf8`：

1. 用固定场景入口准备研究会话，完成当前进程的只读原生契约核对。新流程不调用旧 `arm`，也不会自动启动游戏或补做会发送输入的探针。
2. 执行 `tools/native_grant_ui_stage.py stage <新流程目录>`。只允许未接管的只读研究载体，保留至少 180 秒会话余量，核对真实仓库源码、原生声明、隔离策略、原生授予池及正式文件。写入意图先留档；失败不自动重试。只写研究镜像，拒绝链接或目录联接指向的模块路径。
3. 执行 `tools/native_grant_ui_stage.py reload-gate <新流程目录>`。只读核对准备时同一 PID、脚本与装配摘要、期限和唯一前台研究 HWND，返回十秒内有效的 Ctrl+R 窗口凭据。工具不发按键，不延长原有授权。由 computer-use 窗口 API 单独执行一次重载，随后观察状态；已出现本次生命周期日志即不再签发重复重载。
4. 执行 `tools/native_grant_ui_stage.py capture <新流程目录>`，记录真实初始化与实际绑定；没有授予的技能逐项列为缺口。此捕获只证明观察到初始化，不声明激活、伤害、恢复或角色可玩，也不把旧工作台状态改成已接管。
5. 继续技能验收前另做新鲜动作检查与窗口输入；禁止调用旧按键批处理器。结束时使用真实仓库现有 `tools/ahua_practice.py stop` 和关闭核对，保留原始日志、准备意图、部署归档、窗口门槛与捕获结果。只有准备或初始化记录不能替代技能和收尾验收。

本批流程已完成后端回归，尚未在真实研究会话执行。弦儿两攻击仍待激活、重复释放、活动取消与命中；魔渊仍未适配攻击，不新增玩家菜单角色。

## 同一次接管的连续释放与动作窗口

新增 `tools/boss_skill_repeat_audit.py`，针对“两次后不能再用”的反馈检查同一次接管、同一 World 与同一组参与者中的三至五次连续自然释放。不能拼接多次恢复再接管，也不能忽略第五次之后出现的失败。每次须有活动实例、匹配的运行时短类名、自然归零、对应血量与局部位移；攻击不能用位移代替血量下降。恢复证据和明确 F10 退出分别记录。

此工具只读已关闭会话。日志中的短类名不等于完整授予路径，目标血量下降也不等于已独立归因的伤害；因此始终不授予可玩标记，不替代精确原生授予、活动取消和完整玩家验收。

重放历史会话 `20261118-182949`：

- 游龙首轮接管的五次 `skill_01` 均自然结束、每次血量下降 100，自动打开工作台后的恢复证据通过；不是 F10 退出验收。记录：`evidence/adaptation/boss-skill-repeat-135c1e7a208ac877.json`。
- 万钧下一轮 `skill_07` 只有一次自然结束且血量下降为 0，未达到连续次数，也没有该轮明确恢复证据，不通过。记录：`evidence/adaptation/boss-skill-repeat-834aab29175f6a9d.json`。

新增 `tools/stage_readonly_contracts.py` 分开只读镜头/阵营查询的后台写入与窗口重载；不执行旧探针里的直接按键。新增 `tools/native_grant_skill_gate.py`，只针对已捕获原生绑定签发 F6、实际 F1–F4 技能键或 F10 的十秒窗口凭据。施法前要求同一 PID、完整源码、当前接管身份、新鲜可见目标和上次自然归零；拒绝原生失败后的自动重试。F10 恢复无需等待目标或技能自然结束，便于单独做活动取消验收。两者均不发送输入、不启动游戏。

本批 15 项新测试通过，覆盖重复动作、异常区间、恢复借用、目标/焦点/原生拒绝与只读查询边界。报告：`evidence/adaptation/boss-repeat-window-gates-offline-d743ca5ce1ba3b4a.json`。

## 本次集中验收准备未通过

会话 `20261118-211942` 通过固定场景入口发起一次准备，但在进入游戏前未找到可核验的研究 Steam 主窗口，流程拒绝采集登录内容并自动关闭研究箱。没有启动游戏、应用场景快照、装配角色或发送玩法输入；没有反复启动或代操作认证。

关闭核对确认研究箱为空、无加载器，56 项正式文件、主机配置与注册表无本轮变化。摘要：`evidence/adaptation/boss-followup-preparation-20261118-211942.json`。因此弦儿、魔渊和当前 3C 候选仍没有本轮实机通过凭据，不视作交付。
