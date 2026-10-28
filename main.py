# -*- coding: utf-8 -*-
"""桌面表情 Ping —— Win11 置顶悬浮层小工具（Python + Win32 API）。

玩法：
    1. 双击「启动.bat」或执行 python main.py
    2. 按 Ctrl+Alt+Q 进入「待放置」，鼠标旁会出现提示条
    3. 左键点桌面任意位置 → 该处弹出表情 + 音效，3 秒后淡出
       滚轮切换表情；右键/Esc 取消
    4. Ctrl+Alt+S 打开设置界面：加符号、加图片、给每个表情配音效
       托盘图标右键也有同样的菜单（左键/双击直接打开设置）

配置见同目录 config.json。
"""
from __future__ import annotations

import argparse
import os
import queue
import sys
import time

MUTEX_NAME = "Local\\DesktopEmojiPing_SingleInstance"
_ERROR_BOX_BUDGET = 3  # 避免同一个错误反复弹框


def prepare_frozen_runtime() -> None:
    """打包成 exe 后需要额外告诉 Tcl 去哪里找扩展包（dde / registry）。

    Tcl/Tk 的脚本库由 PyInstaller 的 _tcl_data / _tk_data 机制处理，
    这两个扩展包是我们自己塞进 exe 的，所以用 TCLLIBPATH 指一下。
    """
    if not getattr(sys, "frozen", False):
        return
    base = getattr(sys, "_MEIPASS", "")
    packages = os.path.join(base, "_tcl_pkgs")
    if os.path.isdir(packages):
        os.environ.setdefault("TCLLIBPATH", packages.replace("\\", "/"))


def _report_error(title: str, exc_type, exc, tb) -> None:
    """把异常写到控制台并弹消息框（pythonw 启动时没有控制台）。"""
    global _ERROR_BOX_BUDGET
    import traceback
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    try:
        print(text)
    except Exception:
        pass
    if _ERROR_BOX_BUDGET <= 0:
        return
    _ERROR_BOX_BUDGET -= 1
    try:
        import winapi
        winapi.message_box(text[-1600:], title)
    except Exception:
        pass


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="桌面表情 Ping",
        description="按下全局快捷键后，在鼠标点击处绘制表情、播放音效并自动淡出。",
    )
    parser.add_argument("-c", "--config", default=None, help="配置文件路径（默认：同目录 config.json）")
    parser.add_argument("-i", "--image", default=None,
                        help="本次启动额外加入一个图片/动图（会复制进「表情素材」）")
    parser.add_argument("--hotkey", default=None, help="临时覆盖快捷键，例如 ctrl+alt+q")
    parser.add_argument("--mode", choices=("toggle", "hold"), default=None,
                        help="toggle=按一下进入待放置；hold=按住快捷键期间可连续点击")
    parser.add_argument("--settings", action="store_true", help="启动时直接打开设置窗口")
    parser.add_argument("--no-settings", action="store_true", help="启动时不打开设置窗口（只在托盘待命）")
    parser.add_argument("--no-tray", action="store_true", help="本次启动不显示托盘图标")
    parser.add_argument("--list-items", action="store_true", help="列出配置里的表情后退出")
    parser.add_argument("--selftest", action="store_true",
                        help="跑一遍环境自检并退出（结果写到程序目录的 selftest-report.txt）")
    parser.add_argument("--allow-multiple", action="store_true", help="允许多开（默认单实例）")
    return parser.parse_args(argv)


def default_config_path() -> str:
    import config as config_mod

    return os.path.join(config_mod.app_dir(), "config.json")


