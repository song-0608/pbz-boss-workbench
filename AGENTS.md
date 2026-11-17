# 研究流程约定

- 默认先完成后端实现和离线回归，按里程碑集中实机验收；联机适配暂缓。
- 当前研究起点为“悲泣溪谷—斧老大斩落处”。已保存游戏原生研究存档到 `E:\项目\PBZ-Boss操控研究\研究场景存档`。
- 新的普通研究会话使用 `python -B -X utf8 tools/research_scene_checkpoint.py prepare`；集中验收使用同一命令加 `--acceptance`。该入口先执行原准备流程，再核对快照摘要并应用到已关闭的隔离研究箱，启动后选择“继续游戏”。不要直接调用旧 prepare 导致丢失固定起点，也不要每轮要求用户手动传送。
- 工作台默认入口为 `开始Boss工作台.cmd`，第1步已接入上述场景恢复。正式游戏与正式存档不作为测试对象。
- 场景快照与冷启动重新载入已通过：会话 `20261117-170957` 只点标题“继续游戏”，直接出生在保存的溪谷开阔区与寄魂点旁，没有穿行或传送，未装配Mod。独立记录见 `evidence/releases/research-scene-reload-20261117-170957.json`，用 `tools/verify_research_scene_reload.py` 核验。地点依据本轮画面观察及固定快照来源，未宣称自动图像识别。保留16:14那次窗口错误记录；捕获时的原始checkpoint与指针不变，不把其历史 `reload_verified=false` 当作最新验证状态。
- 不访问背包等无关界面；不绕过会话时限、焦点检查、隔离检查或验收门槛。保留失败记录和历史冻结工具。
- Python 运行带 `-B -X utf8`，避免冻结工作流出现 `__pycache__`。
- 当前交付为六角色工作台 v5（`ahua-boss-workbench-v5-3f29975fe3b8826f`）；说明见 `74-Boss工作台v5操作说明.md`，只读核验使用 `tools/verify_boss_workbench_v5.py`。弦儿仅两项闪避，魔渊未开放；联机暂缓。
- 默认CMD通过 `tools/workbench_status_bootstrap.py` 包装原始且摘要匹配的v5窗口，增加状态提示、重复步骤拦截及新窗口间步骤锁。界面扩展不改冻结的v5窗口、研究流程或游戏Lua；不会热更新旧窗口或重启正在进行的研究会话。回归见 `tests/test_workbench_session_status.py` 与 `tests/test_workbench_cmd_entry.py`。
