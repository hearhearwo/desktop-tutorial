# -*- coding: utf-8 -*-
"""置顶悬浮层：在鼠标点击位置显示你的图片（含 GIF 动图），3 秒后淡出消失。

设计要点
--------
* 每个表情是一个独立的、无边框的置顶 Toplevel：位置互不影响，
  所以多个表情可以同时处在不同的淡出阶段。
* 窗口背景色 = "透明色键"（-transparentcolor），只有图片本体可见。
* 淡出用窗口整体透明度（-alpha）实现，同时保留色键。
  两者的兼容性在启动时探测一次（见 probe_layer_mode），
  万一当前 Tk 版本不支持共存，就退化成"到点直接消失"。
* 窗口带 WS_EX_TRANSPARENT / WS_EX_NOACTIVATE，点击穿透、不抢焦点。
* 程序不画任何自带图形：没有可用图片就不显示，绝不生成占位图案。
"""
from __future__ import annotations

import tkinter as tk

import images
import winapi
from config import normalize_item, resolve_image


def _layered_flags(window: tk.Misc) -> int:
    """读取窗口的分层属性标志位；Tk 可能把属性设在包装窗口上，逐个试。"""
    try:
        for handle in winapi.window_chain(window.winfo_id()):
            flags, _key, _alpha = winapi.get_layered_attributes(handle)
            if flags:
                return flags
    except tk.TclError:
        pass
    return 0


def probe_layer_mode(root: tk.Misc, key: str) -> str:
    """探测当前 Tk 能否同时使用色键透明与整体 alpha。

    返回 "alpha+key"（最优，可淡出）/ "key"（只透明，不淡出）/ "none"。
    探测窗口是 1×1 且放在屏幕外，随后立即销毁。
    """
    top = tk.Toplevel(root)
    mode = "none"
    try:
        top.withdraw()
        top.overrideredirect(True)
        top.configure(bg=key)
        top.geometry("1x1-30000-30000")   # 挪到屏幕外，避免闪一下
        top.attributes("-transparentcolor", key)
        top.attributes("-alpha", 0.5)
        top.deiconify()
        top.update()                      # 确保窗口已建立并应用属性

        flags = _layered_flags(top)
        if flags & winapi.LWA_COLORKEY and flags & winapi.LWA_ALPHA:
            mode = "alpha+key"
        elif flags & winapi.LWA_COLORKEY:
            mode = "key"
        else:
            # 色键可能被 alpha 覆盖了，换个顺序再试一次
            top.attributes("-alpha", 1.0)
            top.attributes("-transparentcolor", key)
            top.update_idletasks()
            flags = _layered_flags(top)
            mode = "key" if flags & winapi.LWA_COLORKEY else "none"
    except tk.TclError as exc:
        print("[悬浮层] 分层窗口探测失败：%s" % exc)
    finally:
        try:
            top.destroy()
        except Exception:
            pass
    return mode


class FloatingLayer:
    """管理所有表情窗口与提示条（只能在 Tk 主线程里使用）。"""

    def __init__(self, root: tk.Tk, cfg):
        self.root = root
        self.cfg = cfg
        self.windows: list[PingWindow] = []
        self._images: dict = {}
        self.mode = probe_layer_mode(root, cfg.transparent_color)
        self.hint = HintWindow(self)

    # ------------------------------------------------------------------
    def image_for(self, path: str, size_px: int):
        """加载并缩放图片（GIF 会读入全部帧），带缓存；失败返回 None。"""
        if not path:
            return None
        resolved = resolve_image(path)
        key = (resolved, int(size_px))
        if key not in self._images:
            try:
                self._images[key] = images.load_image_asset(self.root, resolved, int(size_px))
            except Exception as exc:
                print("[悬浮层] 图片加载失败：%s（%s）" % (resolved, exc))
                self._images[key] = None
        return self._images[key]

    def ping(self, x: int, y: int, item=None) -> "PingWindow | None":
        """在 (x, y) 放一个表情；没有可用图片就返回 None（不画任何占位图形）。"""
        if item is None:
            item = self.cfg.current
        if not isinstance(item, dict):
            item = {"image": str(item)}
        item = normalize_item(item)
        size = int(item["size"] or 0) or int(self.cfg.size)
        asset = self.image_for(item["image"], size)
        if asset is None:
            return None
        window = PingWindow(self, x, y, item, asset)
        self.windows.append(window)
        window.start()
        return window

    def forget(self, window: "PingWindow") -> None:
        if window in self.windows:
            self.windows.remove(window)

    def clear(self) -> None:
        for window in list(self.windows):
            window.destroy()


