# -*- coding: utf-8 -*-
"""图片素材加载：静态图 + GIF 动图，等比缩放并解析每帧延时。

* 装了 Pillow 就用 Pillow（支持 JPG、缩放质量好、帧延时最准）；
* 没装就用 Tk 原生解码：`PhotoImage(file=..., format="gif -index N")`
  逐帧读入，延时由本模块直接解析 GIF 文件结构得到；
* 缩放沿用 Tk 的整数倍（zoom / subsample），挑最接近目标尺寸的倍数。
"""
from __future__ import annotations

import os
import struct
import tkinter as tk

MAX_FRAMES = 120
DEFAULT_DELAY_MS = 80


class ImageAsset:
    """一张图（或一组动图帧）。frames 里都是已经缩放好的 PhotoImage。"""

    def __init__(self, frames, delays, path: str = ""):
        self.frames = list(frames)
        self.delays = list(delays) or [0] * len(self.frames)
        while len(self.delays) < len(self.frames):
            self.delays.append(DEFAULT_DELAY_MS)
        self.path = path

    @property
    def animated(self) -> bool:
        return len(self.frames) > 1

    def width(self) -> int:
        return int(self.frames[0].width())

    def height(self) -> int:
        return int(self.frames[0].height())

    def delay(self, index: int) -> int:
        """第 index 帧应显示多久（毫秒）。"""
        value = self.delays[index % len(self.delays)]
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = DEFAULT_DELAY_MS
        if value <= 0:
            value = DEFAULT_DELAY_MS
        return max(20, min(2000, value))


# ----------------------------------------------------------------------
# GIF 延时解析（只读文件头和数据块，不做像素解码）
# ----------------------------------------------------------------------
def gif_delays(path: str) -> list:
    """返回 GIF 每帧的延时（毫秒）。解析不了就返回空列表。"""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return []
    if len(data) < 14 or data[:3] != b"GIF":
        return []
    try:
        index = 13                       # 6 字节文件头 + 7 字节逻辑屏幕描述符
        flags = data[10]
        if flags & 0x80:                 # 有全局颜色表
            index += 3 * (2 ** ((flags & 0x07) + 1))
        total = len(data)
        delays = []
        pending = DEFAULT_DELAY_MS
        while index < total:
            block = data[index]
            if block == 0x3B:            # 文件结束
                break
            if block == 0x21:            # 扩展块
                label = data[index + 1] if index + 1 < total else 0
                index += 2
                if label == 0xF9 and index + 6 <= total:   # 图形控制扩展：有帧延时
                    delay = struct.unpack("<H", data[index + 2:index + 4])[0] * 10
                    pending = delay or DEFAULT_DELAY_MS
                while index < total and data[index]:
                    index += data[index] + 1
                index += 1
            elif block == 0x2C:          # 图像描述符：一帧
                if index + 10 > total:
                    break
                local_flags = data[index + 9]
                cursor = index + 10
                if local_flags & 0x80:
                    cursor += 3 * (2 ** ((local_flags & 0x07) + 1))
                cursor += 1              # LZW 最小码长
                while cursor < total and data[cursor]:
                    cursor += data[cursor] + 1
                index = cursor + 1
                delays.append(max(20, min(2000, pending)))
                pending = DEFAULT_DELAY_MS
            else:
                break
        return delays
    except Exception:
        return []


# ----------------------------------------------------------------------
# 加载
# ----------------------------------------------------------------------
def load_image_asset(root: tk.Misc, path: str, size_px: int,
                     max_frames: int = MAX_FRAMES) -> ImageAsset:
    """读入图片并按 size_px 等比缩放（动图会读入所有帧）。"""
    if not path or not os.path.isfile(path):
        raise FileNotFoundError(path)
    size_px = max(8, int(size_px))
    try:
        return _load_with_pillow(root, path, size_px, max_frames)
    except ImportError:
        pass
    return _load_with_tk(root, path, size_px, max_frames)


def _load_with_pillow(root, path, size_px, max_frames) -> ImageAsset:
    from PIL import Image, ImageSequence, ImageTk   # 没装就抛 ImportError

    frames, delays = [], []
    with Image.open(path) as image:
        for index, frame in enumerate(ImageSequence.Iterator(image)):
            if index >= max_frames:
                break
            converted = frame.convert("RGBA")
            converted.thumbnail((size_px, size_px), Image.LANCZOS)
            frames.append(ImageTk.PhotoImage(converted, master=root))
            delays.append(int(frame.info.get("duration") or DEFAULT_DELAY_MS))
    if not frames:
        raise ValueError("图片里没有可用帧：%s" % path)
    return ImageAsset(frames, delays, path)


def _load_with_tk(root, path, size_px, max_frames) -> ImageAsset:
    frames = []
    for index in range(max_frames):
        try:
            frame = tk.PhotoImage(file=path, format="gif -index %d" % index, master=root)
        except tk.TclError:
            break
        frames.append(frame)
    if not frames:
        # 不是 GIF（PNG 等）：直接读一张
        try:
            frames = [tk.PhotoImage(file=path, master=root)]
        except tk.TclError as exc:
            raise ValueError("Tk 读不了这种图片（%s）；建议用 PNG / GIF，"
                             "或用 pip install pillow 来支持 JPG" % exc) from exc

    delays = gif_delays(path) if len(frames) > 1 else []

    # Tk 只能整数倍缩放，挑最接近目标尺寸的倍数，所有帧用同一个倍数
    width, height = frames[0].width(), frames[0].height()
    longest = max(width, height)
    kind, factor, best = None, 1, None
    for candidate in range(2, 17):
        diff = abs(longest / candidate - size_px)
        if best is None or diff < best:
            kind, factor, best = "sub", candidate, diff
    for candidate in range(2, 6):
        scaled = longest * candidate
        if scaled > size_px * 1.6:
            break
        diff = abs(scaled - size_px)
        if best is None or diff < best:
            kind, factor, best = "zoom", candidate, diff
    if best is not None and abs(longest - size_px) <= best:
        kind = None
    if kind == "sub":
        frames = [frame.subsample(factor) for frame in frames]
    elif kind == "zoom":
        frames = [frame.zoom(factor) for frame in frames]
    return ImageAsset(frames, delays, path)


def is_animated(path: str) -> bool:
    """快速判断是不是多帧 GIF（只看延时表长度）。"""
    return len(gif_delays(path)) > 1 if path.lower().endswith(".gif") else False


if __name__ == "__main__":
    import sys

    root = tk.Tk()
    root.withdraw()
    for target in sys.argv[1:]:
        asset = load_image_asset(root, target, 96)
        print("%s -> %d 帧, %dx%d, 延时前几个 %s"
              % (os.path.basename(target), len(asset.frames), asset.width(), asset.height(),
                 [asset.delay(i) for i in range(min(5, len(asset.frames)))]))
    root.destroy()
