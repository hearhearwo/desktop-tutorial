# -*- coding: utf-8 -*-
"""音效播放：只播放你自己的音频文件。

* WAV → winsound 异步播放（必定可用）；
* MP3 / M4A / WMA 等 → MCI（winmm.mciSendStringW），音量走 setaudio volume；
* 不内置任何音效：音效来源就是你在设置台里选的文件路径，
  留空或用 "none" 表示这个表情不出声。

play() 返回空字符串表示成功，否则返回错误描述（设置台会把它显示出来）。
"""
from __future__ import annotations

import ctypes
import os

try:
    import winsound
except ImportError:                     # 非 Windows
    winsound = None

# 这些写法都当"不出声"
SILENT_WORDS = ("", "none", "off", "mute", "silent", "无", "静音", "无音效")

# 设置台文件对话框用的后缀
AUDIO_EXTS = (".wav", ".mp3", ".m4a", ".wma", ".aac", ".ogg", ".flac")

_MCI_ALIAS = "desktop_emoji_ping_snd"
_mci_lib = None


# ----------------------------------------------------------------------
# MCI（WAV 之外的格式）
# ----------------------------------------------------------------------
def _mci(command: str) -> int:
    global _mci_lib
    if _mci_lib is None:
        try:
            _mci_lib = ctypes.WinDLL("winmm")
            _mci_lib.mciSendStringW.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p,
                                                ctypes.c_uint, ctypes.c_void_p)
            _mci_lib.mciSendStringW.restype = ctypes.c_uint
        except OSError:
            _mci_lib = False
    if not _mci_lib:
        return 1
    buffer = ctypes.create_unicode_buffer(512)
    return int(_mci_lib.mciSendStringW(command, buffer, 512, None))


def _mci_play(path: str, volume: float) -> str:
    _mci("close %s" % _MCI_ALIAS)
    quoted = path.replace('"', "'")
    code = _mci('open "%s" type mpegvideo alias %s' % (quoted, _MCI_ALIAS))
    if code:
        code = _mci('open "%s" alias %s' % (quoted, _MCI_ALIAS))
    if code:
        return "MCI 打不开这个音频（错误码 %d），建议转成 WAV：%s" % (code, path)
    _mci("setaudio %s volume to %d" % (_MCI_ALIAS, int(max(0.0, min(1.0, volume)) * 1000)))
    code = _mci("play %s from 0" % _MCI_ALIAS)
    if code:
        _mci("close %s" % _MCI_ALIAS)
        return "MCI 播放失败（错误码 %d）" % code
    return ""


def mci_available() -> bool:
    """MCI（MP3 等格式）是否可用。"""
    _mci("")
    return bool(_mci_lib)


# ----------------------------------------------------------------------
# 对外接口
# ----------------------------------------------------------------------
def is_silent(spec: str) -> bool:
    return str(spec or "").strip().lower() in SILENT_WORDS


def play(spec: str, volume: float = 0.7, default: str = "") -> str:
    """播放音效。

    spec    音频文件路径；留空或 "none" 表示不出声
    default 表情没指定音效时用哪个文件
    """
    if winsound is None:
        return "当前系统没有 winsound，无法播放音效"

    spec = str(spec or "").strip()
    if is_silent(spec):
        spec = str(default or "").strip()
    if is_silent(spec):
        return ""

    path = os.path.expandvars(os.path.expanduser(spec))
    if not os.path.isfile(path):
        return "找不到音效文件：%s" % path

    volume = max(0.0, min(1.0, float(volume)))
    if os.path.splitext(path)[1].lower() == ".wav":
        try:
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC
                               | winsound.SND_NODEFAULT)
            return ""
        except Exception as exc:
            return "播放 WAV 失败：%s" % exc
    return _mci_play(path, volume)


def stop() -> None:
    """立即停止当前音效。"""
    if winsound is not None:
        try:
            winsound.PlaySound(None, 0)
        except Exception:
            pass
    _mci("close %s" % _MCI_ALIAS)


def describe(spec: str, default: str = "") -> str:
    """给界面用的文字描述。"""
    spec = str(spec or "").strip()
    if is_silent(spec):
        default = str(default or "").strip()
        if is_silent(default):
            return "无音效"
        return "跟随默认（%s）" % os.path.basename(default)
    return "文件：%s" % os.path.basename(spec)
