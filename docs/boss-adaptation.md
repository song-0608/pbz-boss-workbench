# Boss 适配

## 数据与职责

| 入口 | 用途 |
| --- | --- |
| [角色目录与档案](../research/boss-adaptation) | 保存观察来源、角色和配置候选，以及批次清单。 |
| [适配注册表](../tools/boss_adapter_registry.py) | 按角色汇总类、配置、技能候选与待复核项。 |
| [元数据任务](../tools/boss_metadata_jobs.py) | 统一组织角色类、配置变体和技能类查询。 |
| [批次收据复核](../tools/collect_boss_metadata_jobs.py) | 从闭合会话记录重算结果，并检查批次与来源。 |
| [适配复核](../tools/boss_adapter_review.py) | 保留变体、冲突和缺失项。已取得有效观察的任务不再进入缺失项重试。 |

## 从候选到发布

1. 从已有来源生成独立候选。资源路径和显示名只能提供线索，角色身份以类和实际配置的对应关系为准。
2. 分开核对普通能力和连招调度入口，记录技能来源和实际授予。配置不匹配或观察矛盾时保留待复核状态。
3. 先运行离线检查，再在隔离研究场景核对该角色的接管、恢复、单招完成、取消、实际效果和跨场景行为。
4. 发布前核对候选和源码摘要。只有具备对应证据的角色与能力进入玩家菜单。

## 离线检查

在仓库根目录运行：

```powershell
python -B -X utf8 -m unittest discover -s tests -p "test_boss_adapt*.py"
python -B -X utf8 -m unittest discover -s tests -p "test_boss_metadata_jobs.py"
```

`tools/run_boss_offline_milestone.py` 在配置了已有研究输入的机器上生成离线候选和批次。本地夹具结果用于校验数据和流程，实机表现需通过对应候选的集中验收。
