# -*- coding: utf-8 -*-
"""托盘图标 + 右键菜单（纯 ctypes 实现，零第三方依赖）。

在自己的线程里注册窗口类、创建隐藏窗口并跑消息循环；
菜单点击通过 queue 交给 Tk 主线程处理：
    ("settings", None)     打开设置窗口
    ("toggle_pause", None) 暂停 / 恢复监听
    ("toggle_mute", None)  静音开关
    ("quit", None)         退出程序

任何一步失败都只是“没有托盘图标”，程序其余功能不受影响。
"""
from __future__ import annotations

import ctypes
import queue
import threading

import winapi

WM_APP = 0x8000
WM_TRAYICON = WM_APP + 1
WM_NULL = 0x0000
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_CONTEXTMENU = 0x007B
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205

NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 0x1, 0x2, 0x4

MF_STRING = 0x0000
MF_SEPARATOR = 0x0800
MF_CHECKED = 0x0008

TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
TPM_NONOTIFY = 0x0080

IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
LR_DEFAULTSIZE = 0x0040
IDI_APPLICATION = 32512
SM_CXSMICON, SM_CYSMICON = 49, 50
ERROR_CLASS_ALREADY_EXISTS = 1410


class _WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", winapi.UINT),
        ("style", winapi.UINT),
        ("lpfnWndProc", ctypes.c_void_p),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", winapi.HANDLE),
        ("hIcon", winapi.HANDLE),
        ("hCursor", winapi.HANDLE),
        ("hbrBackground", winapi.HANDLE),
        ("lpszMenuName", ctypes.c_wchar_p),
        ("lpszClassName", ctypes.c_wchar_p),
        ("hIconSm", winapi.HANDLE),
    ]


class _NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", winapi.DWORD),
        ("hWnd", winapi.HWND),
        ("uID", winapi.UINT),
        ("uFlags", winapi.UINT),
        ("uCallbackMessage", winapi.UINT),
        ("hIcon", winapi.HANDLE),
        ("szTip", ctypes.c_wchar * 128),
        ("dwState", winapi.DWORD),
        ("dwStateMask", winapi.DWORD),
        ("szInfo", ctypes.c_wchar * 256),
        ("uTimeoutOrVersion", winapi.UINT),
        ("szInfoTitle", ctypes.c_wchar * 64),
        ("dwInfoFlags", winapi.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", winapi.HANDLE),
    ]


_WNDPROC = winapi.WINFUNCTYPE(winapi.LRESULT, winapi.HWND, winapi.UINT,
                              winapi.WPARAM, winapi.LPARAM)

_user32 = winapi.user32
_shell32 = ctypes.WinDLL("shell32", use_last_error=True)

_user32.RegisterClassExW.argtypes = (ctypes.POINTER(_WNDCLASSEXW),)
_user32.RegisterClassExW.restype = ctypes.c_uint16
_user32.CreateWindowExW.argtypes = (winapi.DWORD, ctypes.c_wchar_p, ctypes.c_wchar_p,
                                    winapi.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, winapi.HWND, winapi.HANDLE,
                                    winapi.HINSTANCE, ctypes.c_void_p)
_user32.CreateWindowExW.restype = winapi.HWND
_user32.DefWindowProcW.argtypes = (winapi.HWND, winapi.UINT, winapi.WPARAM, winapi.LPARAM)
_user32.DefWindowProcW.restype = winapi.LRESULT
_user32.DestroyWindow.argtypes = (winapi.HWND,)
_user32.DestroyWindow.restype = winapi.BOOL
_user32.PostQuitMessage.argtypes = (ctypes.c_int,)
_user32.PostMessageW.argtypes = (winapi.HWND, winapi.UINT, winapi.WPARAM, winapi.LPARAM)
_user32.CreatePopupMenu.restype = winapi.HANDLE
_user32.AppendMenuW.argtypes = (winapi.HANDLE, winapi.UINT, ctypes.c_size_t, ctypes.c_wchar_p)
_user32.AppendMenuW.restype = winapi.BOOL
_user32.TrackPopupMenu.argtypes = (winapi.HANDLE, winapi.UINT, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, winapi.HWND, ctypes.c_void_p)
_user32.TrackPopupMenu.restype = winapi.BOOL
_user32.DestroyMenu.argtypes = (winapi.HANDLE,)
_user32.SetForegroundWindow.argtypes = (winapi.HWND,)
_user32.LoadImageW.argtypes = (winapi.HINSTANCE, ctypes.c_wchar_p, winapi.UINT,
                               ctypes.c_int, ctypes.c_int, winapi.UINT)
