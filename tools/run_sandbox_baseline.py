"""用途：经过实测隔离后，做一次不加载Mod的PBZ限时诊断，前后校验正式文件。"""
from __future__ import annotations

from datetime import datetime
import hashlib
import ctypes
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import test_isolation as isolation
import preflight

ROOT = Path(__file__).resolve().parent.parent
GAME = Path(r"E:\SteamLibrary\steamapps\common\PBZ")
EXE = GAME / "steam/PBZ.exe"
EXPECTED = "17bf1e56c1a63f1dcde66d468b3f50fb308a8d29d2283ede7b275d953e47485d"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def formal_files():
    """用途：同时检查新增、删除和内容变化；只记录正式路径，跳过着色器缓存。"""
    roots = [GAME / "ProjectPBZ/Saved", Path(os.environ["LOCALAPPDATA"]) / "ProjectPBZ/Saved"]
    userdata = Path(r"D:\steam\userdata")
    if userdata.is_dir():
        roots.extend(child / "4115450" for child in userdata.iterdir() if child.is_dir() and (child / "4115450").is_dir())
    result = {}
    for root in roots:
        if not root.is_dir():
            continue
        for directory, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = [name for name in dirs if name.casefold() != "cache"
                       and not (Path(directory)/name).is_symlink() and not (Path(directory)/name).is_junction()]
            for name in files:
                path = Path(directory) / name
                if path.is_file() and not path.is_symlink():
                    result[str(path)] = {"bytes": path.stat().st_size, "sha256": digest(path)}
    return result


