# 研究流程约定

- 默认先完成后端实现和离线回归，按里程碑集中实机验收；联机适配暂缓。
- 当前研究起点为“悲泣溪谷—斧老大斩落处”。已保存游戏原生研究存档到 `E:\项目\PBZ-Boss操控研究\研究场景存档`。
- 新的普通研究会话使用 `python -B -X utf8 tools/research_scene_checkpoint.py prepare`；集中验收使用同一命令加 `--acceptance`。该入口先执行原准备流程，再核对快照摘要并应用到已关闭的隔离研究箱，启动后选择“继续游戏”。不要直接调用旧 prepare 导致丢失固定起点，也不要每轮要求用户手动传送。
- 工作台默认入口为 `开始Boss工作台.cmd`，第1步已接入上述场景恢复。正式游戏与正式存档不作为测试对象。
- 场景快照内容与应用校验已经通过；冷启动画面确认因窗口工具 `foreground window did not report a process id` 中断，当前 `reload_verified=false`。后续集中实机验收顺便观察实际出生点，未观察前不要将此项写为通过。
- 不访问背包等无关界面；不绕过会话时限、焦点检查、隔离检查或验收门槛。保留失败记录和历史冻结工具。
- Python 运行带 `-B -X utf8`，避免冻结工作流出现 `__pycache__`。
- 当前交付为四Boss v4；说明见 `72-四Boss技能扩展v4操作说明.md`，只读核验使用 `tools/verify_boss_skill_delivery.py`。
