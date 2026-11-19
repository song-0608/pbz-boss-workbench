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
- 同一默认CMD现在包含“Boss 开发与研究 / UE 创作与 3C / 统一集成与冲突”三页。UE作者工作区为 `E:\项目\PBZ-Boss操控研究\创作协作\UE工程\PBZCreative`，后台创作草稿为同目录的 `后台草稿\PBZCreative`；Mod代码仍在本仓库。双方各自保存、提交提案，工作台统一检查三方差异，不并发写同一份UE二进制资产，不把源码草稿直接装进研究箱。
- 创作提案只接收各自 `Content/PBZCreative` 与三份 `Config/PBZCreative/*.json`；提案/集成快照带摘要、来源与基线。JSON按字段合并，UE资产按整文件处理；冲突必须在工作台明确取舍，并绑定预览时的集成版本。集成不覆盖双方的编辑文件；接收结果保存在不可变集成快照，进入下一次开发构建。工作区原始资产在E盘，不上传Git。
- `tools/creative_workspace.py initialize|submit --lane ue|backend` 负责各自创作源；`preview <提案ID>` 与 `integrate <提案ID>` 只操作离线快照。新开发候选会固化一次已选集成的3C参数及来源摘要；未提交或未集成的草稿不能进入候选。新增视觉/场景资源仍是编辑器源，必须另行完成目标版本Cook、挂载/加载和集中实机验证，不得宣称已在PBZ生效。详见 `统一工作台协作说明.md`。
- “UE 创作与 3C”的“打开 UE 练习场”已接入 `tools/creative_starter_workspace.py`：首次后台调用本机UE原生命令生成并保存 `/Game/PBZCreative/Maps/L_PBZCreativeHub`、角色/GameMode子蓝图与Niagara喷泉，随后打开可见关卡。再次打开不得重建用户场景，工程正在运行时不得覆盖资产或再开同工程第二个编辑器。模板依赖保持 `Characters/Input/ThirdPerson/LevelPrototyping` 原包路径；只提交自有 `Content/PBZCreative` 和指定配置，Epic模板二进制不上传Git。
- UE练习场是创作示例，不包含PBZ Boss或原地图；本轮仅观察到PIE启动、模板角色与粒子显示，键盘移动/跳跃仍未独立验收。用户正在人工预览时停止自动按键，不关闭PIE、不抢焦点。旧版指引文字迁移只在下次打开且关卡干净、未播放时处理可识别的未改动标签，不据此宣称原地图迁移已实测。
