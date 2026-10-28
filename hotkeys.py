# -*- coding: utf-8 -*-
"""快捷键字符串解析与匹配。

支持 "ctrl+alt+q"、"ctrl+shift+f1"、"alt+`"、"f8"、"win+d" 这类写法，
按键名不区分大小写。
"""
from __future__ import annotations

# 常用虚拟键码（Virtual-Key Code）
VK_LBUTTON = 0x01
VK_RBUTTON = 0x02
VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12          # Alt
VK_PAUSE = 0x13
VK_CAPITAL = 0x14
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_PRIOR = 0x21         # PageUp
VK_NEXT = 0x22          # PageDown
VK_END = 0x23
VK_HOME = 0x24
VK_LEFT = 0x25
VK_UP = 0x26
VK_RIGHT = 0x27
VK_DOWN = 0x28
VK_INSERT = 0x2D
VK_DELETE = 0x2E
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_NUMPAD0 = 0x60
VK_F1 = 0x70

# 左右修饰键 → 通用修饰键
_MODIFIER_ALIAS = {
    0xA0: VK_SHIFT,      # LShift
    0xA1: VK_SHIFT,      # RShift
    0xA2: VK_CONTROL,    # LCtrl
    0xA3: VK_CONTROL,    # RCtrl
    0xA4: VK_MENU,       # LAlt
    0xA5: VK_MENU,       # RAlt
    VK_RWIN: VK_LWIN,
}

MODIFIER_VKS = frozenset({VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN})

_NAMED_KEYS = {
    "ctrl": VK_CONTROL, "control": VK_CONTROL,
    "alt": VK_MENU, "menu": VK_MENU,
    "shift": VK_SHIFT,
    "win": VK_LWIN, "super": VK_LWIN, "cmd": VK_LWIN, "meta": VK_LWIN,
    "esc": VK_ESCAPE, "escape": VK_ESCAPE,
    "space": VK_SPACE, "tab": VK_TAB,
    "enter": VK_RETURN, "return": VK_RETURN,
    "backspace": VK_BACK, "back": VK_BACK,
    "del": VK_DELETE, "delete": VK_DELETE,
    "ins": VK_INSERT, "insert": VK_INSERT,
    "home": VK_HOME, "end": VK_END,
    "pageup": VK_PRIOR, "pgup": VK_PRIOR,
    "pagedown": VK_NEXT, "pgdn": VK_NEXT,
    "up": VK_UP, "down": VK_DOWN, "left": VK_LEFT, "right": VK_RIGHT,
    "caps": VK_CAPITAL, "capslock": VK_CAPITAL,
    "pause": VK_PAUSE,
    "`": 0xC0, "~": 0xC0,
    "-": 0xBD, "_": 0xBD,
    "=": 0xBB, "+": 0xBB,
    "[": 0xDB, "{": 0xDB,
    "]": 0xDD, "}": 0xDD,
    "\\": 0xDC, "|": 0xDC,
    ";": 0xBA, ":": 0xBA,
    "'": 0xDE, '"': 0xDE,
    ",": 0xBC, "<": 0xBC,
    ".": 0xBE, ">": 0xBE,
    "/": 0xBF, "?": 0xBF,
}
# 数字 0-9 与字母 A-Z 的虚拟键码就是其 ASCII 码
for _c in range(0x30, 0x3A):
    _NAMED_KEYS[chr(_c)] = _c
for _c in range(0x41, 0x5B):
    _NAMED_KEYS[chr(_c)] = _c
for _i in range(1, 25):
    _NAMED_KEYS["f%d" % _i] = VK_F1 + _i - 1
for _i in range(10):
    _NAMED_KEYS["num%d" % _i] = VK_NUMPAD0 + _i


def normalize_vk(vk: int) -> int:
    """把左右修饰键统一成通用修饰键。"""
    return _MODIFIER_ALIAS.get(vk, vk)


def normalize_set(vks) -> set:
    return {normalize_vk(v) for v in vks}


# 反查表：虚拟键码 → 名字（同一个键有多个别名时取最先定义的）
_VK_NAMES = {}
for _name, _vk in _NAMED_KEYS.items():
    _VK_NAMES.setdefault(_vk, _name)
del _name, _vk


def vk_name(vk: int) -> str:
    """虚拟键码 → 可读名字，例如 0x51 → "q"。"""
    key = normalize_vk(vk)
    return _VK_NAMES.get(key, "vk%02x" % key)


def hotkey_text(vk: int, pressed_raw) -> str:
    """把「按下的键 + 当前按下的修饰键」拼成 ctrl+alt+q 这样的字符串。"""
    mods = normalize_set(pressed_raw)
    parts = [name for name, code in (("ctrl", VK_CONTROL), ("shift", VK_SHIFT),
                                     ("alt", VK_MENU), ("win", VK_LWIN)) if code in mods]
    parts.append(vk_name(vk))
    return "+".join(parts)


class Hotkey:
    """一个全局快捷键：一个主键 + 若干修饰键。"""

    __slots__ = ("vk", "mods", "text")

    def __init__(self, vk: int, mods, text: str = ""):
        self.vk = vk
        self.mods = set(mods)
        self.text = text or self._format(vk, self.mods)

    @staticmethod
    def _format(vk: int, mods) -> str:
        parts = []
        if VK_CONTROL in mods:
            parts.append("Ctrl")
        if VK_SHIFT in mods:
            parts.append("Shift")
        if VK_MENU in mods:
            parts.append("Alt")
        if VK_LWIN in mods:
            parts.append("Win")
        if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
            parts.append(chr(vk))
        elif VK_F1 <= vk <= VK_F1 + 23:
            parts.append("F%d" % (vk - VK_F1 + 1))
        else:
            parts.append("VK_0x%02X" % vk)
        return "+".join(parts)

    @classmethod
    def parse(cls, text: str) -> "Hotkey":
        """解析快捷键字符串，失败时抛 ValueError。"""
        if not text or not str(text).strip():
            raise ValueError("快捷键不能为空")
        tokens = [t for t in str(text).replace(" ", "").split("+") if t]
        if not tokens:
            raise ValueError("快捷键不能为空: %r" % (text,))

        mods = set()
        vk = None
        for token in tokens:
            key = _NAMED_KEYS.get(token.lower())
            if key is None and len(token) == 1:
                key = _NAMED_KEYS.get(token.upper())
            if key is None:
                raise ValueError("无法识别的按键: %r" % token)
            if key in MODIFIER_VKS:
                mods.add(key)
            else:
                if vk is not None:
                    raise ValueError("一个快捷键只能有一个主键: %r" % (text,))
                vk = key
        if vk is None:
            raise ValueError("快捷键必须包含一个非修饰键，例如 ctrl+alt+q: %r" % (text,))
        return cls(vk, mods, str(text).strip())

    def matches(self, vk: int, pressed_raw) -> bool:
        """判断按键事件是否命中本快捷键。

        vk 为本次按下的键，pressed_raw 为当前所有按下的键（含左右区分）。
        """
        if normalize_vk(vk) != self.vk:
            return False
        return self.mods.issubset(normalize_set(pressed_raw))

    def __repr__(self) -> str:
        return "Hotkey(%s)" % self.text
