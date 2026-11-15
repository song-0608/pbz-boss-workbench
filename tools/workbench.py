"""用途：初学者统一入口，只查状态、运行模拟测试或打开资料，不启动游戏。"""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parent.parent


def show_status():
    status=json.loads((ROOT/'项目状态.json').read_text(encoding='utf-8'))
    # 用途：看门狗在对话结束后仍可能更新准备状态，以实时租约为准，不显示过期的“正在认证”。
    lease_path=status.get('authentication_preparation_state')
    if lease_path and Path(lease_path).is_file():
        lease=json.loads(Path(lease_path).read_text(encoding='utf-8'))
        if lease.get('restored') and status.get('authentication_preparation_active'):
            status['status_summary']='本人登录准备已关闭并恢复离线规则；仍需验证合法离线会话和游戏菜单。'
        elif not lease.get('restored'):
            print('本人登录准备截止：'+lease['deadline_at'])
    print('\n实际状态：'+status['status_summary'])
    print('当前阻塞：'+status['blocked_reason'])
    if status.get('protected_interactive_controls_verified'):
        print('Boss控制：阿花操控、技能和目标切换已有实机证据。双击 开始阿花训练.cmd 查看本轮实际技能键；完整Boss系统仍在开发，旧归档不代表当前源码。')
    elif status.get('boss_minimal_control_loop_verified'):
        print('Boss控制：阿花最小控制链已实机通过；'+('第三人称镜头、F10及首招中断通过。' if status.get('boss_camera_visual_verified') else '镜头待修。')+'正式入口禁用，限时实验键位不作用于正常游戏。')
    else:print('Boss控制：尚未接通真实游戏，拟定按键无效。')
    if status.get('next_action'):print('下一关：'+status['next_action'])
    if status.get('validation_workflow'):
        print('排错节奏：一次会话批量采集，游戏外集中修复，再按受影响范围统一复测；不逐项重启。')


def main():
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    if len(sys.argv)>1 and sys.argv[1]=='--status':
        show_status();return
    while True:
        print('\n影之刃零研究工作台（不会启动游戏）')
        print('1 查看实际状态\n2 运行会话测试及模拟\n3 打开当前结果与下一关\n4 打开控制源码文件夹\n5 只读核对历史备份（不回档）\n6 打开阿花最新实测说明\n7 查看历史37项能力样本（不等于37招可玩）\n8 查看最新镜头实测截图\n9 运行控制、输入和观测本地回归（不启动游戏）\nP 打开阿花离线训练窗口（点击按钮才启动研究游戏）\nH 查看阿花四键操作卡\n0 退出')
        choice=input('输入数字后回车：').strip()
        if choice=='0':return
        if choice=='1':show_status()
        elif choice=='2':
            exe=ROOT.parent/'build/lua-harness/Release/lua-lab.exe'
            if not exe.is_file():print('找不到本机Lua练习运行器：'+str(exe));continue
            for script in ('test_session.lua','simulate_control_flow.lua'):
                result=subprocess.run([str(exe),str(ROOT/'tests'/script),str(ROOT)],capture_output=True)
                print(result.stdout.decode('utf-8',errors='replace'));print('退出码：',result.returncode)
                if result.stderr:print(result.stderr.decode('utf-8',errors='replace'))
                if result.returncode:break
            print('这是模拟逻辑测试，不是Boss已经能操控。')
        elif choice=='3':os.startfile(ROOT/'04-当前结果与下一关.md')
        elif choice=='4':os.startfile(ROOT/'mod/PBZBossControl/Scripts')
        elif choice=='5':
            # 用途：仅比较原37个对象，不恢复、不覆盖任何文件。
            import preflight
            print(json.dumps(preflight.compare(ROOT/'evidence/latest-preflight.json'),ensure_ascii=False,indent=2))
        elif choice=='6':
            status=json.loads((ROOT/'项目状态.json').read_text(encoding='utf-8'))
            os.startfile(Path(status.get('latest_result_note',ROOT/'28-阿花定位与Lua观测实测.md')))
        elif choice=='7':
            os.startfile(ROOT/'32-阿花能力清单-非全部可玩.csv')
        elif choice=='8':
            status=json.loads((ROOT/'项目状态.json').read_text(encoding='utf-8'))
            os.startfile(Path(status.get('latest_camera_screenshot',ROOT/'evidence/official-validation/20261113-101145/first-interactive-ahua-preview.png')))
        elif choice=='9':
            result=subprocess.run([sys.executable,str(ROOT/'tools/run_observer_checks.py')],capture_output=True)
            print(result.stdout.decode('utf-8',errors='replace'));print(result.stderr.decode('utf-8',errors='replace'))
            print('退出码：',result.returncode,'；这是本地夹具，不是Boss控制验收。')
        elif choice.upper()=='P':subprocess.Popen([sys.executable,str(ROOT/'tools/ahua_practice_window.py')])
        elif choice.upper()=='H':os.startfile(ROOT/'37-阿花训练版操作卡.md')
        else:print('请输入0到9，或P/H。')


if __name__=='__main__':main()