def main(argv=None) -> int:
    prepare_frozen_runtime()
    args = parse_args(argv)
    sys.excepthook = lambda exc_type, exc, tb: _report_error(
        "桌面表情 Ping 出错", exc_type, exc, tb)

    if args.selftest:
        return run_selftest()

    # 必须在创建任何窗口之前开启 DPI 感知
    import winapi
    winapi.enable_dpi_awareness()

    import config as config_mod
    import iconasset
    import audio

    here = config_mod.app_dir()
    cfg_path = os.path.abspath(args.config or default_config_path())
    cfg = config_mod.Config.load(cfg_path)
    config_mod.assets_dir()          # 先把「表情素材」文件夹建出来，方便往里丢图片
    if args.hotkey:
        cfg.hotkey = args.hotkey
    if args.mode:
        cfg.hotkey_mode = args.mode
    if args.image:
        cfg.add_item({"image": config_mod.import_asset(args.image), "sound": ""})

    if args.list_items:
        if not cfg.items:
            print("（还没有表情）素材目录：%s" % config_mod.assets_dir())
        for index, item in enumerate(cfg.items):
            mark = " *" if index == cfg.current_index else ""
            ready = "OK" if config_mod.item_ready(item) else "缺图片"
            print("%2d  %-24s 音效=%-16s %s%s"
                  % (index, config_mod.item_text(item),
                     audio.describe(item.get("sound"), cfg.default_sound), ready, mark))
        return 0

    if not args.allow_multiple and not winapi.acquire_single_instance(MUTEX_NAME):
        from tray import request_open_settings
        request_open_settings()          # 让已在运行的实例把设置窗口弹出来
        msg = ("程序已经在运行了，已经请它把设置窗口打开。\n\n"
               "如果没反应：右击托盘图标，或按 Ctrl+Alt+S；"
               "要完全退出可以在托盘菜单里选「退出」。")
        print(msg)
        winapi.message_box(msg, "桌面表情 Ping", winapi.MB_ICONINFORMATION)
        return 0

    try:
        import tkinter as tk
    except ImportError as exc:
        msg = ("当前 Python 没有 tkinter，无法运行。\n\n"
               "请到 python.org 安装官方 Python（安装时勾选 tcl/tk）。\n\n%s" % exc)
        print(msg)
        winapi.message_box(msg)
        return 2

    try:
        icon_path = iconasset.ensure_icon(os.path.join(here, "app.ico"))
    except Exception as exc:
        print("[图标] 生成失败，用系统默认图标：%s" % exc)
        icon_path = None

    root = tk.Tk()
    root.withdraw()
    if icon_path:
        try:
            root.iconbitmap(icon_path)
        except tk.TclError:
            pass

    try:
        app = App(root, cfg, cfg_path, icon_path, use_tray=not args.no_tray)
    except Exception as exc:
        msg = "启动失败：%s" % exc
        print(msg)
        winapi.message_box(msg)
        try:
            root.destroy()
        except Exception:
            pass
        return 3

    if not args.no_settings and (args.settings or cfg.open_settings_on_start):
        try:
            app.open_settings()
        except Exception as exc:
            print("[设置] 打不开设置窗口：%s" % exc)
    return app.run()


