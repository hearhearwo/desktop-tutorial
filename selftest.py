# -*- coding: utf-8 -*-
"""环境自检：命令行执行  python selftest.py

逐项检查运行环境：Python / Tk、DPI、透明层、emoji 字体、全局钩子、
音效、图标、配置、托盘、设置窗口。程序跑不起来时先看这里的输出。
"""
from __future__ import annotations

import ctypes
import os
import queue
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = []


def check(title: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((title, bool(ok), detail))
    print("[%s] %-22s %s" % ("OK " if ok else "!! ", title, detail))
    return bool(ok)


def main() -> int:
    print("=" * 62)
    print(" 桌面表情 Ping 环境自检")
    print("=" * 62)
    print("Python 版本 : %s" % sys.version.replace("\n", " "))
    print("解释器      : %s" % sys.executable)
    print("平台        : %s" % sys.platform)

    try:
        import winapi
    except Exception as exc:
        check("导入 winapi", False, str(exc))
        return 1

    check("DPI 感知", winapi.enable_dpi_awareness(),
          "多显示器/缩放坐标才不会偏")
    vx, vy, vw, vh = winapi.virtual_screen()
    print("虚拟桌面    : %d,%d %dx%d" % (vx, vy, vw, vh))

    try:
        import tkinter as tk
    except ImportError as exc:
        check("导入 tkinter", False, str(exc))
        return 1

    from tkinter import font as tkfont

    root = tk.Tk()
    root.withdraw()
    print("Tk 版本     : %s" % root.tk.call("info", "patchlevel"))

    families = set(tkfont.families(root))
    check("emoji 字体", "Segoe UI Emoji" in families, "Segoe UI Emoji")
    check("中文字体", "Microsoft YaHei UI" in families, "Microsoft YaHei UI")

    # ---- 透明层 ----
    from overlay import probe_layer_mode
    mode = probe_layer_mode(root, "#FF00FF")
    detail = {"alpha+key": "色键透明 + 淡出都可用（最佳）",
              "key": "只有色键透明，表情会到点直接消失（没有淡出）",
              "none": "透明层不可用，表情会是不透明方块！"}.get(mode, mode)
    check("透明层", mode != "none", detail)

    # ---- 配置 ----
    try:
        import config as config_mod
        cfg = config_mod.Config()
        cfg.validate()
        item = config_mod.normalize_item({"image": "a.png", "sound": "b.wav", "size": 120})
        ok = (set(item) == {"image", "sound", "size", "label"} and item["size"] == 120)
        folder = config_mod.assets_dir()
        check("配置结构", ok and os.path.isdir(folder),
              "表情项 = 图片 + 音效 + 大小；素材目录 %s" % folder)
    except Exception as exc:
        check("配置结构", False, str(exc))

    # ---- 全局钩子 ----
    try:
        from hotkeys import Hotkey
        from input_monitor import InputMonitor
        hk = Hotkey.parse("ctrl+alt+q")
        monitor = InputMonitor(hk, queue.Queue())
        ok = monitor.start()
        monitor.stop()
        check("全局钩子", ok, monitor.error or "键盘/鼠标低级钩子安装成功")
    except Exception as exc:
        check("全局钩子", False, str(exc))

    # ---- 音效 ----
    try:
        import audio
        import struct
        import tempfile
        import wave

        # 造一段 0.2 秒的静音 WAV（自检用，不出声）验证播放通路
        silent = os.path.join(tempfile.gettempdir(), "deping_selftest.wav")
        with wave.open(silent, "wb") as fh:
            fh.setnchannels(1)
            fh.setsampwidth(2)
            fh.setframerate(44100)
            fh.writeframes(struct.pack("<%dh" % 8820, *([0] * 8820)))
        err = audio.play(silent, 0.5)
        check("音效（WAV 播放）", err == "",
              "winsound 异步播放 OK（%d 字节的测试文件）" % os.path.getsize(silent))
        check("音效（静音/找不到文件）",
              audio.play("none") == "" and audio.play("不存在的文件.wav") != "",
              "留空/none 不出声；文件不存在会返回错误文字")
        check("音效（MP3 走 MCI）", True,
              "本机 MCI 可用" if audio.mci_available() else "本机 MCI 不可用（MP3 会失败）")
        try:
            os.remove(silent)
        except OSError:
            pass
    except Exception as exc:
        check("音效", False, str(exc))

    # ---- 图标 ----
    try:
        import iconasset
        ico = iconasset.ensure_icon(os.path.join(HERE, "app.ico"))
        user32 = ctypes.WinDLL("user32")
        user32.LoadImageW.restype = ctypes.c_void_p
        handle = user32.LoadImageW(None, ico, 1, 16, 16, 0x00000010)
        check("程序图标", bool(handle),
              "%s（%d KB，16/32/48 三个尺寸）" % (os.path.basename(ico), os.path.getsize(ico) // 1024))
    except Exception as exc:
        check("程序图标", False, str(exc))

    # ---- 托盘 ----
    try:
        import tray
        check("托盘结构", ctypes.sizeof(tray._NOTIFYICONDATAW) in (956, 976),
              "NOTIFYICONDATAW=%d 字节" % ctypes.sizeof(tray._NOTIFYICONDATAW))
        t = tray.TrayIcon(queue.Queue(), "自检", os.path.join(HERE, "app.ico"))
        started = t.start()
        t.stop()
        check("托盘图标", started,
              "已显示" if started else ("%s（没有托盘的环境，比如远程/沙箱桌面，属正常）"
                                        % (t.error or "不可用")))
    except Exception as exc:
        check("托盘图标", False, str(exc))

    # ---- 设置窗口 ----
    try:
        import config as config_mod
        from settings_ui import SettingsWindow

        class _StubApp:
            def __init__(self, config):
                self.root = root
                self.cfg = config
                self.icon_path = os.path.join(HERE, "app.ico")
                self.recorded = None

            def apply_settings(self, config):
                self.recorded = config

            def test_ping(self, item, config=None):
                pass

            def start_hotkey_record(self, key):
                self.recorded = key

            def settings_closed(self):
                pass

        window = SettingsWindow(_StubApp(config_mod.Config()))
        window.top.update_idletasks()
        rows = len(window.tree.get_children())
        hint = window.var_status.get()
        window.top.destroy()
        check("设置窗口", rows == 0, "空列表也能正常打开（空状态提示：%s）" % hint)
    except Exception as exc:
        check("设置窗口", False, "%s: %s" % (type(exc).__name__, exc))

    root.destroy()

    failed = [title for title, ok, _ in RESULTS if not ok]
    print("=" * 62)
    if failed:
        print(" 有 %d 项需要注意：%s" % (len(failed), "、".join(failed)))
        print(" 上面标 !! 的行有说明；托盘的项在远程/沙箱桌面上本来就会失败。")
    else:
        print(" 全部通过 ✓  直接运行 main.py 或双击 启动.bat")
    print("=" * 62)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
