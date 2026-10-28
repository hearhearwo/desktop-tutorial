# -*- coding: utf-8 -*-
"""Win32 底层封装（只用标准库 ctypes，无第三方依赖）。

职责：
  1. 开启进程 DPI 感知，避免多显示器 / 缩放（125%、150%）下坐标错位；
  2. 提供全局低级键鼠钩子（WH_KEYBOARD_LL / WH_MOUSE_LL）的常量与结构体；
  3. 提供悬浮窗样式操作：点击穿透、不抢焦点、不进 Alt+Tab，
     以及读取分层窗口（Layered Window）的透明属性。

所有结构体都显式声明类型，不依赖 ctypes.wintypes 的实现细节。
"""
from __future__ import annotations

import ctypes
from ctypes import POINTER, WINFUNCTYPE, byref

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
try:
    shcore = ctypes.WinDLL("shcore", use_last_error=True)
except OSError:  # Windows 8 之前没有 shcore.dll
    shcore = None

# --------------------------------------------------------------------------
# 基础类型
# --------------------------------------------------------------------------
BOOL = ctypes.c_int32
DWORD = ctypes.c_uint32
UINT = ctypes.c_uint32
LONG = ctypes.c_int32
BYTE = ctypes.c_ubyte
HANDLE = ctypes.c_void_p
HWND = HANDLE
HINSTANCE = HANDLE
HMODULE = HANDLE
HHOOK = HANDLE
WPARAM = ctypes.c_size_t
LPARAM = ctypes.c_ssize_t
LRESULT = ctypes.c_ssize_t

PTR_BITS = ctypes.sizeof(ctypes.c_void_p) * 8


class POINT(ctypes.Structure):
    _fields_ = [("x", LONG), ("y", LONG)]


