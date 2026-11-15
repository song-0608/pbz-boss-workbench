"""PBZ Boss研究的只读前置检查：记录程序、备份存档；不启动或修改游戏。"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import mmap
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


HOME = Path(__file__).resolve().parent.parent
APPID = "4115450"


def digest(path: Path) -> str:
    """用途：逐块读取并生成文件指纹，不改变文件内容。"""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def games_running() -> list[dict]:
    """用途：仅检查PBZ进程，运行中就拒绝创建可能不一致的存档快照。"""
    code = "Get-CimInstance Win32_Process -Filter \"Name='PBZ.exe' OR Name='PBZ-Win64-Shipping.exe' OR Name='PhantomBladeZero.exe'\" | Select-Object ProcessId,Name,ExecutablePath | ConvertTo-Json -Compress"
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", code],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25)
    if result.returncode:
        raise RuntimeError("无法确认PBZ是否运行，停止存档备份；未触碰游戏。")
    text = result.stdout.strip()
    if not text:
        return []
    rows = json.loads(text)
    return rows if isinstance(rows, list) else [rows]


def pe_information(path: Path) -> dict:
    """用途：调用现有离线PE解析器识别程序区段，记录版本字串线索而不执行程序。"""
    sys.path.insert(0, str(HOME.parent / "tools"))
    from aob_lab import PE
    with path.open("rb") as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
        pe = PE(data)
        evidence = []
        for text in ("5.7.4", "++UE5+Release-5.7", "CL-302256_JKS-17280", "SaveToUserDir", "UserDir=", "SavedDir="):
            for encoding in ("ascii", "utf-16le"):
                token = text.encode(encoding)
                position = data.find(token)
                if position >= 0:
                    evidence.append({"text": text, "encoding": encoding, "first_file_offset": position,
                                     "meaning": "字节字串线索；不能证明此选项被游戏采用，或完整引擎版本"})
        return {"architecture": "x64 PE32+", "image_size": pe.image_size,
                "sections": pe.sections, "string_evidence": evidence}


def snapshot(source: Path, target: Path) -> dict:
    """用途：读取原件、复制到D盘备份，再读回双方核对内容和大小。"""
    stat_before = source.stat()
    old_hash = digest(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    after = source.stat()
    if (stat_before.st_size, stat_before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError("备份过程中原存档发生变化；保留备份，但不能视为一致快照。")
    if digest(source) != old_hash or digest(target) != old_hash:
        raise RuntimeError("原件/备份校验不同，不得继续实机实验。")
    return {"source": str(source), "backup": str(target), "bytes": after.st_size,
            "sha256": old_hash, "mtime_ns": after.st_mtime_ns, "copy_verified": True}


def perform(game_root: Path, action: str) -> dict:
    """用途：将检查和快照全部写到研究目录；不提供启动、部署、恢复或网络改动接口。"""
    game_root = game_root.resolve(strict=True)
    candidates = [game_root / "steam" / "PBZ.exe", game_root / "platform" / "steam" / "PBZ.exe"]
    if not all(path.is_file() for path in candidates):
        raise RuntimeError("目录不符合当前已核对的安装布局，停止；不尝试其他程序。")
    running = games_running()
    if running:
        raise RuntimeError("检测到PBZ运行中。为避免干扰当前游戏，不启动、不注入、不备份；请先在方便时正常退出。")
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
    output = HOME / "evidence" / stamp
    output.mkdir(parents=True)
    steam_root = Path(r"D:\steam")
    manifest = game_root.parents[1] / f"appmanifest_{APPID}.acf"
    fields = {}
    if manifest.is_file():
        fields = dict(re.findall(r'"([^"\r\n]+)"\s*"([^"\r\n]*)"', manifest.read_text(encoding="utf-8-sig")))
    files = [{"path": str(path), "bytes": path.stat().st_size, "sha256": digest(path),
              "pe": pe_information(path)} for path in candidates]
    protected_sources: list[tuple[Path, Path]] = []
    saved = game_root / "ProjectPBZ" / "Saved"
    for path in saved.rglob("*"):
        if path.is_file() and not path.is_symlink() and "Cache" not in path.relative_to(saved).parts:
            protected_sources.append((path, Path("game_saved") / path.relative_to(saved)))
    local = Path(os.environ["LOCALAPPDATA"]) / "ProjectPBZ" / "Saved" / "Config"
    if local.is_dir():
        for path in local.rglob("*"):
            if path.is_file() and not path.is_symlink():
                protected_sources.append((path, Path("local_config") / path.relative_to(local)))
    # 用途：只备份本App的云同步元数据，不读取其他游戏或账号凭据。
    userdata = steam_root / "userdata"
    if userdata.is_dir():
        for directory in userdata.iterdir():
            app = directory / APPID
            if not app.is_dir():
                continue
            for path in app.rglob("*"):
                if path.is_file() and not path.is_symlink():
                    protected_sources.append((path, Path("steam_app_metadata") / directory.name / path.relative_to(app)))
    bytes_to_backup = sum(path.stat().st_size for path, _ in protected_sources)
    if bytes_to_backup > 200 * 1024 * 1024:
        raise RuntimeError("待备份文件超过200MB，请先核对范围；未修改游戏。")
    sources = []
    for path, relative in protected_sources:
        if action == "snapshot":
            row = snapshot(path, output / "backup" / relative)
        else:
            row = {"source": str(path), "bytes": path.stat().st_size, "sha256": digest(path), "copy_verified": False}
        sources.append(row)
    # 用途：备份完成后检查整个集合及内容未变化；不把一次读取当作云同步已经停止。
    changed = [row["source"] for row in sources if not Path(row["source"]).is_file() or digest(Path(row["source"])) != row["sha256"]]
    if games_running() or changed:
        raise RuntimeError("检查期间PBZ启动或原文件变化；保留报告前的副本，但不得据此实机修改。")
    total_install_bytes = 0
    file_count = 0
    loader_markers = []
    for directory, dirs, names in os.walk(game_root, followlinks=False):
        dirs[:] = [name for name in dirs if not (Path(directory)/name).is_junction() and not (Path(directory)/name).is_symlink()]
        for name in names:
            path = Path(directory) / name
            if path.is_symlink():
                continue
            file_count += 1
            total_install_bytes += path.stat().st_size
            if name.lower() in {"ue4ss.dll", "ue4ss-settings.ini"}:
                loader_markers.append(str(path))
    report = {"checked_at": datetime.now().astimezone().isoformat(), "action": action,
              "game_root": str(game_root), "steam_manifest": str(manifest),
              "app_id": fields.get("appid"), "build_id": fields.get("buildid"), "state_flags": fields.get("StateFlags"),
              "program_candidates": files,
              "runtime_candidate": str(candidates[1]),
              "runtime_candidate_basis": "目录/文件大小及版本资源线索；尚未通过启动或模块观察确认",
              "save_root_found": str(saved), "local_config_root_found": str(local),
              "protected_files": sources, "protected_file_count": len(sources),
              "snapshot_bytes": bytes_to_backup, "original_file_contents_unchanged": True,
              "snapshot_copy_verified": action == "snapshot", "cloud_sync_record_present": any("steam_app_metadata" in str(relative) for _,relative in protected_sources),
              "install_file_count": file_count, "install_total_bytes": total_install_bytes,
              "d_drive_free_bytes": shutil.disk_usage(HOME).free,
              "existing_ue4ss_markers": loader_markers,
              "game_launched": False, "loader_deployed": False, "network_settings_changed": False,
              "offline_execution_verified": False, "save_redirection_verified": False, "boss_control_verified": False,
              "runtime_testing_allowed": False,
              "blockers": ["离线执行与目标进程网络隔离尚未验证", "游戏自定义存档重定向尚未验证；不能假定-UserDir有效", "尚未完成当前构建的通用UE4SS只读初始化", "Boss、技能和镜头对象尚无实机证据"],
              "report": str(output / "preflight.json")}
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    (output / "preflight.json").write_text(text, encoding="utf-8")
    (HOME / "evidence" / "latest-preflight.json").write_text(text, encoding="utf-8")
    return report


def compare(report: Path) -> dict:
    """用途：重新检查正式文件与备份，不自动恢复、不覆盖正式进度或云同步缓存。"""
    original = json.loads(report.read_text(encoding="utf-8"))
    changes = []
    for row in original["protected_files"]:
        path = Path(row["source"])
        if not path.is_file() or digest(path) != row["sha256"]:
            changes.append(row["source"])
        if row.get("backup"):
            backup = Path(row["backup"])
            if not backup.is_file() or digest(backup) != row["sha256"]:
                raise RuntimeError("备份校验失败：" + str(backup))
    return {"baseline": str(report), "original_files_changed_count": len(changes),
            "changed_files": changes, "backup_contents_verified": True,
            "meaning": "若之后正常玩游戏，原文件变化可能是正常进度；本工具不自动回档。"}


def main():
    """用途：只允许审计、快照、对比三项操作，实机部署必须另行验收。"""
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("audit", "snapshot", "compare"))
    parser.add_argument("--game-root", type=Path, default=Path(r"E:\SteamLibrary\steamapps\common\PBZ"))
    args = parser.parse_args()
    report = compare(HOME / "evidence" / "latest-preflight.json") if args.action == "compare" else perform(args.game_root,args.action)
    keys = ("action", "app_id", "build_id", "protected_file_count", "snapshot_bytes", "snapshot_copy_verified", "original_file_contents_unchanged", "install_total_bytes", "d_drive_free_bytes", "game_launched", "loader_deployed", "runtime_testing_allowed", "original_files_changed_count", "backup_contents_verified", "report")
    print(json.dumps({key:report[key] for key in keys if key in report}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
