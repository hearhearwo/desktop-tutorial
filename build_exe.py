# -*- coding: utf-8 -*-
"""打包成单文件 exe。

用法：
    python build_exe.py          （需要先 pip install pyinstaller）
产物：
    dist/桌面表情Ping.exe        双击即用，配置与「表情素材」会生成在 exe 旁边

为什么脚本里要解包 Tcl/Tk：
    Python 3.12+ 的官方 Windows 版把 Tcl/Tk 的脚本库放进了 zip
    （解释器里看到的是 //zipfs:/lib/tcl/tcl_library 这种路径），
    PyInstaller 收集不到这些文件，打出来的 exe 会报
    “Cannot find a usable init.tcl”。
    所以这里先把 zip 解成普通目录，再用 --add-data 塞进去，
    配合 PyInstaller 运行时会自动设置的 _tcl_data / _tk_data 生效。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "build_assets")
NAME = "桌面表情Ping"


def log(message: str) -> None:
    print("[打包] %s" % message)


def find_tcl_root() -> str:
    """找到 Python 自带的 tcl 目录。"""
    candidates = [
        os.path.join(os.path.dirname(sys.executable), "tcl"),
        os.path.join(sys.prefix, "tcl"),
        os.path.join(sys.base_prefix, "tcl"),
    ]
    for path in candidates:
        if os.path.isdir(path):
            return path
    return ""


def extract_zip(zip_path: str, inner_prefix: str, dest: str) -> int:
    """把 zip 里 inner_prefix/ 下的内容解包并平铺到 dest。"""
    count = 0
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            name = info.filename
            if info.is_dir() or not name.startswith(inner_prefix):
                continue
            relative = name[len(inner_prefix):].lstrip("/")
            if not relative:
                continue
            target = os.path.join(dest, relative.replace("/", os.sep))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with archive.open(info) as source, open(target, "wb") as out:
                shutil.copyfileobj(source, out)
            count += 1
    return count


def prepare_assets() -> list:
    """准备 Tcl/Tk 数据目录，返回 PyInstaller 的 --add-data 参数。"""
    tcl_root = find_tcl_root()
    if not tcl_root:
        log("找不到 Python 的 tcl 目录，跳过（如果 exe 报 init.tcl 错误，请检查这一步）")
        return []

    shutil.rmtree(ASSETS, ignore_errors=True)
    tcl_dest = os.path.join(ASSETS, "_tcl_data")
    tk_dest = os.path.join(ASSETS, "_tk_data")
    pkg_dest = os.path.join(ASSETS, "_tcl_pkgs")
    os.makedirs(tcl_dest)
    os.makedirs(tk_dest)
    os.makedirs(pkg_dest)

    zips = {name.lower(): os.path.join(tcl_root, name)
            for name in os.listdir(tcl_root) if name.lower().endswith(".zip")}
    tcl_zip = next((path for key, path in zips.items() if "tcl" in key), "")
    tk_zip = next((path for key, path in zips.items() if "tk" in key), "")

    if tcl_zip:
        count = extract_zip(tcl_zip, "tcl_library", tcl_dest)
        log("解出 Tcl 脚本库 %d 个文件（%s）" % (count, os.path.basename(tcl_zip)))
    if tk_zip:
        count = extract_zip(tk_zip, "tk_library", tk_dest)
        log("解出 Tk 脚本库 %d 个文件（%s）" % (count, os.path.basename(tk_zip)))
    if not (tcl_zip and tk_zip):
        # 老式布局：tcl/tcl8.6、tcl/tk8.6 直接就是目录
        for name, dest in (("tcl8.6", tcl_dest), ("tcl9.0", tcl_dest),
                           ("tk8.6", tk_dest), ("tk9.0", tk_dest)):
            source = os.path.join(tcl_root, name)
            if os.path.isdir(source) and os.path.isfile(os.path.join(source, "init.tcl")):
                shutil.rmtree(dest, ignore_errors=True)
                shutil.copytree(source, dest)
                log("复制目录 %s" % name)

    for name in sorted(os.listdir(tcl_root)):
        if name.startswith(("dde", "registry", "tdbc", "sqlite")):
            source = os.path.join(tcl_root, name)
            if os.path.isdir(source):
                shutil.copytree(source, os.path.join(pkg_dest, name), dirs_exist_ok=True)
                log("带上 Tcl 扩展包 %s" % name)

    return ["--add-data", "%s;_tcl_data" % tcl_dest,
            "--add-data", "%s;_tk_data" % tk_dest,
            "--add-data", "%s;_tcl_pkgs" % pkg_dest]


def ensure_icon() -> str:
    icon = os.path.join(HERE, "app.ico")
    if not os.path.isfile(icon):
        import iconasset
        iconasset.ensure_icon(icon)
        log("生成图标 app.ico")
    return icon


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        log("没装 PyInstaller，先执行：pip install pyinstaller")
        return 2

    icon = ensure_icon()
    data_args = prepare_assets()
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
               "--onefile", "--noconsole", "--name", NAME, "--icon", icon,
               "--hidden-import", "selftest"] + data_args + ["main.py"]
    log("开始打包：%s" % NAME)
    code = subprocess.call(command, cwd=HERE)
    if code != 0:
        log("打包失败（退出码 %d）" % code)
        return code
    exe = os.path.join(HERE, "dist", NAME + ".exe")
    size = os.path.getsize(exe) / 1048576.0 if os.path.isfile(exe) else 0
    log("完成：%s（%.1f MB）" % (exe, size))
    log("可以双击运行；配置和「表情素材」会生成在 exe 同目录。")
    log("自检：%s --selftest  （结果写在 exe 旁的 selftest-report.txt）" % os.path.basename(exe))
    return 0


if __name__ == "__main__":
    sys.exit(main())