class MSG(ctypes.Structure):
    # 与 Win32 MSG 内存布局一致（ctypes 按平台自然对齐）
    _fields_ = [
        ("hwnd", HWND),
        ("message", UINT),
        ("wParam", WPARAM),
        ("lParam", LPARAM),
        ("time", DWORD),
        ("pt", POINT),
    ]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", DWORD),
        ("scanCode", DWORD),
        ("flags", DWORD),
        ("time", DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", DWORD),
        ("flags", DWORD),
        ("time", DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


# --------------------------------------------------------------------------
# 常量
# --------------------------------------------------------------------------
WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
HC_ACTION = 0

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012

WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MOUSEWHEEL = 0x020A

GWL_EXSTYLE = -20
GA_ROOT = 2

WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020  # 鼠标点击穿透
WS_EX_NOACTIVATE = 0x08000000   # 不抢焦点
WS_EX_TOOLWINDOW = 0x00000080   # 不出现在 Alt+Tab

LWA_COLORKEY = 0x00000001
LWA_ALPHA = 0x00000002

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
PROCESS_PER_MONITOR_DPI_AWARE = 2
ERROR_ALREADY_EXISTS = 183
MB_ICONERROR = 0x10
MB_ICONINFORMATION = 0x40

# 低级钩子回调类型：LRESULT CALLBACK HookProc(int, WPARAM, LPARAM)
if ctypes.sizeof(ctypes.c_void_p) == 8:
    HOOKPROC = WINFUNCTYPE(LRESULT, ctypes.c_int, WPARAM, LPARAM)
else:
    HOOKPROC = WINFUNCTYPE(ctypes.c_long, ctypes.c_int, WPARAM, LPARAM)


# --------------------------------------------------------------------------
# 函数原型
# --------------------------------------------------------------------------
user32.SetWindowsHookExW.argtypes = (ctypes.c_int, HOOKPROC, HINSTANCE, DWORD)
user32.SetWindowsHookExW.restype = HHOOK
user32.UnhookWindowsHookEx.argtypes = (HHOOK,)
user32.UnhookWindowsHookEx.restype = BOOL
user32.CallNextHookEx.argtypes = (HHOOK, ctypes.c_int, WPARAM, LPARAM)
user32.CallNextHookEx.restype = LRESULT

user32.GetMessageW.argtypes = (POINTER(MSG), HWND, UINT, UINT)
user32.GetMessageW.restype = BOOL
user32.PeekMessageW.argtypes = (POINTER(MSG), HWND, UINT, UINT, UINT)
user32.PeekMessageW.restype = BOOL
user32.TranslateMessage.argtypes = (POINTER(MSG),)
user32.TranslateMessage.restype = BOOL
user32.DispatchMessageW.argtypes = (POINTER(MSG),)
user32.DispatchMessageW.restype = LRESULT
user32.PostThreadMessageW.argtypes = (DWORD, UINT, WPARAM, LPARAM)
user32.PostThreadMessageW.restype = BOOL

user32.GetCursorPos.argtypes = (POINTER(POINT),)
user32.GetCursorPos.restype = BOOL
user32.GetSystemMetrics.argtypes = (ctypes.c_int,)
user32.GetSystemMetrics.restype = ctypes.c_int
user32.GetAncestor.argtypes = (HWND, UINT)
user32.GetAncestor.restype = HWND
user32.GetParent.argtypes = (HWND,)
user32.GetParent.restype = HWND
user32.SetWindowPos.argtypes = (HWND, HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, UINT)
user32.SetWindowPos.restype = BOOL
user32.GetLayeredWindowAttributes.argtypes = (HWND, POINTER(DWORD), POINTER(BYTE), POINTER(DWORD))
user32.GetLayeredWindowAttributes.restype = BOOL
user32.MessageBoxW.argtypes = (HWND, ctypes.c_wchar_p, ctypes.c_wchar_p, UINT)
user32.MessageBoxW.restype = ctypes.c_int

kernel32.GetModuleHandleW.argtypes = (ctypes.c_wchar_p,)
kernel32.GetModuleHandleW.restype = HMODULE
kernel32.GetCurrentThreadId.argtypes = ()
kernel32.GetCurrentThreadId.restype = DWORD
kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, BOOL, ctypes.c_wchar_p)
kernel32.CreateMutexW.restype = HANDLE

# GetWindowLongPtrW 在 32 位 Python 上不存在，退化为 GetWindowLongW
_get_window_long = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
_set_window_long = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
_get_window_long.argtypes = (HWND, ctypes.c_int)
_get_window_long.restype = ctypes.c_ssize_t
_set_window_long.argtypes = (HWND, ctypes.c_int, ctypes.c_ssize_t)
_set_window_long.restype = ctypes.c_ssize_t


# --------------------------------------------------------------------------
# DPI 感知
# --------------------------------------------------------------------------
def _as_handle(value: int) -> HANDLE:
    return HANDLE(value & ((1 << PTR_BITS) - 1))


def enable_dpi_awareness() -> bool:
    """开启 DPI 感知，返回是否成功。必须在创建任何窗口之前调用。"""
    try:
        fn = user32.SetProcessDpiAwarenessContext
        fn.argtypes = (HANDLE,)
        fn.restype = BOOL
        if fn(_as_handle(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)):
            return True
    except Exception:
        pass

    if shcore is not None:
        try:
            if shcore.SetProcessDpiAwareness(PROCESS_PER_MONITOR_DPI_AWARE) == 0:  # S_OK
                return True
        except Exception:
            pass

    try:
        return bool(user32.SetProcessDPIAware())
    except Exception:
        return False


# --------------------------------------------------------------------------
# 坐标 / 屏幕
# --------------------------------------------------------------------------
def get_cursor_pos() -> tuple[int, int]:
    pt = POINT()
    if not user32.GetCursorPos(byref(pt)):
        return (0, 0)
    return (int(pt.x), int(pt.y))


def virtual_screen() -> tuple[int, int, int, int]:
    """返回 (x, y, width, height)，多显示器时为整个虚拟桌面范围。"""
    return (
        int(user32.GetSystemMetrics(SM_XVIRTUALSCREEN)),
        int(user32.GetSystemMetrics(SM_YVIRTUALSCREEN)),
        int(user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)),
        int(user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)),
    )


