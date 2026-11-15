"""用途：将已完成的叠加层对照与安全收尾写入统一工作台；不启动游戏。"""
import json
import sys
from pathlib import Path
import official_validation as v


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    root=v.ROOT
    check=json.loads((root/'evidence/latest-native-diagnostic-postcheck.json').read_text(encoding='utf-8'))
    analysis=json.loads((root/'evidence/latest-offline-dump-analysis.json').read_text(encoding='utf-8'))
    assert check['validation_restored'] and check['research_box_empty']
    assert not check['formal_files_changed'] and not check['host_config_files_changed']
    assert check['all_temporary_network_removed'] and check['overlay_file_block_removed'] and check['nvidia_overlay_blocks_removed']
    assert analysis['selftest']['passed'] and len(analysis['runs'])==5
    v.verify_build() # 用途：再次核对两个已固定原版EXE的哈希及未部署加载器。
    summary='完成两轮有效叠加层排除实测：原版仍在PBZ.exe+0x14543cab访问异常退出；菜单未验收。临时联网已撤销，研究箱为空，56个正式文件与37个备份对象复核未变。'
    blocker='原版在当前研究沙盒仍持续崩溃；移除Steam及NVIDIA叠加组件后仍复现。5份转储未恢复可靠调用者帧，唯一根因尚未确定，不能进入UE4SS/Boss实机改造。'
    next_action='先以新的具体兼容性假设解决原版隔离启动；菜单通过后再做离线冷启动和真实存档隔离，随后才部署UE4SS。'
    common={'updated_at':v.utc8(),'status_summary':summary,'blocked_reason':blocker,'next_action':next_action,
        'latest_result_note':str(root/'17-叠加层排除实测与调用栈边界.md'),
        'latest_real_machine_diagnostic':str(root/'evidence/latest-native-diagnostic-postcheck.json'),
        'latest_official_validation_postcheck':str(root/'evidence/latest-native-diagnostic-postcheck.json'),
        'latest_native_crash_summary':str(root/'evidence/official-validation/20261112-200945/stackwalk.json'),
        'latest_offline_dump_analysis':str(root/'evidence/latest-offline-dump-analysis.json'),
        'official_validation_active':False,'official_validation_network_active':False,
        'official_client_preparation_network_active':False,'local_config_virtualization_override_active':False,
        'overlay_experiment_rules_active':False,'steam_overlay_absence_experiment_verified':True,
        'steam_and_nvidia_overlay_absence_experiment_verified':True,'original_crash_still_reproduces_without_overlays':True,
        'dump_analyzer_selftest_passed':True,'pbz_reliable_caller_frames_recovered':0,'root_cause_identified':False,
        'research_overlay_ui_enabled':False,'research_cloud_disabled_verified':True,
        'no_remaining_pbz_processes_verified':True,'last_game_exit_code':'0xC0000005',
        'gameplay_verified':False,'menu_verified':False,'game_save_isolation_verified':False,
        'game_initialization_verified':False,'boss_control_verified':False,'real_bridge_available':False,
        'no_loader_deployment':True,'awaiting_user':None}
    for path in (root/'项目状态.json',root.parent/'profiles/pbz-offline.json'):
        data=json.loads(path.read_text(encoding='utf-8'));data.update(common)
        if path.name=='项目状态.json':
            for item in ('Steam叠加层真实未加载时原版仍在同一偏移崩溃；模块采样和转储交叉核对',
                         'Steam与NVIDIA叠加组件均真实未加载时原版仍崩溃；已回收实验规则和联网',
                         '离线StackWalk64工具通过自建MAP调用链自检；5份PBZ转储的展开限制已如实记录'):
                if item not in data['completed']:data['completed'].append(item)
        else:
            data.update({'status':'native-game-crash-reproduced-without-overlays','note':summary})
        v.save(path,data)
    old=(root/'04-当前结果与下一关.md').read_text(encoding='utf-8')
    cleanup=old[old.index('## 整理与删除'):]
    text='''# 当前结果与下一关（2026年11月12日20:14更新）

**Boss还不能操控，UE4SS尚未部署。当前先解决原版在研究环境中的启动崩溃。**

## 最新实机结果

- 研究Steam离线冷启动和本人接受协议已有证据，无需重新完成这些步骤。
- PBZ断网启动仍显示服务器不可达；已授权的限时官方验证则出现访问异常。
- 本轮两项新对照真实移除了Steam叠加层、再移除NVIDIA叠加组件，游戏仍在同一位置崩溃，尚未到菜单。
- 离线分析器通过自建调用链自检，但5份游戏转储没有恢复出可靠调用者帧，根因未确定。
- 验证已结束，临时联网和实验规则已撤销，研究箱为空。56个已发现正式文件和37个备份对象复核未变。

完整对照和证据见 [17-叠加层排除实测与调用栈边界.md](17-叠加层排除实测与调用栈边界.md)。早期报告中的SteamAPI错误和“正在准备登录”不是当前状态。

## 怎样打开现有成果

双击同目录的 **打开研究工作台.cmd**：

1. 输入1：看当前真实状态和阻塞。
2. 输入2：运行17项Lua模拟测试与10步完整模拟；这些使用假的游戏接口，不启动PBZ。
3. 输入3：打开本说明。
4. 输入4：打开带用途注释的Lua源码。
5. 输入5：只读复核存档备份，不恢复或覆盖进度。

代码入口为 `mod/PBZBossControl/Scripts/session.lua`。先阅读“接管→执行技能→恢复”三个阶段，再对照 `tests/test_session.lua` 理解为什么失败要恢复、技能未结束不能重入。真实桥接 `pbz_bridge.lua` 仍禁用，F6／F10／F1–F4不是可用热键。

新增C++工具 `tools/offline_dump_stack.cpp` 用于本地崩溃诊断，不是UE4SS加载器；学习时可对照 `offline_dump_fixture.cpp` 看已知调用链是怎样被验证的。

## 下一关

必须先获得原版在保留存档隔离的环境中进入标题／主菜单的证据。下一轮应有新的、具体且可单独验证的兼容性假设；相同条件下反复启动不能替代定位。

随后依次验收：撤网后的离线冷启动、真实游戏存档隔离、通用UE4SS只读初始化、自写AOB／偏移、Boss对象与控制器、接管／恢复、单招技能和最终按键表。原版菜单没有通过时，不向正式目录部署DLL或猜测游戏偏移。

'''+cleanup
    (root/'04-当前结果与下一关.md').write_text(text,encoding='utf-8')
    print(json.dumps({'status_recorded':True,'report':common['latest_result_note'],'native_build_hashes_verified':True},ensure_ascii=False))


if __name__=='__main__':main()