_user32.LoadImageW.restype = winapi.HANDLE
_user32.LoadIconW.argtypes = (winapi.HINSTANCE, ctypes.c_void_p)
_user32.LoadIconW.restype = winapi.HANDLE
_shell32.Shell_NotifyIconW.argtypes = (winapi.DWORD, ctypes.POINTER(_NOTIFYICONDATAW))
_shell32.Shell_NotifyIconW.restype = winapi.BOOL
_user32.RegisterWindowMessageW.argtypes = (ctypes.c_wchar_p,)
_user32.RegisterWindowMessageW.restype = winapi.UINT

# 让「重复启动」变成「打开设置窗口」：第二个实例广播这条消息，第一个实例收到后弹设置
OPEN_SETTINGS_MESSAGE = int(_user32.RegisterWindowMessageW("DesktopEmojiPing_OpenSettings"))
HWND_BROADCAST = 0xFFFF


def request_open_settings() -> bool:
    """请求已在运行的实例打开设置窗口。"""
    if not OPEN_SETTINGS_MESSAGE:
        return False
    try:
        return bool(_user32.PostMessageW(HWND_BROADCAST, OPEN_SETTINGS_MESSAGE, 0, 0))
    except Exception:
        return False


class TrayIcon:
    """托盘图标。start() 返回是否成功。"""

    CLASS_NAME = "DesktopEmojiPingTrayWnd"
    ICON_ID = 1

    def __init__(self, events: "queue.Queue", tooltip: str = "桌面表情 Ping",
                 icon_path: str | None = None):
        self.events = events
        self.tooltip = tooltip
        self.icon_path = icon_path
        self.paused = False
        self.muted = False
        self.available = False
        self.error: str | None = None

        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._thread_id = 0
        self._hwnd = None
        self._hicon = None
        self._wndproc = None
        self._nid = _NOTIFYICONDATAW()

    # ------------------------------------------------------------------
    def start(self, timeout: float = 5.0) -> bool:
        if self._thread is not None:
            return self.available
        self._thread = threading.Thread(target=self._run, name="tray-icon", daemon=True)
        self._thread.start()
        self._ready.wait(timeout)
        return self.available

    def stop(self) -> None:
        if self._hwnd:
            try:
                _user32.PostMessageW(self._hwnd, WM_CLOSE, 0, 0)
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(2.0)
            self._thread = None

    def set_state(self, paused: bool | None = None, muted: bool | None = None) -> None:
        if paused is not None:
            self.paused = bool(paused)
        if muted is not None:
            self.muted = bool(muted)

    def set_tooltip(self, text: str) -> None:
        self.tooltip = text
        if not self.available or not self._hwnd:
            return
        try:
            nid = self._base_nid()
            nid.uFlags = NIF_TIP
            _shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))
        except Exception:
            pass

    def post_balloon(self, title: str, text: str) -> None:
        """（可选）弹个气泡提示；失败就算了。"""
        if not self.available or not self._hwnd:
            return
        try:
            nid = self._base_nid()
            nid.uFlags = NIF_TIP | 0x10  # NIF_INFO
            nid.szInfo = str(text)[:255]
            nid.szInfoTitle = str(title)[:63]
            nid.dwInfoFlags = 0x1        # NIIF_INFO
            _shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _post(self, kind: str) -> None:
        self.events.put((kind, None))

    def _base_nid(self) -> _NOTIFYICONDATAW:
        nid = _NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(_NOTIFYICONDATAW)
        nid.hWnd = self._hwnd
        nid.uID = self.ICON_ID
        nid.uCallbackMessage = WM_TRAYICON
        nid.hIcon = self._hicon
        nid.szTip = self.tooltip[:127]
        return nid

    def _load_icon(self):
        size = winapi.user32.GetSystemMetrics(SM_CXSMICON) or 16
        if self.icon_path:
            handle = _user32.LoadImageW(None, self.icon_path, IMAGE_ICON, size, size, LR_LOADFROMFILE)
            if handle:
                return handle
        return _user32.LoadIconW(None, ctypes.c_void_p(IDI_APPLICATION))

    # ------------------------------------------------------------------
    def _run(self) -> None:
        try:
            self._thread_id = int(winapi.kernel32.GetCurrentThreadId())
            msg = winapi.MSG()
            winapi.user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)

            hinst = winapi.kernel32.GetModuleHandleW(None)
            self._hicon = self._load_icon()
            self._wndproc = _WNDPROC(self._on_message)

            wc = _WNDCLASSEXW()
            wc.cbSize = ctypes.sizeof(_WNDCLASSEXW)
            wc.style = 0
            wc.lpfnWndProc = ctypes.cast(self._wndproc, ctypes.c_void_p)
            wc.hInstance = hinst
            wc.hIcon = self._hicon
            wc.hIconSm = self._hicon
            wc.lpszClassName = self.CLASS_NAME
            if not _user32.RegisterClassExW(ctypes.byref(wc)):
                if ctypes.get_last_error() != ERROR_CLASS_ALREADY_EXISTS:
                    raise RuntimeError("RegisterClassExW 失败（错误码 %d）" % ctypes.get_last_error())

            self._hwnd = _user32.CreateWindowExW(0, self.CLASS_NAME, "桌面表情 Ping", 0,
                                                 0, 0, 0, 0, None, None, hinst, None)
            if not self._hwnd:
                raise RuntimeError("CreateWindowExW 失败（错误码 %d）" % ctypes.get_last_error())

            nid = self._base_nid()
            nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
            if not _shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)):
                raise RuntimeError("Shell_NotifyIcon 失败（错误码 %d）" % ctypes.get_last_error())
            self._nid = nid
            self.available = True
            self._ready.set()

            while True:
                ret = winapi.user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret in (0, -1):
                    break
                winapi.user32.TranslateMessage(ctypes.byref(msg))
                winapi.user32.DispatchMessageW(ctypes.byref(msg))
        except Exception as exc:
            self.error = "托盘图标不可用：%s" % exc
        finally:
            self._ready.set()
            try:
                if self._hwnd:
                    _shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._base_nid()))
                    _user32.DestroyWindow(ctypes.c_void_p(self._hwnd))
            except Exception:
                pass
            self.available = False
            self._hwnd = None
            self._thread_id = 0

    def _on_message(self, hwnd, msg, wparam, lparam):
        try:
            if msg == OPEN_SETTINGS_MESSAGE:
                self._post("settings")
                return 0
            if msg == WM_TRAYICON:
                event = int(lparam) & 0xFFFF
                if event in (WM_RBUTTONUP, WM_CONTEXTMENU):
                    self._show_menu()
                elif event in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                    self._post("settings")
                return 0
            if msg == WM_CLOSE:
                _user32.DestroyWindow(hwnd)
                return 0
            if msg == WM_DESTROY:
                _user32.PostQuitMessage(0)
                return 0
        except Exception:
            pass
        return _user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _show_menu(self) -> None:
        menu = _user32.CreatePopupMenu()
        if not menu:
            return
        cmd = 0
        try:
            _user32.AppendMenuW(menu, MF_STRING, 1, "设置与表情…")
            _user32.AppendMenuW(menu, MF_STRING | (MF_CHECKED if self.paused else 0), 2, "暂停监听")
            _user32.AppendMenuW(menu, MF_STRING | (MF_CHECKED if self.muted else 0), 3, "静音")
            _user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            _user32.AppendMenuW(menu, MF_STRING, 4, "退出")

            _user32.SetForegroundWindow(self._hwnd)
            x, y = winapi.get_cursor_pos()
            cmd = _user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY,
                                         x, y, 0, self._hwnd, None)
            _user32.PostMessageW(self._hwnd, WM_NULL, 0, 0)
        finally:
            _user32.DestroyMenu(menu)
        action = {1: "settings", 2: "toggle_pause", 3: "toggle_mute", 4: "quit"}.get(int(cmd))
        if action:
            self._post(action)