def wheel_delta(mouse_data: int) -> int:
    """从 MSLLHOOKSTRUCT.mouseData 取出滚轮方向（+120 上滚 / -120 下滚）。"""
    raw = (mouse_data >> 16) & 0xFFFF
    if raw >= 0x8000:
        raw -= 0x10000
    return raw


# --------------------------------------------------------------------------
# 窗口样式
# --------------------------------------------------------------------------
def to_hwnd(value) -> int:
    """把 Tk 给的窗口句柄转成整数。

    winfo_id() 在 Windows 上的返回值可能是整数，也可能是 "0x1a0f2c"
    这种十六进制字符串，两种都要能处理。
    """
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if text.lower().startswith("0x"):
        try:
            return int(text, 16)
        except ValueError:
            return 0
    try:
        return int(text)
    except ValueError:
        return 0


def root_hwnd(hwnd) -> int:
    """Tk 的 winfo_id() 返回子窗口，向上找到真正的顶层窗口。"""
    hwnd = to_hwnd(hwnd)
    root = user32.GetAncestor(HWND(hwnd), GA_ROOT)
    return int(root) if root else hwnd


def window_chain(hwnd) -> list:
    """返回候选窗口句柄列表：顶层窗口 → 父窗口 → 原始子窗口。

    Tk 会把分层属性设在顶层包装窗口上，不同 Tk 版本层级可能不同，
    逐个尝试最稳妥。
    """
    child = to_hwnd(hwnd)
    candidates = []
    root = user32.GetAncestor(HWND(child), GA_ROOT)
    parent = user32.GetParent(HWND(child))
    for handle in (root, parent, child):
        if handle:
            value = int(handle)
            if value and value not in candidates:
                candidates.append(value)
    return candidates


def make_click_through(hwnd: int) -> bool:
    """让窗口点击穿透、不抢焦点、不出现在 Alt+Tab。

    注意：改动 GWL_EXSTYLE 有可能重置分层窗口的透明属性，
    所以样式已经齐全时直接返回，不做多余改动。
    """
    try:
        needed = WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
        style = _get_window_long(HWND(hwnd), GWL_EXSTYLE)
        if (style & needed) == needed:
            return True
        _set_window_long(HWND(hwnd), GWL_EXSTYLE, style | needed)
        user32.SetWindowPos(HWND(hwnd), None, 0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED)
        return True
    except Exception:
        return False


def get_layered_attributes(hwnd: int) -> tuple[int, int, int]:
    """读取分层窗口属性，返回 (flags, colorkey, alpha)。

    flags 含 LWA_COLORKEY 表示色键透明生效，含 LWA_ALPHA 表示整体透明度生效。
    失败时返回 (0, 0, -1)。
    """
    flags = DWORD(0)
    key = DWORD(0)
    alpha = BYTE(0)
    try:
        ok = user32.GetLayeredWindowAttributes(HWND(hwnd), byref(key), byref(alpha), byref(flags))
        if not ok:
            return (0, 0, -1)
        return (int(flags.value), int(key.value), int(alpha.value))
    except Exception:
        return (0, 0, -1)


# --------------------------------------------------------------------------
# 其它
# --------------------------------------------------------------------------
_SINGLETON_HANDLES = []


def acquire_single_instance(name: str) -> bool:
    """用命名互斥体做单实例检查，返回是否拿到所有权。"""
    try:
        handle = kernel32.CreateMutexW(None, False, name)
        if not handle:
            return True
        _SINGLETON_HANDLES.append(handle)  # 保活，程序退出前不能释放
        return ctypes.get_last_error() != ERROR_ALREADY_EXISTS
    except Exception:
        return True


def message_box(text: str, title: str = "桌面表情 Ping", flags: int = MB_ICONERROR) -> None:
    """弹系统消息框——用 pythonw 启动时没有控制台，出错只能靠它提示。"""
    try:
        user32.MessageBoxW(None, str(text), str(title), flags)
    except Exception:
        pass
