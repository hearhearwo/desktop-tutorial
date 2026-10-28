# -*- coding: utf-8 -*-
"""全局键鼠监听。

在独立线程里安装两个低级钩子：
  * WH_KEYBOARD_LL —— 监听快捷键（在任何程序、任何窗口都生效）；
  * WH_MOUSE_LL    —— 监听"待放置"状态下的左键点击位置。

低级钩子必须在安装它的线程里跑消息循环，所以本类自带一个线程 + GetMessage 循环，
事件通过 queue.Queue 交给 Tk 主线程处理（钩子回调里不能碰 Tk）。
"""
from __future__ import annotations

import ctypes
import queue
import threading

import winapi
from hotkeys import (MODIFIER_VKS, VK_ESCAPE, VK_F1, Hotkey, hotkey_text,
                     normalize_vk)

PM_NOREMOVE = 0x0000


class InputMonitor:
    """全局快捷键 + 鼠标点击监听器。"""

    def __init__(self, hotkey: Hotkey, events: "queue.Queue", *, mode: str = "toggle",
                 exit_hotkey: Hotkey | None = None, settings_hotkey: Hotkey | None = None,
                 mute_hotkey: Hotkey | None = None, cancel_vks=(VK_ESCAPE,),
                 consume_click: bool = True, stay_armed: bool = False,
                 swallow_hotkey: bool = True, cycle_on_wheel: bool = True):
        self.hotkey = hotkey
        self.exit_hotkey = exit_hotkey
        self.settings_hotkey = settings_hotkey
        self.mute_hotkey = mute_hotkey
        self.events = events
        self.mode = mode
        self.cancel_vks = {normalize_vk(v) for v in cancel_vks}
        self.consume_click = bool(consume_click)
        self.stay_armed = bool(stay_armed)
        self.swallow_hotkey = bool(swallow_hotkey)
        self.cycle_on_wheel = bool(cycle_on_wheel)

        self.armed = False
        self.paused = False        # 暂停：不响应主快捷键
        self.suspended = False     # 临时让出：录制快捷键 / 设置窗口输入时不抢键
        self.recording = False     # 正在录制快捷键
        self.error: str | None = None

        self._pressed: set[int] = set()
        self._swallow_lup = False
        self._swallow_rup = False

        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._kb_hook = None
        self._ms_hook = None
        self._kb_proc = None
        self._ms_proc = None

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def start(self, timeout: float = 5.0) -> bool:
        """启动监听线程并等待钩子安装完成，返回是否成功。"""
        if self._thread is not None:
            return self.error is None
        self._thread = threading.Thread(target=self._run, name="input-monitor", daemon=True)
        self._thread.start()
        self._ready.wait(timeout)
        return self.error is None

    def stop(self, timeout: float = 2.0) -> None:
        if self._thread_id:
            winapi.user32.PostThreadMessageW(self._thread_id, winapi.WM_QUIT, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None

    def set_armed(self, value: bool) -> None:
        """由主线程调用：强制设置/取消待放置状态。"""
        self._set_armed(bool(value))

    def set_paused(self, value: bool) -> None:
        """暂停/恢复主快捷键（托盘菜单、设置界面用）。"""
        self.paused = bool(value)
        if self.paused:
            self._set_armed(False)

    def start_recording(self) -> None:
        """开始录制快捷键：后续按键不会被界面收到，也不会触发任何快捷键。"""
        self._set_armed(False)
        self._pressed.clear()
        self.suspended = True
        self.recording = True

    def stop_recording(self) -> None:
        self.recording = False
        self.suspended = False

    # ------------------------------------------------------------------
    # 监听线程
    # ------------------------------------------------------------------
    def _run(self) -> None:
        try:
            self._thread_id = int(winapi.kernel32.GetCurrentThreadId())
            # 先建好线程消息队列，这样 stop() 一定能 PostThreadMessage 成功
            msg = winapi.MSG()
            winapi.user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_NOREMOVE)

            hmod = winapi.kernel32.GetModuleHandleW(None)
            self._kb_proc = winapi.HOOKPROC(self._key_proc)
            self._ms_proc = winapi.HOOKPROC(self._mouse_proc)
            self._kb_hook = winapi.user32.SetWindowsHookExW(winapi.WH_KEYBOARD_LL, self._kb_proc, hmod, 0)
            self._ms_hook = winapi.user32.SetWindowsHookExW(winapi.WH_MOUSE_LL, self._ms_proc, hmod, 0)
            if not self._kb_hook or not self._ms_hook:
                err = ctypes.get_last_error()
                self.error = "安装全局钩子失败（Win32 错误码 %d）" % err

            self._ready.set()
            if self.error:
                return

            while True:
                ret = winapi.user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret in (0, -1):
                    break
                winapi.user32.TranslateMessage(ctypes.byref(msg))
                winapi.user32.DispatchMessageW(ctypes.byref(msg))
        except Exception as exc:  # 线程内异常必须吞掉并上报
            self.error = "监听线程异常：%r" % (exc,)
        finally:
            self._ready.set()
            if self._kb_hook:
                winapi.user32.UnhookWindowsHookEx(self._kb_hook)
                self._kb_hook = None
            if self._ms_hook:
                winapi.user32.UnhookWindowsHookEx(self._ms_hook)
                self._ms_hook = None
            self._thread_id = 0

    # ------------------------------------------------------------------
    # 钩子回调（运行在监听线程）
    # ------------------------------------------------------------------
    def _key_proc(self, code, wparam, lparam):
        if code == winapi.HC_ACTION:
            try:
                kb = ctypes.cast(lparam, ctypes.POINTER(winapi.KBDLLHOOKSTRUCT)).contents
                vk = int(kb.vkCode)
                if self.recording:
                    self._record_key(vk, wparam)
                    return 1          # 录制期间吞掉全部键盘事件
                if self.suspended:
                    return winapi.user32.CallNextHookEx(None, code, wparam, lparam)
                if wparam in (winapi.WM_KEYDOWN, winapi.WM_SYSKEYDOWN):
                    first_press = vk not in self._pressed
                    self._pressed.add(vk)
                    if self._on_key_down(vk, first_press):
                        return 1
                elif wparam in (winapi.WM_KEYUP, winapi.WM_SYSKEYUP):
                    self._pressed.discard(vk)
                    if self._on_key_up(vk):
                        return 1
            except Exception:
                pass
        return winapi.user32.CallNextHookEx(None, code, wparam, lparam)

    def _record_key(self, vk: int, wparam) -> None:
        """录制快捷键：等一个「修饰键 + 主键」的组合。"""
        if wparam in (winapi.WM_KEYDOWN, winapi.WM_SYSKEYDOWN):
            self._pressed.add(vk)
            key = normalize_vk(vk)
            if key in MODIFIER_VKS:
                return                                   # 只按了修饰键，继续等主键
            if key == VK_ESCAPE:
                self.stop_recording()
                self._post("record_cancel", None)
                return
            mods = {normalize_vk(v) for v in self._pressed} & MODIFIER_VKS
            if not mods and not (VK_F1 <= key <= VK_F1 + 23):
                self._post("record_error",
                           "至少要带一个修饰键（Ctrl / Alt / Shift / Win），或者用 F1~F24")
                return                                   # 保持录制状态，等用户重按
            text = hotkey_text(vk, self._pressed)
            self.stop_recording()
            self._post("recorded", text)
        elif wparam in (winapi.WM_KEYUP, winapi.WM_SYSKEYUP):
            self._pressed.discard(vk)

    def _mouse_proc(self, code, wparam, lparam):
        if code == winapi.HC_ACTION:
            try:
                if self.suspended:
                    return winapi.user32.CallNextHookEx(None, code, wparam, lparam)
                ms = ctypes.cast(lparam, ctypes.POINTER(winapi.MSLLHOOKSTRUCT)).contents
                if wparam == winapi.WM_LBUTTONDOWN and self.armed:
                    # 记录按下位置 → 交给主线程绘制
                    self._swallow_lup = self.consume_click
                    self._post("ping", (int(ms.pt.x), int(ms.pt.y)))
                    if not self.stay_armed:
                        self._set_armed(False)
                    if self.consume_click:
                        return 1
                elif wparam == winapi.WM_LBUTTONUP and self._swallow_lup:
                    self._swallow_lup = False
                    return 1
                elif wparam == winapi.WM_RBUTTONDOWN and self.armed:
                    self._swallow_rup = True
                    self._set_armed(False)
                    return 1
                elif wparam == winapi.WM_RBUTTONUP and self._swallow_rup:
                    self._swallow_rup = False
                    return 1
                elif wparam == winapi.WM_MOUSEWHEEL and self.armed and self.cycle_on_wheel:
                    self._post("cycle", 1 if winapi.wheel_delta(int(ms.mouseData)) > 0 else -1)
                    return 1
            except Exception:
                pass
        return winapi.user32.CallNextHookEx(None, code, wparam, lparam)

    # ------------------------------------------------------------------
    # 状态机
    # ------------------------------------------------------------------
    def _on_key_down(self, vk: int, first_press: bool) -> bool:
        """返回 True 表示吞掉这次按键。"""
        if self.exit_hotkey is not None and self.exit_hotkey.matches(vk, self._pressed):
            self._post("quit", None)
            return True

        if self.settings_hotkey is not None and self.settings_hotkey.matches(vk, self._pressed):
            if first_press:
                self._set_armed(False)
                self._post("settings", None)
            return True

        if self.mute_hotkey is not None and self.mute_hotkey.matches(vk, self._pressed):
            if first_press:
                self._post("toggle_mute", None)
            return True

        if not self.paused and self.hotkey.matches(vk, self._pressed):
            if first_press:
                if self.mode == "hold":
                    self._set_armed(True)
                else:
                    self._set_armed(not self.armed)
            return self.swallow_hotkey

        if self.armed and normalize_vk(vk) in self.cancel_vks:
            self._set_armed(False)
            return True  # 待放置时按 Esc 直接取消
        return False

    def _on_key_up(self, vk: int) -> bool:
        if self.mode == "hold" and normalize_vk(vk) == self.hotkey.vk and self.armed:
            self._set_armed(False)
            return self.swallow_hotkey
        return False

    def _set_armed(self, value: bool) -> None:
        if value == self.armed:
            return
        self.armed = value
        self._post("arm" if value else "disarm", None)

    def _post(self, kind: str, payload) -> None:
        self.events.put((kind, payload))
