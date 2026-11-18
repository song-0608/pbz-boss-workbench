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

六角色 3C 候选另有 40 组离线回归与部分实机记录，见 `角色3C调校开发记录.md`；持续步速、自由转镜头、跨图与整体流畅度仍未完成最终验收。本轮没有把这些开发候选标为最终交付。