class PingWindow:
    """一个表情窗口的完整生命周期：弹出 → 停留 → 淡出 → 销毁。"""

    INITIAL_ALPHA = 0.35
    POP_STEPS = 3
    POP_INTERVAL_MS = 28

    def __init__(self, layer: FloatingLayer, x: int, y: int, item: dict, asset):
        cfg = layer.cfg
        self.layer = layer
        self.cfg = cfg
        self.item = item
        self.image_path = item["image"]
        self.asset = asset
        self.mode = layer.mode
        self._alive = True
        self._timer = None
        self._anim_timer = None

        pad = max(4, int(cfg.size) // 12)
        self.width = max(16, asset.width() + pad * 2)
        self.height = max(16, asset.height() + pad * 2)
        # 极少数情况下透明层不可用，退化成一个深色小方块，至少不是刺眼的纯色
        self.bg = cfg.transparent_color if self.mode != "none" else "#141414"

        self.top = tk.Toplevel(layer.root)
        self.top.withdraw()
        self.top.overrideredirect(True)
        try:
            self.top.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.top.configure(bg=self.bg)

        self.label = tk.Label(self.top, image=asset.frames[0], bg=self.bg,
                              bd=0, highlightthickness=0, padx=0, pady=0)
        self.label.place(relx=0.5, rely=0.5, anchor="center")

        # 让图片中心对准鼠标点击点
        px = int(x) - self.width // 2 + cfg.offset_x
        py = int(y) - self.height // 2 + cfg.offset_y
        self.top.geometry("%dx%d+%d+%d" % (self.width, self.height, px, py))

        self._apply_layering()
        self.top.deiconify()
        try:
            self.top.lift()
        except tk.TclError:
            pass
        # 改扩展样式有可能重置分层属性，所以之后再补设一次透明属性
        winapi.make_click_through(winapi.root_hwnd(self.top.winfo_id()))
        self._apply_layering()

    # ------------------------------------------------------------------
    @property
    def photo(self):
        """当前显示的第一帧。"""
        return self.asset.frames[0]

    def _apply_layering(self) -> None:
        if self.mode == "none":
            return
        key = self.cfg.transparent_color
        try:
            if self.mode == "alpha+key":
                # 顺序与探测一致：先色键，后 alpha
                self.top.attributes("-transparentcolor", key)
                self.top.attributes("-alpha", self.INITIAL_ALPHA)
            else:
                self.top.attributes("-alpha", 1.0)
                self.top.attributes("-transparentcolor", key)
        except tk.TclError as exc:
            print("[悬浮层] 设置透明属性失败：%s" % exc)

    def set_alpha(self, value: float) -> None:
        if self.mode != "alpha+key":
            return
        try:
            self.top.attributes("-alpha", max(0.0, min(1.0, float(value))))
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    def start(self) -> None:
        self._start_animation()
        self._schedule(0, self._pop, 0)

    def _start_animation(self) -> None:
        """GIF 动图：按每一帧自己的延时循环播放，直到窗口消失。"""
        if self.asset.animated:
            self._animate(1)

    def _animate(self, index: int) -> None:
        if not self._alive:
            return
        frames = self.asset.frames
        try:
            self.label.configure(image=frames[index % len(frames)])
        except tk.TclError:
            return
        try:
            self._anim_timer = self.top.after(self.asset.delay(index), self._animate, index + 1)
        except tk.TclError:
            self._alive = False

    def _pop(self, step: int) -> None:
        """快速弹出（轻微淡入），让表情出现得更自然。"""
        if not self._alive:
            return
        steps = self.POP_STEPS
        span = 1.0 - self.INITIAL_ALPHA
        self.set_alpha(self.INITIAL_ALPHA + span * (step + 1) / steps)
        if step + 1 < steps:
            self._schedule(self.POP_INTERVAL_MS, self._pop, step + 1)
        else:
            self._schedule(max(0, int(self.cfg.duration_ms)), self._fade, 0)

    def _fade(self, step: int) -> None:
        """停留结束后淡出消失。"""
        if not self._alive:
            return
        if self.cfg.fade_ms <= 0:
            self.destroy()
            return
        steps = max(6, int(self.cfg.fade_ms / 33))
        if step > steps:
            self.destroy()
            return
        self.set_alpha(1.0 - step / steps)
        self._schedule(33, self._fade, step + 1)

    def _schedule(self, delay_ms: int, func, *args) -> None:
        if not self._alive:
            return
        try:
            self._timer = self.top.after(int(delay_ms), func, *args)
        except tk.TclError:
            self._alive = False

    def destroy(self) -> None:
        if not self._alive:
            return
        self._alive = False
        for attribute in ("_timer", "_anim_timer"):
            timer = getattr(self, attribute)
            if timer is not None:
                try:
                    self.top.after_cancel(timer)
                except Exception:
                    pass
                setattr(self, attribute, None)
        try:
            self.top.destroy()
        except Exception:
            pass
        self.layer.forget(self)


class HintWindow:
    """「待放置」状态下跟随鼠标的提示条：显示当前表情缩略图 + 操作说明。"""

    OFFSET_X = 18
    OFFSET_Y = 24

    def __init__(self, layer: FloatingLayer):
        self.layer = layer
        self.top = tk.Toplevel(layer.root)
        self.top.withdraw()
        self.top.overrideredirect(True)
        try:
            self.top.attributes("-topmost", True)
            self.top.attributes("-alpha", 0.94)
        except tk.TclError:
            pass

        self.frame = tk.Frame(self.top, bg="#242424", bd=0, highlightthickness=1,
                              highlightbackground="#4A4A4A")
        self.frame.pack(fill="both", expand=True)

        self.thumb = tk.Label(self.frame, bg="#242424", fg="#BBBBBB",
                              font=("Microsoft YaHei UI", -12), padx=0, pady=0)
        self.thumb.pack(side="left", padx=(10, 6), pady=6)
        self.thumb_image = None

        self.text_label = tk.Label(self.frame, text="左键放置 · 滚轮切换 · 右键/Esc 取消",
                                   bg="#242424", fg="#E8E8E8",
                                   font=("Microsoft YaHei UI", -int(layer.cfg.hint_font_size)),
                                   padx=0, pady=0)
        self.text_label.pack(side="left", padx=(0, 12), pady=6)

        self._visible = False
        self._alive = True
        self._timer = None
        self._follow()

    def show(self, item=None) -> None:
        """显示提示条。item 为空或没有图片时，提示"还没有表情"。"""
        if not self._alive:
            return
        self.update_item(item)
        self._visible = True
        try:
            self.top.deiconify()
            self.top.lift()
        except tk.TclError:
            return
        winapi.make_click_through(winapi.root_hwnd(self.top.winfo_id()))
        try:
            # 改样式可能重置整体透明度，补设一次
            self.top.attributes("-alpha", 0.94)
        except tk.TclError:
            pass

    def update_item(self, item=None) -> None:
        """换成另一个表情的缩略图。"""
        if not self._alive:
            return
        cfg = self.layer.cfg
        asset = None
        if isinstance(item, dict) and item.get("image"):
            asset = self.layer.image_for(item["image"], int(cfg.hint_thumb_size))
        self.thumb_image = asset.frames[0] if asset is not None else None
        if self.thumb_image is not None:
            self.thumb.configure(image=self.thumb_image, text="")
            self.text_label.configure(text="左键放置 · 滚轮切换 · 右键/Esc 取消")
        else:
            self.thumb.configure(image="", text="（没有图片）")
            self.text_label.configure(text="打开设置台添加图片（Ctrl+Alt+S）")

    def hide(self) -> None:
        if not self._alive:
            return
        self._visible = False
        try:
            self.top.withdraw()
        except tk.TclError:
            pass

    def destroy(self) -> None:
        self._alive = False
        if self._timer is not None:
            try:
                self.top.after_cancel(self._timer)
            except Exception:
                pass
            self._timer = None
        try:
            self.top.destroy()
        except Exception:
            pass

    def _follow(self) -> None:
        """每 30ms 把提示条挪到鼠标右下方。"""
        if not self._alive:
            return
        if self._visible:
            try:
                self.top.update_idletasks()
                x, y = winapi.get_cursor_pos()
                vx, vy, vw, vh = winapi.virtual_screen()
                w = max(self.top.winfo_reqwidth(), self.top.winfo_width())
                h = max(self.top.winfo_reqheight(), self.top.winfo_height())
                px = min(max(x + self.OFFSET_X, vx), vx + vw - w)
                py = min(max(y + self.OFFSET_Y, vy), vy + vh - h)
                self.top.geometry("+%d+%d" % (px, py))
            except tk.TclError:
                pass
        try:
            self._timer = self.top.after(30, self._follow)
        except tk.TclError:
            self._alive = False
