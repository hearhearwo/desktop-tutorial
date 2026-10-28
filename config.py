# -*- coding: utf-8 -*-
"""配置读写。

配置文件是程序目录下的 config.json，首次运行自动生成，也可以在设置台里改。

一个表情 = 一张图片 + 一个音效，图片和音效都用你自己的素材文件：

    "items": [
      {"image": "表情素材/banana.png", "sound": ""},
      {"image": "表情素材/fire.gif", "sound": "表情素材/boom.wav", "size": 120}
    ]

字段说明（每一项）：
    image 图片路径（PNG / GIF 动图 / JPG；相对路径会先在程序目录找，再到素材目录找）
    sound 音效文件路径；留空或用 "none" 表示这个表情不出声
    size  该表情单独的大小（像素），0 表示跟随全局 size
    label 在设置台列表里显示的名字，留空自动用文件名

程序不内置任何图片和音效，素材全部来自你选的、或放进「表情素材」文件夹的文件。
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass, field, fields
from typing import Any, List

ITEM_FIELDS = ("image", "sound", "size", "label")

# 图片素材统一放在程序目录下的这个文件夹里（选图片时会自动拷进来）
ASSETS_DIRNAME = "表情素材"
IMAGE_EXTS = (".png", ".gif", ".jpg", ".jpeg", ".bmp", ".webp", ".ico", ".ppm", ".pgm")


def app_dir() -> str:
    """程序所在目录。

    跑源码时是脚本目录；用 PyInstaller 打包成 exe 后，__file__ 指向临时解包目录，
    所以要改用 exe 自己所在的目录，配置和素材才不会丢。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = app_dir()


def set_base_dir(path: str) -> None:
    """记住程序所在目录，用来解析相对路径和素材文件夹。"""
    global BASE_DIR
    BASE_DIR = os.path.abspath(path)


def assets_dir(base_dir: str | None = None, create: bool = True) -> str:
    """素材文件夹：<程序目录>/表情素材。"""
    folder = os.path.join(os.path.abspath(base_dir or BASE_DIR), ASSETS_DIRNAME)
    if create:
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError:
            pass
    return folder


def resolve_image(path: str, base_dir: str | None = None) -> str:
    """把配置里的图片路径解析成绝对路径（相对路径按程序目录 / 素材目录找）。"""
    if not path:
        return ""
    text = os.path.expandvars(os.path.expanduser(str(path).strip()))
    if os.path.isabs(text):
        return text
    base = os.path.abspath(base_dir or BASE_DIR)
    for candidate in (os.path.join(base, text), os.path.join(base, ASSETS_DIRNAME, text)):
        if os.path.isfile(candidate):
            return candidate
    return os.path.join(base, text)


def resolve_audio(path: str, base_dir: str | None = None) -> str:
    """音效文件同样支持相对路径。"""
    return resolve_image(path, base_dir) if path else ""


def import_asset(src: str, base_dir: str | None = None) -> str:
    """把外部文件拷进素材文件夹，返回相对路径（重名会自动加序号）。"""
    src = os.path.abspath(src)
    base = os.path.abspath(base_dir or BASE_DIR)
    folder = assets_dir(base)
    if os.path.dirname(src).lower() == folder.lower():
        return os.path.relpath(src, base).replace("\\", "/")

    name = os.path.basename(src)
    stem, ext = os.path.splitext(name)
    target = os.path.join(folder, name)
    counter = 1
    while os.path.exists(target) and os.path.getsize(target) != os.path.getsize(src):
        target = os.path.join(folder, "%s_%d%s" % (stem, counter, ext))
        counter += 1
    try:
        if not os.path.exists(target):
            shutil.copy2(src, target)
    except OSError as exc:
        print("[素材] 复制失败，继续用原路径：%s" % exc)
        return src
    return os.path.relpath(target, base).replace("\\", "/")


def iter_image_files(folder: str) -> List[str]:
    """列出文件夹里的图片文件（不递归）。"""
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    return [os.path.join(folder, name) for name in names
            if os.path.splitext(name)[1].lower() in IMAGE_EXTS
            and os.path.isfile(os.path.join(folder, name))]


def normalize_item(value, index: int = 0) -> dict:
    """把表情项规整成标准 dict。"""
    if isinstance(value, str):
        # 老配置里可能直接写路径
        item = {"image": value}
    elif isinstance(value, dict):
        item = {key: value.get(key) for key in ITEM_FIELDS}
    else:
        item = {}

    item["image"] = str(item.get("image") or "").strip()
    item["sound"] = str(item.get("sound") or "").strip()
    item["label"] = str(item.get("label") or "").strip()
    try:
        item["size"] = int(item.get("size") or 0)
    except (TypeError, ValueError):
        item["size"] = 0
    item["size"] = max(0, min(400, item["size"]))
    return item