def run_selftest() -> int:
    """环境自检：结果打印到控制台，同时写到程序目录，方便 exe 版排查。"""
    import contextlib
    import io

    import config as config_mod
    import selftest as selftest_mod

    buffer = io.StringIO()
    code = 1
    try:
        with contextlib.redirect_stdout(buffer):
            code = selftest_mod.main()
    except Exception as exc:
        buffer.write("\n自检脚本自身出错：%r\n" % (exc,))
    report = buffer.getvalue()
    try:
        print(report)
    except Exception:
        pass
    try:
        path = os.path.join(config_mod.app_dir(), "selftest-report.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(report)
        print("自检结果已写入：%s" % path)
    except OSError:
        pass
    return code


class App:
    """把全局监听、悬浮层、音效、托盘、设置窗口粘在一起。"""

    POLL_MS = 15

    def __init__(self, root, cfg, cfg_path: str, icon_path: str | None,
                 use_tray: bool = True):
        import audio
        from overlay import FloatingLayer
        from tray import TrayIcon

        self.audio = audio
        self.root = root
        self.cfg = cfg
        self.cfg_path = cfg_path
        self.icon_path = icon_path
        self.events: "queue.Queue" = queue.Queue()
        self._stopped = False
        self._paused = False
        self._recording_key = None
        self._settings_window = None
        self._last_sound_ms = 0.0
        self._pump_timer = None

        root.report_callback_exception = self._on_callback_error

        self.layer = FloatingLayer(root, cfg)
        self.tray = TrayIcon(self.events, tooltip=self._tooltip(), icon_path=icon_path)
        self._use_tray = bool(use_tray and cfg.enable_tray)
        self.monitor = None
        self._start_monitor()

    # ------------------------------------------------------------------
    # 启动 / 主循环
    # ------------------------------------------------------------------
    def _start_monitor(self) -> None:
        from input_monitor import InputMonitor

        hotkey = self._hotkey(self.cfg.hotkey, required=True)
        monitor = InputMonitor(
            hotkey,
            self.events,
            mode=self.cfg.hotkey_mode,
            exit_hotkey=self._hotkey(self.cfg.exit_hotkey),
            settings_hotkey=self._hotkey(self.cfg.settings_hotkey),
            mute_hotkey=self._hotkey(self.cfg.mute_hotkey),
            consume_click=self.cfg.consume_click,
            stay_armed=self.cfg.stay_armed,
            swallow_hotkey=self.cfg.swallow_hotkey,
            cycle_on_wheel=self.cfg.cycle_on_wheel,
        )
        if not monitor.start():
            raise RuntimeError("无法安装全局钩子：%s（可以试试以管理员身份运行）"
                               % (monitor.error or "未知错误"))
        old = self.monitor
        self.monitor = monitor
        monitor.set_paused(self._paused)
        if old is not None:
            old.stop()

    def _hotkey(self, text: str, required: bool = False):
        from hotkeys import Hotkey

        text = str(text or "").strip()
        if not text:
            if required:
                raise RuntimeError("hotkey 不能为空")
            return None
        try:
            return Hotkey.parse(text)
        except ValueError as exc:
            if required:
                raise RuntimeError("快捷键「%s」无效：%s" % (text, exc))
            print("[配置] 忽略无效快捷键 %r：%s" % (text, exc))
            return None

    def run(self) -> int:
        if self._use_tray:
            if not self.tray.start():
                print("[托盘] %s（不影响其它功能）" % (self.tray.error or "不可用"))
        self._print_banner()
        self.root.after(self.POLL_MS, self._pump)
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.shutdown()
        finally:
            try:
                self.monitor.stop()
            except Exception:
                pass
            self.cfg.save(self.cfg_path)
        return 0

    def _print_banner(self) -> None:
        import config as config_mod

        print("=" * 60)
        print(" 桌面表情 Ping 已启动")
        print(" 配置文件   : %s" % self.cfg_path)
        print(" 放置表情   : %s   （%s）"
              % (self.cfg.hotkey, "按住模式" if self.cfg.hotkey_mode == "hold" else "按一下"))
        print(" 打开设置   : %s" % (self.cfg.settings_hotkey or "（未设置，可用托盘菜单）"))
        print(" 静音开关   : %s" % (self.cfg.mute_hotkey or "（未设置）"))
        print(" 退出程序   : %s" % (self.cfg.exit_hotkey or "（未设置，可用托盘菜单）"))
        if self.cfg.has_items:
            print(" 表情数量   : %d 个，当前：%s" % (self.cfg.count, self.cfg.current_text))
        else:
            print(" 表情数量   : 0 —— 请在设置台里「添加图片」")
        print(" 素材文件夹 : %s" % config_mod.assets_dir())
        if getattr(self.cfg, "dropped_items", 0):
            print(" 已清理     : %d 个旧版文字表情（现在只支持图片素材）"
                  % self.cfg.dropped_items)
        print(" 音效       : %s（音量 %.2f）"
              % ("开" if self.cfg.sound_enabled else "关", self.cfg.sound_volume))
        print(" 透明层模式 : %s" % self.layer.mode)
        print(" 托盘图标   : %s" % ("开" if self._use_tray else "关"))
        print("-" * 60)
        print(" 快捷键 → 左键点击放置；滚轮换表情；右键/Esc 取消")
        print("=" * 60)

    # ------------------------------------------------------------------
    # 事件循环
    # ------------------------------------------------------------------
    def _pump(self) -> None:
        if self._stopped:
            return
        try:
            while True:
                kind, payload = self.events.get_nowait()
                self._handle(kind, payload)
                if self._stopped:
                    return
        except queue.Empty:
            pass
        except KeyboardInterrupt:
            self.shutdown()
            return
        try:
            self._pump_timer = self.root.after(self.POLL_MS, self._pump)
        except Exception:
            pass

    def _handle(self, kind: str, payload) -> None:
        if kind == "arm":
            if self.cfg.show_hint:
                self.layer.hint.show(self.cfg.current)
            if self.cfg.has_items:
                print("[就绪] 待放置：%s" % self.cfg.current_text)
            else:
                print("[就绪] 还没有表情，请在设置台（%s）里添加图片"
                      % (self.cfg.settings_hotkey or "Ctrl+Alt+S"))
        elif kind == "disarm":
            self.layer.hint.hide()
        elif kind == "ping":
            self.place_ping(payload[0], payload[1])
        elif kind == "cycle":
            self.cfg.cycle(int(payload))
            self.cfg.save(self.cfg_path)
            self.layer.hint.update_item(self.cfg.current)
            print("[切换] 当前表情：%s" % self.cfg.current_text)
        elif kind == "settings":
            self.open_settings()
        elif kind == "toggle_mute":
            self.toggle_mute()
        elif kind == "toggle_pause":
            self.toggle_pause()
        elif kind == "recorded":
            self._on_recorded(payload)
        elif kind == "record_cancel":
            self._on_record_cancel()
        elif kind == "record_error":
            if self._settings_window:
                self._settings_window.record_failed(payload)
        elif kind == "quit":
            print("[退出] 收到退出指令")
            self.shutdown()

    # ------------------------------------------------------------------
    # 放置
    # ------------------------------------------------------------------
    def place_ping(self, x: int, y: int, item=None) -> None:
        item = item if item is not None else self.cfg.current
        window = self.layer.ping(x, y, item)
        if window is None:
            # 没有可用图片就不画占位图形：提示一下，同时保证音效也不响
            print("[绘制] 跳过：这个表情没有可用图片（%s）" % (item.get("image") or "未设置"))
            if self.cfg.show_hint:
                self.layer.hint.show(item)
            return
        self._play_sound(item, self.cfg)
        from config import item_text
        print("[绘制] %s @ (%d, %d)" % (item_text(item), x, y))

    def _play_sound(self, item, cfg) -> None:
        if not cfg.sound_enabled:
            return
        now = time.monotonic() * 1000.0
        if now - self._last_sound_ms < cfg.sound_min_interval_ms:
            return
        self._last_sound_ms = now
        spec = item.get("sound", "") if isinstance(item, dict) else ""
        error = self.audio.play(spec, cfg.sound_volume, cfg.default_sound)
        if error:
            print("[音效] %s" % error)

    def test_ping(self, item, cfg=None) -> None:
        """设置窗口的「测试」按钮：按当前编辑中的参数放一个表情。"""
        import winapi

        cfg = cfg or self.cfg
        saved = self.layer.cfg
        try:
            self.layer.cfg = cfg            # 让预览反映编辑中的尺寸/颜色
            vx, vy, vw, vh = winapi.virtual_screen()
            window = self.layer.ping(vx + vw // 2, vy + vh // 2, item)
        finally:
            self.layer.cfg = saved
        if window is None:
            print("[测试] 跳过：这个表情没有可用图片")
            return
        self._play_sound(item, cfg)

    # ------------------------------------------------------------------
    # 开关
    # ------------------------------------------------------------------
    def toggle_mute(self) -> None:
        self.cfg.sound_enabled = not self.cfg.sound_enabled
        self.cfg.save(self.cfg_path)
        self._sync_tray()
        self._refresh_settings()
        print("[音效] %s" % ("已开启" if self.cfg.sound_enabled else "已静音"))

    def toggle_pause(self) -> None:
        self._set_paused(not self._paused)

    def _set_paused(self, value: bool) -> None:
        self._paused = bool(value)
        if self.monitor is not None:
            self.monitor.set_paused(self._paused)
            if self._paused:
                self.monitor.set_armed(False)
        if self._paused:
            self.layer.hint.hide()
        self._sync_tray()
        self._refresh_settings()
        print("[监听] %s" % ("已暂停" if self._paused else "已恢复"))

    def is_paused(self) -> bool:
        return self._paused

    def is_muted(self) -> bool:
        return not self.cfg.sound_enabled

    def status_text(self) -> str:
        parts = ["已暂停，快捷键不响应" if self._paused else "监听中"]
        parts.append("放置键 %s" % (self.cfg.hotkey or "未设置"))
        if self.cfg.has_items:
            parts.append("表情 %d 个" % self.cfg.count)
        else:
            parts.append("还没有表情，点「添加图片」")
        parts.append("音效开" if self.cfg.sound_enabled else "已静音")
        if self.layer.mode != "alpha+key":
            parts.append("（当前 Tk 不支持淡出）")
        return " · ".join(parts)

    def _refresh_settings(self) -> None:
        if self._settings_window is not None:
            try:
                self._settings_window.refresh_status()
            except Exception:
                pass

    def _tooltip(self) -> str:
        state = []
        if self._paused:
            state.append("已暂停")
        if not self.cfg.sound_enabled:
            state.append("静音")
        suffix = ("（%s）" % "、".join(state)) if state else ""
        return "桌面表情 Ping%s" % suffix

    def _sync_tray(self) -> None:
        self.tray.set_state(paused=self._paused, muted=not self.cfg.sound_enabled)
        self.tray.set_tooltip(self._tooltip())

    # ------------------------------------------------------------------
    # 设置窗口
    # ------------------------------------------------------------------
    def open_settings(self) -> None:
        if self._settings_window is not None:
            self._settings_window.focus()
            return
        from settings_ui import SettingsWindow

        self._settings_window = SettingsWindow(self)
        self._settings_window.focus()

    def settings_closed(self) -> None:
        self._settings_window = None
        if self._recording_key and self.monitor is not None:
            self.monitor.stop_recording()
            self._recording_key = None

    def start_hotkey_record(self, key: str) -> None:
        if self.monitor is None:
            return
        self._recording_key = key
        self.monitor.start_recording()

    def _on_recorded(self, text: str) -> None:
        key, self._recording_key = self._recording_key, None
        if key and self._settings_window:
            self._settings_window.set_recorded(key, text)

    def _on_record_cancel(self) -> None:
        key, self._recording_key = self._recording_key, None
        if self._settings_window:
            self._settings_window.record_cancelled(key)

    def apply_settings(self, new_cfg) -> None:
        """设置窗口点「保存并应用」：写回配置并即时生效。"""
        from overlay import HintWindow

        def signature(cfg):
            return (cfg.hotkey, cfg.exit_hotkey, cfg.settings_hotkey, cfg.mute_hotkey,
                    cfg.hotkey_mode, cfg.consume_click, cfg.stay_armed,
                    cfg.swallow_hotkey, cfg.cycle_on_wheel)

        before = signature(self.cfg)
        self.cfg.copy_from(new_cfg)
        self.cfg.validate()
        self.cfg.save(self.cfg_path)

        if signature(self.cfg) != before:
            self._start_monitor()      # 快捷键/点击行为变了 → 重装钩子

        # 提示条的字号/字体可能变了，直接重建
        try:
            self.layer.hint.destroy()
        except Exception:
            pass
        self.layer.hint = HintWindow(self.layer)
        self.layer._images.clear()     # 图片设置可能变了
        self._use_tray = bool(self.cfg.enable_tray)
        self._sync_tray()
        self._refresh_settings()
        print("[设置] 已应用新配置")

    # ------------------------------------------------------------------
    def _on_callback_error(self, exc_type, exc, tb) -> None:
        _report_error("桌面表情 Ping 内部错误", exc_type, exc, tb)

    def shutdown(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        if self._pump_timer is not None:
            try:
                self.root.after_cancel(self._pump_timer)
            except Exception:
                pass
            self._pump_timer = None
        if self._settings_window is not None:
            try:
                self._settings_window.close()
            except Exception:
                pass
            self._settings_window = None
        try:
            self.monitor.stop()
        except Exception:
            pass
        try:
            self.tray.stop()
        except Exception:
            pass
        try:
            self.layer.hint.destroy()
            self.layer.clear()
        except Exception:
            pass
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
