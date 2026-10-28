# -*- coding: utf-8 -*-
"""用代码生成程序图标，免去附带二进制素材。

样式：红底圆形 + 白色感叹号（和「ping 标记」的意象一致）。
做法：4 倍超采样画圆与感叹号 → 降采样得到抗锯齿像素 → 编码 PNG
→ 打包成多尺寸 ICO（16 / 32 / 48），Windows Vista 以后都支持 PNG 压缩的图标。
"""
from __future__ import annotations

import math
import os
import struct
import zlib

ACCENT = (232, 72, 58)        # 主色
ACCENT_EDGE = (168, 38, 30)   # 边缘稍暗，看起来更有体积感
MARK = (255, 255, 255)        # 白色感叹号


def _render(size: int, supersample: int = 4) -> list:
    """画一张 size×size 的 RGBA 图，返回逐行 bytes。"""
    ss = max(1, int(supersample))
    big_w = size * ss
    cx = cy = (big_w - 1) / 2.0
    radius = big_w * 0.5 - ss * 0.30

    bar_half = big_w * 0.072        # 感叹号竖线半宽
    bar_top = big_w * 0.235
    bar_bottom = big_w * 0.615
    dot_r = big_w * 0.088
    dot_cy = big_w * 0.762

    buffer = bytearray(big_w * big_w * 4)
    limit = radius + 1.0
    for y in range(big_w):
        py = y + 0.5
        for x in range(big_w):
            px = x + 0.5
            dist = math.hypot(px - cx, py - cy)
            if dist > limit:
                continue
            idx = (y * big_w + x) * 4
            # 圆形本体，边缘 1px 内做覆盖度渐隐
            cover = 1.0 if dist <= radius - 0.5 else max(0.0, radius + 0.5 - dist)
            if cover <= 0.0:
                continue
            ratio = min(1.0, dist / radius)
            red = ACCENT[0] + (ACCENT_EDGE[0] - ACCENT[0]) * ratio
            green = ACCENT[1] + (ACCENT_EDGE[1] - ACCENT[1]) * ratio
            blue = ACCENT[2] + (ACCENT_EDGE[2] - ACCENT[2]) * ratio

            in_bar = abs(px - cx) <= bar_half and bar_top <= py <= bar_bottom
            in_dot = math.hypot(px - cx, py - dot_cy) <= dot_r
            if in_bar or in_dot:
                red, green, blue = MARK

            buffer[idx] = int(red)
            buffer[idx + 1] = int(green)
            buffer[idx + 2] = int(blue)
            buffer[idx + 3] = int(255 * cover)

    # 降采样（按预乘 alpha 求平均，避免边缘出现黑边）
    rows = []
    total = ss * ss
    for y in range(size):
        row = bytearray()
        for x in range(size):
            sr = sg = sb = sa = 0
            for dy in range(ss):
                base = ((y * ss + dy) * big_w + x * ss) * 4
                for dx in range(ss):
                    idx = base + dx * 4
                    a = buffer[idx + 3]
                    sr += buffer[idx] * a
                    sg += buffer[idx + 1] * a
                    sb += buffer[idx + 2] * a
                    sa += a
            alpha = sa // total
            if sa:
                row += bytes((sr // sa, sg // sa, sb // sa, alpha))
            else:
                row += bytes((0, 0, 0, 0))
        rows.append(bytes(row))
    return rows


def png_bytes(size: int) -> bytes:
    """生成 size×size 的 PNG 数据。"""
    rows = _render(size)
    raw = b"".join(b"\x00" + row for row in rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


def ico_bytes(sizes=(16, 32, 48)) -> bytes:
    """把多个尺寸的 PNG 打包成一个 ICO。"""
    images = [(size, png_bytes(size)) for size in sizes]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = bytearray()
    blob = bytearray()
    for size, data in images:
        entries += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
        blob += data
    return header + bytes(entries) + bytes(blob)


def ensure_icon(ico_path: str, png_path: str | None = None) -> str:
    """没有图标就生成一份，返回 ico 路径。"""
    if not (os.path.isfile(ico_path) and os.path.getsize(ico_path) > 0):
        tmp = ico_path + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(ico_bytes())
        os.replace(tmp, ico_path)
    if png_path and not (os.path.isfile(png_path) and os.path.getsize(png_path) > 0):
        with open(png_path, "wb") as fh:
            fh.write(png_bytes(128))
    return ico_path


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    ico = ensure_icon(os.path.join(here, "app.ico"), os.path.join(here, "icon_preview.png"))
    print("已生成：", ico, os.path.getsize(ico), "字节")