@dataclass
class Config:
    # ---- 快捷键 ----
    hotkey: str = "ctrl+alt+q"                  # 进入待放置状态
    exit_hotkey: str = "ctrl+alt+shift+q"       # 退出，留空表示不启用
    settings_hotkey: str = "ctrl+alt+s"         # 打开设置台
    mute_hotkey: str = "ctrl+alt+m"             # 静音开/关
    hotkey_mode: str = "toggle"                 # toggle=按一下；hold=按住期间可连续点

    # ---- 表情（图片 + 音效，全部来自你自己的素材）----
    items: List[Any] = field(default_factory=list)
    current_index: int = 0
    size: int = 96                              # 默认表情像素尺寸（图片按这个缩放）
    transparent_color: str = "#FF00FF"          # 透明色键，一般不用改

    # ---- 动画 ----
    duration_ms: int = 3000                     # 停留时间（毫秒）
    fade_ms: int = 700                          # 淡出时长（毫秒）

    # ---- 音效 ----
    sound_enabled: bool = True
    default_sound: str = ""                     # 表情没指定音效时用哪个文件，留空=不出声
    sound_volume: float = 0.7                   # 0.0 ~ 1.0
    sound_min_interval_ms: int = 60             # 最短播放间隔，避免连续点击时糊成一片

    # ---- 交互 ----
    consume_click: bool = True                  # 放置时吞掉这次左键点击
    stay_armed: bool = False                    # 放置后是否继续保持待放置
    swallow_hotkey: bool = True                 # 拦截快捷键本身，避免触发其它软件
    cycle_on_wheel: bool = True                 # 待放置时滚轮切换表情
    show_hint: bool = True                      # 待放置时在鼠标旁显示提示条
    hint_font_size: int = 14
    hint_thumb_size: int = 40                   # 提示条里缩略图的大小

    # ---- 位置微调 ----
    offset_x: int = 0
    offset_y: int = -6

    # ---- 其它 ----
    enable_tray: bool = True                    # 显示托盘图标
    open_settings_on_start: bool = True          # 启动就直接打开设置台

    # 加载时被清掉的旧版文字表情数量（临时值，不写进文件）
    dropped_items: int = field(default=0, compare=False, repr=False)

    # ------------------------------------------------------------------
    @property
    def symbols(self) -> List[dict]:
        """兼容旧叫法：表情列表。"""
        return self.items

    @property
    def count(self) -> int:
        return len(self.items)

    @property
    def has_items(self) -> bool:
        return bool(self.items)

    @property
    def current(self) -> dict:
        """当前选中的表情；一个都没有时返回空 dict。"""
        if not self.items:
            return {}
        self.current_index %= len(self.items)
        return self.items[self.current_index]

    @property
    def symbol(self) -> dict:
        """兼容旧叫法。"""
        return self.current

    @property
    def current_text(self) -> str:
        return item_text(self.current) if self.items else "（还没有表情）"

    def cycle(self, delta: int = 1) -> str:
        """滚轮切换表情，返回切换后的显示文字。"""
        if self.items:
            self.current_index = (self.current_index + delta) % len(self.items)
        return self.current_text

    def select(self, index: int) -> dict:
        if self.items:
            self.current_index = max(0, min(len(self.items) - 1, int(index)))
        return self.current

    def add_item(self, item, index: int | None = None) -> dict:
        entry = normalize_item(item)
        if index is None:
            self.items.append(entry)
            self.current_index = len(self.items) - 1
        else:
            self.items.insert(index, entry)
            self.current_index = index
        return entry

    def add_items(self, values) -> int:
        added = 0
        for value in values:
            self.items.append(normalize_item(value))
            added += 1
        if added:
            self.current_index = len(self.items) - 1
        return added

    def remove_item(self, index: int) -> None:
        if 0 <= index < len(self.items):
            self.items.pop(index)
            self.current_index = max(0, min(self.current_index, len(self.items) - 1))

    def move_item(self, index: int, delta: int) -> int:
        target = index + delta
        if 0 <= index < len(self.items) and 0 <= target < len(self.items):
            self.items[index], self.items[target] = self.items[target], self.items[index]
            self.current_index = target
            return target
        return index

    def clone(self) -> "Config":
        return copy.deepcopy(self)

    def copy_from(self, other: "Config") -> None:
        """把另一份配置的值拷回自己（保持对象身份不变）。"""
        for f in fields(self):
            setattr(self, f.name, copy.deepcopy(getattr(other, f.name)))

    # ------------------------------------------------------------------
    @classmethod
    def load(cls, path: str) -> "Config":
        set_base_dir(os.path.dirname(os.path.abspath(path)))
        cfg = cls()
        data: dict[str, Any] = {}
        try:
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            if not isinstance(data, dict):
                data = {}
        except Exception as exc:
            print("[配置] 读取 %s 失败，改用默认配置：%s" % (path, exc))
            data = {}

        known = {f.name for f in fields(cls)}

        # 兼容旧版本：symbols 是"文字表情"数组，现在只支持图片，这里把它们清掉
        raw_items = data.get("items", data.get("symbols"))
        if isinstance(raw_items, (list, tuple)):
            kept, dropped = [], 0
            for value in raw_items:
                item = normalize_item(value)
                if item["image"]:
                    kept.append(item)
                else:
                    dropped += 1
            cfg.items = kept
            cfg.dropped_items = dropped

        for key, value in data.items():
            if key in known and key != "items":
                setattr(cfg, key, value)
        cfg.validate()
        cfg.save(path)
        return cfg

    def save(self, path: str) -> None:
        try:
            data = asdict(self)
            data.pop("dropped_items", None)      # 临时值不落盘
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
        except Exception as exc:
            print("[配置] 写入 %s 失败：%s" % (path, exc))

    # ------------------------------------------------------------------
    def validate(self) -> None:
        raw = self.items if isinstance(self.items, (list, tuple)) else []
        self.items = [normalize_item(value, index) for index, value in enumerate(raw)]
        if self.items:
            self.current_index = self._int(self.current_index, 0, 0, len(self.items) - 1)
        else:
            self.current_index = 0

        self.size = self._int(self.size, 96, 8, 800)
        self.duration_ms = self._int(self.duration_ms, 3000, 100, 600000)
        self.fade_ms = self._int(self.fade_ms, 700, 0, 30000)
        self.offset_x = self._int(self.offset_x, 0, -2000, 2000)
        self.offset_y = self._int(self.offset_y, -6, -2000, 2000)
        self.hint_font_size = self._int(self.hint_font_size, 14, 8, 60)
        self.hint_thumb_size = self._int(self.hint_thumb_size, 40, 16, 200)
        self.sound_min_interval_ms = self._int(self.sound_min_interval_ms, 60, 0, 5000)

        try:
            volume = float(self.sound_volume)
        except (TypeError, ValueError):
            volume = 0.7
        self.sound_volume = max(0.0, min(1.0, volume))

        for name in ("consume_click", "stay_armed", "swallow_hotkey", "cycle_on_wheel",
                     "show_hint", "sound_enabled", "enable_tray", "open_settings_on_start"):
            setattr(self, name, self._bool(getattr(self, name)))

        if self.hotkey_mode not in ("toggle", "hold"):
            self.hotkey_mode = "toggle"
        if not str(self.transparent_color).strip():
            self.transparent_color = "#FF00FF"

        for name in ("hotkey", "exit_hotkey", "settings_hotkey", "mute_hotkey",
                     "default_sound"):
            setattr(self, name, str(getattr(self, name) or "").strip())

    @staticmethod
    def _int(value, default: int, low: int, high: int) -> int:
        try:
            value = int(value)
        except (TypeError, ValueError):
            return default
        return max(low, min(high, value))

    @staticmethod
    def _bool(value) -> bool:
        # 允许 "false" / "0" / "no" 这类字符串写法
        if isinstance(value, str):
            return value.strip().lower() not in ("", "0", "false", "no", "off", "none")
        return bool(value)


# ----------------------------------------------------------------------
# 表情项的辅助函数（设置台和渲染都用）
# ----------------------------------------------------------------------
def item_text(item: dict) -> str:
    """列表里显示的短名。"""
    if not isinstance(item, dict):
        return str(item)
    image = str(item.get("image") or "")
    if not image:
        return "（缺图片）"
    return os.path.basename(image)


def item_title(item: dict, index: int = 0) -> str:
    """列表里显示的标题。"""
    if not isinstance(item, dict):
        return str(item)
    if item.get("label"):
        return str(item["label"])
    return item_text(item)


def item_ready(item: dict) -> bool:
    """这个表情能不能用（有图片且文件存在）。"""
    if not isinstance(item, dict) or not item.get("image"):
        return False
    return os.path.isfile(resolve_image(item["image"]))