def box_pids(dll):
    """用途：只枚举专用箱，绝不按全机同名进程进行清理。"""
    f = dll.SbieApi_EnumProcessEx
    f.argtypes = [w.LPCWSTR, ctypes.c_ubyte, w.ULONG, ctypes.POINTER(w.ULONG), ctypes.POINTER(w.ULONG)]
    f.restype = w.LONG
    pids = (w.ULONG * 512)()
    # 官方SbieApi_EnumProcess宏使用pids[0]作数量；旧版DLL没有末尾可选count输出。
    status = f(isolation.BOX, False, 0xffffffff, pids, None)
    if status != 0:
        raise RuntimeError(f"Cannot enumerate dedicated box: {status}")
    if pids[0] > 511:
        raise RuntimeError("Invalid dedicated-box PID count")
    return list(pids)[1:pids[0] + 1]


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if "windowsapps" in sys.executable.casefold():
        raise RuntimeError("Use non-Store Python to avoid AppData redirection")
    if preflight.games_running():
        raise RuntimeError("PBZ already running; no launch or interference allowed")
    if box_pids(isolation.api()):
        raise RuntimeError("Dedicated box already in use; preserve existing session")
    if digest(EXE) != EXPECTED:
        raise RuntimeError("PBZ build changed; re-audit required")
    baseline = preflight.compare(ROOT / "evidence/latest-preflight.json")
    if baseline["original_files_changed_count"]:
        raise RuntimeError("Formal progress changed since snapshot; preserve it and re-audit first")
    check = subprocess.run([sys.executable, str(ROOT / "tools/test_isolation.py")], capture_output=True, timeout=70)
    isolation_result = json.loads((ROOT / "evidence/isolation-probe/latest-result.json").read_text(encoding="utf-8"))
    if check.returncode or isolation_result.get("passed") is not True:
        raise RuntimeError("Isolation probe failed; PBZ NOT launched")
    dll = isolation.api(); policy = isolation.check_policy(dll); container = isolation.get_root(dll)
    # 探针结束后Sandboxie RPC辅助进程可能仍在收尾；只清理本次探针的专用箱。
    if box_pids(dll):
        subprocess.run([str(isolation.SBIE/"Start.exe"), "/box:"+isolation.BOX, "/terminate"], timeout=12)
        for _ in range(30):
            if not box_pids(dll):break
            time.sleep(.2)
    if box_pids(dll):
        raise RuntimeError("Probe helper cleanup failed; game NOT launched")
    # 用途：当前阶段不允许先放任何加载器到正式安装或虚拟安装；只测原版入口。
    for parent in (EXE.parent, GAME / "steam"):
        for name in ("UE4SS.dll", "UE4SS-settings.ini", "dwmapi.dll", "xinput1_3.dll"):
            if (parent/name).exists():
                raise RuntimeError(f"Unexpected existing loader marker: {parent/name}")
    before = formal_files()
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
    work = ROOT / "evidence/sandbox-baseline" / run_id
    work.mkdir(parents=True)
    (work / "formal-before.json").write_text(json.dumps(before, ensure_ascii=False, indent=2), encoding="utf-8")
    logical_report = work / "guard-report.json"
    logical_log = work / "PBZ-baseline.log"
    command = [str(isolation.SBIE / "Start.exe"), "/box:" + isolation.BOX, "/silent", "/hide_window", "/wait",
               str(ROOT / "build/sandbox-guard/sandbox-guard.exe"), str(EXE), str(logical_report), str(logical_log)]
    report = {"time": datetime.now().astimezone().isoformat(), "run_id": run_id, "box": isolation.BOX,
              "container": str(container), "exe": str(EXE), "exe_sha256": EXPECTED,
              "isolation_probe": isolation_result["run_id"], "policy": policy, "launcher_command": command,
              "rendering_requested": "nullrhi", "loader_deployed": False, "boss_control_verified": False}
    print("Isolation verified; starting one guarded 45-second null-RHI baseline.", flush=True)
    try:
        launch = subprocess.run(command, capture_output=True, timeout=58)
        report["launcher_exit_code"] = launch.returncode
        physical_report = isolation.virtual_file(container, logical_report)
        physical_log = isolation.virtual_file(container, logical_log)
        if physical_report.is_file():
            report["guard"] = json.loads(physical_report.read_text(encoding="utf-8"))
        else:
            report["error"] = "No guard report; game execution not attested"
        if physical_log.is_file():
            (work / "PBZ-baseline.log").write_bytes(physical_log.read_bytes())
            report["log"] = str(work / "PBZ-baseline.log")
        else:
            report["log"] = None
    except subprocess.TimeoutExpired:
        report["error"] = "Guard timeout; terminating ONLY PBZBossLab"
        subprocess.run([str(isolation.SBIE/"Start.exe"), "/box:"+isolation.BOX, "/terminate"], timeout=12)
    finally:
        # 作业终止在实际环境中未必能清掉沙盒子进程；使用官方专用箱终止并回读。
        # 启动前已确认此箱无其他会话，因此这里不会终止用户原先的任何游戏。
        residue = box_pids(dll)
        report["residual_box_pids_before_cleanup"] = residue
        # 即使枚举为空仍执行箱级清理，避免只凭枚举结果遗漏仍在终止中的子进程。
        subprocess.run([str(isolation.SBIE/"Start.exe"), "/box:"+isolation.BOX, "/terminate"], timeout=12)
        for _ in range(40):
            if not box_pids(dll) and not preflight.games_running():
                break
            time.sleep(0.2)
        report["residual_box_pids_after_cleanup"] = box_pids(dll)
        after = formal_files()
        differences = [name for name in sorted(set(before) | set(after)) if before.get(name) != after.get(name)]
        report["formal_file_count_before"] = len(before)
        report["formal_file_count_after"] = len(after)
        report["formal_files_changed"] = differences
        report["formal_files_unchanged"] = not differences
        report["old_snapshot_compare"] = preflight.compare(ROOT / "evidence/latest-preflight.json")
        report["game_exe_unchanged"] = digest(EXE) == EXPECTED
        report["remaining_pbz_processes"] = preflight.games_running()
        report["native_initialization_verified"] = False
        text = json.dumps(report, ensure_ascii=False, indent=2)
        (work / "host-result.json").write_text(text, encoding="utf-8")
        (ROOT / "evidence/sandbox-baseline/latest-result.json").write_text(text, encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    # 成功的原版退出也不代表游戏初始化/UE4SS适配/存档可用，结果需人工查看日志证据。
    return 0 if report.get("formal_files_unchanged") and report.get("game_exe_unchanged") and not report.get("remaining_pbz_processes") else 1


if __name__ == "__main__":
    raise SystemExit(main())
