# -*- coding: utf-8 -*-
"""设置窗口：管理表情（符号 / 图片 / 每个表情的音效）和全局选项。

分两个标签页：「表情」管列表和单个表情的属性，「选项」管快捷键与全局行为。
改完点「保存并应用」即时生效（快捷键变了会自动重装钩子）。
"""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import audio
import config as config_mod
import images
from config import Config, item_title
from hotkeys import Hotkey

SILENT = "none"


class SettingsWindow:
    """设置窗口。app 需要提供 cfg / icon_path / apply_settings / test_ping / start_hotkey_record。"""

    def __init__(self, app):
        self.app = app
        self.cfg: Config = app.cfg.clone()
        self.top = tk.Toplevel(app.root)
        self.top.title("桌面表情 Ping · 设置")
        self.top.protocol("WM_DELETE_WINDOW", self.close)
        try:
            if app.icon_path:
                self.top.iconbitmap(app.icon_path)
        except tk.TclError:
            pass

        self._loading = False
        self._index = 0
        self._sound_map = {}
        self._record_buttons = {}
        self._preview_timer = None
        self._preview_asset = None
        self._preview_index = 0

        self._build()
        self._refresh_list()
        self._load_globals()
        self.select(0)
        self.refresh_status()

        # 按内容算最小尺寸，避免面板互相压盖
        self.top.update_idletasks()
        width = max(900, self.top.winfo_reqwidth() + 24)
        height = max(620, self.top.winfo_reqheight() + 24)
        self.top.minsize(width, height)
        self.top.geometry("%dx%d" % (width, height))

    # ==================================================================
    # 界面搭建
    # ==================================================================
    def _build(self) -> None:
        root = ttk.Frame(self.top, padding=10)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        book = ttk.Notebook(root)
        self.book = book
        book.grid(row=0, column=0, sticky="nsew")

        page1 = ttk.Frame(book, padding=10)
        book.add(page1, text="  表情  ")
        page1.columnconfigure(0, weight=1, minsize=330)
        page1.columnconfigure(1, weight=1)
        page1.rowconfigure(0, weight=1)

        page2 = ttk.Frame(book, padding=10)
        book.add(page2, text="  选项  ")
        page2.columnconfigure(0, weight=1)

        # ---------------- 页 1：表情列表 ----------------
        left = ttk.LabelFrame(page1, text=" 表情列表（滚轮切换的顺序） ", padding=8)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(left, columns=("kind", "sound"), show="tree headings",
                                 selectmode="browse", height=8)
        self.tree.heading("#0", text="表情")
        self.tree.heading("kind", text="类型")
        self.tree.heading("sound", text="音效")
        self.tree.column("#0", width=150, anchor="w")
        self.tree.column("kind", width=76, anchor="center", stretch=False)
        self.tree.column("sound", width=170, anchor="w", stretch=False)
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)

        buttons = ttk.Frame(left)
        buttons.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        actions = (("添加图片", self.add_image), ("添加文件夹", self.add_folder), ("删除", self.remove),
                   ("上移", lambda: self.move(-1)), ("下移", lambda: self.move(1)), ("测试", self.test))
        for index, (text, command) in enumerate(actions):
            row, column = divmod(index, 3)
            ttk.Button(buttons, text=text, command=command, width=10).grid(
                row=row, column=column, padx=2, pady=2, sticky="ew")
        for column in range(3):
            buttons.columnconfigure(column, weight=1)

        # ---------------- 页 1：单个表情 ----------------
        item = ttk.LabelFrame(page1, text=" 选中的表情 ", padding=8)
        item.grid(row=0, column=1, sticky="nsew")
        item.columnconfigure(1, weight=1)

        self.var_image = tk.StringVar()
        self.var_sound = tk.StringVar()
        self.var_size = tk.StringVar()
        self.var_label = tk.StringVar()
        for var in (self.var_image, self.var_sound, self.var_size, self.var_label):
            var.trace_add("write", self._on_form_changed)

        ttk.Label(item, text="图片 / 动图").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(item, textvariable=self.var_image, width=1).grid(
            row=0, column=1, sticky="ew", pady=3)
        ttk.Button(item, text="选图…", width=8, command=self.pick_image).grid(row=0, column=2, padx=4)
        ttk.Button(item, text="清除", width=6,
                   command=lambda: self.var_image.set("")).grid(row=0, column=3)

        ttk.Label(item, text="音效文件").grid(row=1, column=0, sticky="w", pady=3)
        self.cmb_sound = ttk.Combobox(item, textvariable=self.var_sound, state="readonly", width=1)
        self.cmb_sound.grid(row=1, column=1, sticky="ew", pady=3)
        ttk.Button(item, text="试听", width=8, command=self.preview_sound).grid(row=1, column=2, padx=4)
        ttk.Button(item, text="选文件", width=8, command=self.pick_sound).grid(row=1, column=3)

        ttk.Label(item, text="单独大小").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Spinbox(item, from_=0, to=800, width=8, textvariable=self.var_size).grid(
            row=2, column=1, sticky="w", pady=3)
        ttk.Label(item, text="0 = 跟随全局（像素）").grid(row=2, column=2, columnspan=2, sticky="w")

        ttk.Label(item, text="列表名称").grid(row=3, column=0, sticky="w", pady=3)
        ttk.Entry(item, textvariable=self.var_label, width=1).grid(
            row=3, column=1, columnspan=3, sticky="ew", pady=3)

        ttk.Label(item, text="预览").grid(row=4, column=0, sticky="nw", pady=(8, 0))
        preview_box = ttk.Frame(item)
        preview_box.grid(row=4, column=1, columnspan=3, sticky="w", pady=(8, 0))
        self.preview = tk.Label(preview_box, text="", bg="#F3F3F3", fg="#202020",
                                relief="solid", borderwidth=1)
        self.preview.pack(side="left")
        self.preview_image = None
        self.var_preview_note = tk.StringVar()
        ttk.Label(preview_box, textvariable=self.var_preview_note, foreground="#666666").pack(
            side="left", padx=8)

        # ---------------- 页 2：快捷键 ----------------
        keys = ttk.LabelFrame(page2, text=" 快捷键（点「录制」后直接按组合键） ", padding=8)
        keys.grid(row=0, column=0, sticky="ew")

        self.var_hotkeys = {
            "hotkey": tk.StringVar(), "settings_hotkey": tk.StringVar(),
            "mute_hotkey": tk.StringVar(), "exit_hotkey": tk.StringVar(),
        }
        rows = (("hotkey", "放置表情"), ("settings_hotkey", "打开设置"),
                ("mute_hotkey", "静音开关"), ("exit_hotkey", "退出程序"))
        for index, (key, title) in enumerate(rows):
            row, column = divmod(index, 2)
            base = column * 5
            ttk.Label(keys, text=title, width=9).grid(row=row, column=base, sticky="w", pady=3)
            ttk.Entry(keys, textvariable=self.var_hotkeys[key], state="readonly",
                      width=16).grid(row=row, column=base + 1, sticky="w", pady=3)
            button = ttk.Button(keys, text="录制…", width=8,
                                command=lambda k=key: self.record_hotkey(k))
            button.grid(row=row, column=base + 2, padx=6, pady=3)
            self._record_buttons[key] = button
            ttk.Button(keys, text="清除", width=6,
                       command=lambda k=key: self.var_hotkeys[k].set("")).grid(
                row=row, column=base + 3, sticky="w", pady=3)
            keys.columnconfigure(base + 4, weight=1)   # 每组的最后一列吃掉多余宽度

        # ---------------- 页 2：外观与行为 ----------------
        misc = ttk.LabelFrame(page2, text=" 外观与行为 ", padding=8)
        misc.grid(row=1, column=0, sticky="ew", pady=(10, 0))

        self.var_number = {}
        fields = (("表情尺寸(px)", "size"), ("停留(ms)", "duration_ms"), ("淡出(ms)", "fade_ms"),
                  ("音量(0-1)", "sound_volume"), ("提示字号", "hint_font_size"))
        for index, (title, key) in enumerate(fields):
            row, column = divmod(index, 2)
            var = tk.StringVar()
            self.var_number[key] = var
            ttk.Label(misc, text=title).grid(row=row, column=column * 2, sticky="w", pady=3)
            spin = ttk.Spinbox(misc, width=8, textvariable=var)
            if key == "sound_volume":
                spin.configure(from_=0, to=1, increment=0.1)
            elif key == "hint_font_size":
                spin.configure(from_=8, to=60)
            else:
                spin.configure(from_=0, to=600000)
            spin.grid(row=row, column=column * 2 + 1, sticky="w", padx=(6, 24), pady=3)

        ttk.Label(misc, text="触发方式").grid(row=3, column=0, sticky="w", pady=3)
        self.var_mode = tk.StringVar()
        ttk.Combobox(misc, textvariable=self.var_mode, state="readonly", width=18,
                     values=("toggle（按一下）", "hold（按住）")).grid(
            row=3, column=1, columnspan=3, sticky="w", padx=(6, 0), pady=3)

        checks = ttk.Frame(misc)
        checks.grid(row=4, column=0, columnspan=4, sticky="w", pady=(8, 0))
        self.var_checks = {}
        options = (("sound_enabled", "启用音效"), ("consume_click", "吞掉那次点击"),
                   ("stay_armed", "放完继续待放置"), ("cycle_on_wheel", "滚轮切换"),
                   ("show_hint", "鼠标提示条"), ("enable_tray", "托盘图标"),
                   ("open_settings_on_start", "启动时打开本窗口"))
        for index, (key, title) in enumerate(options):
            var = tk.BooleanVar()
            self.var_checks[key] = var
            ttk.Checkbutton(checks, text=title, variable=var).grid(
                row=index // 3, column=index % 3, sticky="w", padx=(0, 16), pady=2)

        # ---------------- 底部按钮 ----------------
        status = ttk.Frame(root)
        status.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.var_app_status = tk.StringVar(value="")
        ttk.Label(status, textvariable=self.var_app_status,
                  foreground="#1F6F3F").pack(side="left")
        ttk.Button(status, text="退出程序", width=10,
                   command=self.quit_app).pack(side="right")
        self.btn_mute = ttk.Button(status, text="静音", width=10, command=self.toggle_mute)
        self.btn_mute.pack(side="right", padx=6)
        self.btn_pause = ttk.Button(status, text="暂停监听", width=10, command=self.toggle_pause)
        self.btn_pause.pack(side="right")

        bottom = ttk.Frame(root)
        bottom.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(bottom, text="关闭", width=10, command=self.close).pack(side="right")
        ttk.Button(bottom, text="重新载入", width=10, command=self.reload).pack(side="right", padx=6)
        ttk.Button(bottom, text="保存并应用", width=12, command=self.save).pack(side="right")
        ttk.Button(bottom, text="打开素材夹", width=12,
                   command=self.open_assets).pack(side="left")
        self.var_status = tk.StringVar(
            value="图片会自动复制到「%s」文件夹，GIF 会当作动图播放" % config_mod.ASSETS_DIRNAME)
        ttk.Label(bottom, textvariable=self.var_status, foreground="#3366AA").pack(
            side="left", fill="x", expand=True, padx=10)

    # ==================================================================
    # 列表
    # ==================================================================
    def _refresh_list(self, keep: int | None = None) -> None:
        selected = self._index if keep is None else keep
        self.tree.delete(*self.tree.get_children())
        for index, item in enumerate(self.cfg.items):
            self.tree.insert("", "end", iid=str(index),
                             text="%d. %s" % (index + 1, item_title(item, index)),
                             values=("图片" if config_mod.item_ready(item) else "缺图片",
                                     audio.describe(item.get("sound"), self.cfg.default_sound)))
        if not self.cfg.items:
            self.var_status.set("还没有表情：点「添加图片」或「添加文件夹」把你的图片加进来"
                                "（会自动复制到「%s」）" % config_mod.ASSETS_DIRNAME)
        if self.cfg.items:
            self.select(min(max(0, selected), len(self.cfg.items) - 1))

    def select(self, index: int) -> None:
        if not self.cfg.items:
            return
        index = min(max(0, index), len(self.cfg.items) - 1)
        self._index = index
        self.tree.selection_set(str(index))
        self.tree.see(str(index))
        self._load_item()
        self.cfg.current_index = index

    def _on_select(self, _event=None) -> None:
        selection = self.tree.selection()
        if selection:
            self._index = int(selection[0])
            self.cfg.current_index = self._index
            self._load_item()

    # ==================================================================
    # 表单 ←→ 表情项
    # ==================================================================
    def _load_item(self) -> None:
        if not self.cfg.items:
            return
        item = self.cfg.items[self._index]
        self._loading = True
        try:
            self.var_image.set(item.get("image", ""))
            self.var_size.set(str(item.get("size", 0)))
            self.var_label.set(item.get("label", ""))
            self._refresh_sound_choices(item.get("sound", ""))
        finally:
            self._loading = False
        self._update_preview()

    def _refresh_sound_choices(self, current: str) -> None:
        # 音效来源只有"你自己的文件"：要么指一个文件，要么留空（不出声 / 跟随默认）
        self._sound_map = {"无音效": SILENT, "跟随默认": ""}
        if self.cfg.default_sound:
            self._sound_map["跟随默认"] = self.cfg.default_sound
        text = None
        for label, value in self._sound_map.items():
            if value == current:
                text = label
                break
        if text is None:
            if current:
                text = "文件：%s" % os.path.basename(current)
                self._sound_map[text] = current
            else:
                text = "无音效"
        self.cmb_sound.configure(values=list(self._sound_map))
        self.var_sound.set(text)

    def _on_form_changed(self, *_args) -> None:
        if self._loading or not self.cfg.items:
            return
        item = self.cfg.items[self._index]
        item["image"] = self.var_image.get().strip()
        item["label"] = self.var_label.get().strip()
        try:
            item["size"] = max(0, min(800, int(float(self.var_size.get() or 0))))
        except ValueError:
            item["size"] = 0
        item["sound"] = self._sound_map.get(self.var_sound.get(), item.get("sound", ""))
        index = self._index
        self.tree.item(str(index), text="%d. %s" % (index + 1, item_title(item, index)),
                       values=("图片" if config_mod.item_ready(item) else "缺图片",
                               audio.describe(item["sound"], self.cfg.default_sound)))
        self._update_preview()

    def _update_preview(self) -> None:
        if not self.cfg.items:
            self._stop_preview_animation()
            self.preview.configure(image="", text="？", width=4, height=2,
                                   fg="#999999", font=("Microsoft YaHei UI", 14))
            self.var_preview_note.set("还没有表情，先「添加图片」")
            return
        self.preview.configure(image="", text="")
        self.preview_image = None
        self._stop_preview_animation()
        item = self.cfg.items[self._index]
        raw = item.get("image", "")
        path = config_mod.resolve_image(raw) if raw else ""
        if path and os.path.isfile(path):
            try:
                asset = images.load_image_asset(self.top, path, 64)
            except Exception:
                self.var_preview_note.set("读不了这张图：建议用 PNG / GIF（JPG 需要 pip install pillow）")
                return
            self._preview_asset = asset
            self._preview_index = 0
            self.preview_image = asset.frames[0]
            # width/height 设成 0 才会按图片自身大小显示，否则会被裁掉
            self.preview.configure(image=asset.frames[0], text="",
                                   width=0, height=0, bg="#F3F3F3")
            kind = "动图（%d 帧）" % len(asset.frames) if asset.animated else "图片表情"
            self.var_preview_note.set("%s · %s" % (kind, os.path.basename(path)))
            if asset.animated:
                self._preview_timer = self.top.after(asset.delay(0) * 3, self._preview_tick)
            return
        if path:
            self.var_preview_note.set("找不到这张图片：%s（相对路径会在程序目录和「%s」里找）"
                                      % (raw, config_mod.ASSETS_DIRNAME))
        else:
            self.var_preview_note.set("这个表情还没选图片")
        self.preview.configure(text="（缺图）", image="", width=8, height=2,
                               fg="#999999", font=("Microsoft YaHei UI", 12))

    def _stop_preview_animation(self) -> None:
        if self._preview_timer is not None:
            try:
                self.top.after_cancel(self._preview_timer)
            except Exception:
                pass
            self._preview_timer = None
        self._preview_asset = None

    def _preview_tick(self) -> None:
        asset = self._preview_asset
        if asset is None or not self.top.winfo_exists():
            self._preview_timer = None
            return
        frames = asset.frames
        self._preview_index += 1
        frame = frames[self._preview_index % len(frames)]
        try:
            self.preview.configure(image=frame, text="", width=0, height=0)
            self.preview_image = frame
            self._preview_timer = self.top.after(asset.delay(self._preview_index),
                                                 self._preview_tick)
        except tk.TclError:
            self._preview_timer = None

    # ==================================================================
    # 列表操作
    # ==================================================================
    def add_symbol(self) -> None:
        """兼容旧按钮名（现在只支持图片）。"""
        self.add_image()

    def add_image(self) -> None:
        patterns = " ".join("*" + ext for ext in config_mod.IMAGE_EXTS)
        paths = filedialog.askopenfilenames(
            parent=self.top, title="选择图片 / 动图（可多选）",
            filetypes=[("图片", patterns), ("所有文件", "*.*")])
        if not paths:
            return
        for path in paths:
            self.cfg.add_item({"image": config_mod.import_asset(path), "sound": ""})
        self._refresh_list(keep=len(self.cfg.items) - 1)
        self.var_status.set("已把 %d 个文件复制到「%s」，点「保存并应用」生效"
                            % (len(paths), config_mod.ASSETS_DIRNAME))

    def add_folder(self) -> None:
        """把一个文件夹里的图片全部加进来（不会递归子目录）。"""
        folder = filedialog.askdirectory(parent=self.top, title="选择装满图片的文件夹")
        if not folder:
            return
        files = config_mod.iter_image_files(folder)
        if not files:
            messagebox.showinfo("没找到图片",
                                "这个文件夹里没有可用的图片（支持 %s）"
                                % "、".join(ext.lstrip(".") for ext in config_mod.IMAGE_EXTS),
                                parent=self.top)
            return
        for path in files:
            self.cfg.add_item({"image": config_mod.import_asset(path), "sound": ""})
        self._refresh_list(keep=len(self.cfg.items) - 1)
        self.var_status.set("已从文件夹加入 %d 个图片到「%s」，点「保存并应用」生效"
                            % (len(files), config_mod.ASSETS_DIRNAME))

    def pick_image(self) -> None:
        patterns = " ".join("*" + ext for ext in config_mod.IMAGE_EXTS)
        path = filedialog.askopenfilename(
            parent=self.top, title="选择图片 / 动图",
            filetypes=[("图片", patterns), ("所有文件", "*.*")])
        if path:
            self.var_image.set(config_mod.import_asset(path))
            self.var_status.set("已复制到「%s」文件夹" % config_mod.ASSETS_DIRNAME)

    def remove(self) -> None:
        if not self.cfg.items:
            return
        if len(self.cfg.items) == 1:
            messagebox.showinfo("提示", "这是最后一个表情了，删掉就没得放了。", parent=self.top)
            return
        self.cfg.remove_item(self._index)
        self._refresh_list(keep=self._index)

    def move(self, delta: int) -> None:
        new_index = self.cfg.move_item(self._index, delta)
        self._refresh_list(keep=new_index)

    def test(self) -> None:
        if self.cfg.items:
            self.app.test_ping(self.cfg.items[self._index], self.cfg)

    # ==================================================================
    # 音效
    # ==================================================================
    def preview_sound(self) -> None:
        spec = self._sound_map.get(self.var_sound.get(), "")
        error = audio.play(spec, self._volume(), self.cfg.default_sound)
        self.var_status.set(error or ("试听：" + audio.describe(spec, self.cfg.default_sound)))

    def pick_sound(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.top, title="选择音效文件",
            filetypes=[("音频", "*.wav *.mp3 *.m4a *.wma *.aac"), ("所有文件", "*.*")])
        if not path:
            return
        value = os.path.normpath(path)
        label = "文件：%s" % os.path.basename(value)
        self._sound_map[label] = value
        self.cmb_sound.configure(values=list(self._sound_map))
        self._loading = True
        self.var_sound.set(label)
        self._loading = False
        self._on_form_changed()

    def _volume(self) -> float:
        try:
            return max(0.0, min(1.0, float(str(self.var_number["sound_volume"].get()))))
        except (KeyError, ValueError):
            return float(self.app.cfg.sound_volume)

    # ==================================================================
    # 全局设置
    # ==================================================================
    def _load_globals(self) -> None:
        self._loading = True
        try:
            for key, var in self.var_hotkeys.items():
                var.set(getattr(self.cfg, key, "") or "")
            self.var_mode.set("hold（按住）" if self.cfg.hotkey_mode == "hold" else "toggle（按一下）")
            for key, var in self.var_number.items():
                var.set(str(getattr(self.cfg, key)))
            for key, var in self.var_checks.items():
                var.set(bool(getattr(self.cfg, key)))
        finally:
            self._loading = False

    def _commit_globals(self) -> None:
        for key, var in self.var_hotkeys.items():
            setattr(self.cfg, key, var.get().strip())
        self.cfg.hotkey_mode = "hold" if self.var_mode.get().startswith("hold") else "toggle"
        for key, var in self.var_number.items():
            if key == "sound_volume":
                continue
            setattr(self.cfg, key, self._int(var.get(), getattr(self.cfg, key)))
        self.cfg.sound_volume = self._volume()
        for key, var in self.var_checks.items():
            setattr(self.cfg, key, bool(var.get()))

    @staticmethod
    def _int(text, default: int) -> int:
        try:
            return int(float(str(text).strip()))
        except (TypeError, ValueError):
            return default

    # ==================================================================
    # 快捷键录制
    # ==================================================================
    def record_hotkey(self, key: str) -> None:
        button = self._record_buttons.get(key)
        if button:
            button.configure(text="按键…")
        self.var_status.set("请按下组合键（要带 Ctrl/Alt/Shift/Win，或 F1~F24）；Esc 取消")
        self.app.start_hotkey_record(key)

    def set_recorded(self, key: str, text: str) -> None:
        button = self._record_buttons.get(key)
        if button:
            button.configure(text="录制…")
        if key in self.var_hotkeys:
            self.var_hotkeys[key].set(text)
        self.var_status.set("已录制：%s，点「保存并应用」生效" % text)

    def record_failed(self, message: str) -> None:
        self.var_status.set(message)

    def record_cancelled(self, key: str) -> None:
        button = self._record_buttons.get(key)
        if button:
            button.configure(text="录制…")
        self.var_status.set("已取消录制")

    # ==================================================================
    # 保存 / 重载 / 关闭
    # ==================================================================
    def save(self) -> None:
        self._commit_globals()
        self.cfg.validate()
        problems = []
        for key, title in (("hotkey", "放置表情"), ("settings_hotkey", "打开设置"),
                           ("mute_hotkey", "静音开关"), ("exit_hotkey", "退出程序")):
            value = getattr(self.cfg, key, "")
            if value:
                try:
                    Hotkey.parse(value)
                except ValueError as exc:
                    problems.append("%s 的快捷键无效：%s" % (title, exc))
        missing = [item["image"] for item in self.cfg.items
                   if item.get("image") and not os.path.isfile(config_mod.resolve_image(item["image"]))]
        if missing:
            problems.append("这些图片找不到：\n  " + "\n  ".join(missing[:5]))
        no_image = [str(index + 1) for index, item in enumerate(self.cfg.items)
                    if not config_mod.item_ready(item)]
        if no_image:
            problems.append("第 %s 个表情还没有可用图片，放着不会显示" % "、".join(no_image[:8]))
        if problems:
            messagebox.showerror("配置有问题", "\n".join(problems), parent=self.top)
            return
        try:
            self.app.apply_settings(self.cfg)
        except Exception as exc:
            messagebox.showerror("应用失败", str(exc), parent=self.top)
            return
        self.var_status.set("已保存并应用 ✓")

    def reload(self) -> None:
        self.cfg = self.app.cfg.clone()
        self._refresh_list(keep=0)
        self._load_globals()
        self.refresh_status()
        self.var_status.set("已重新载入当前配置")

    def close(self) -> None:
        self._stop_preview_animation()
        self.app.settings_closed()
        try:
            self.top.destroy()
        except tk.TclError:
            pass

    # ==================================================================
    # 程序控制（底部的状态栏）
    # ==================================================================
    def refresh_status(self) -> None:
        if hasattr(self.app, "status_text"):
            self.var_app_status.set(self.app.status_text())
        if hasattr(self.app, "is_paused"):
            self.btn_pause.configure(text="继续监听" if self.app.is_paused() else "暂停监听")
        if hasattr(self.app, "is_muted"):
            self.btn_mute.configure(text="取消静音" if self.app.is_muted() else "静音")
        # 静音可能在别处被切换过（托盘 / 快捷键），同步到编辑副本，
        # 免得随手点「保存并应用」又把它改回去
        try:
            enabled = bool(self.app.cfg.sound_enabled)
            self.cfg.sound_enabled = enabled
            self.var_checks["sound_enabled"].set(enabled)
        except Exception:
            pass

    def toggle_pause(self) -> None:
        if hasattr(self.app, "toggle_pause"):
            self.app.toggle_pause()
        self.refresh_status()

    def toggle_mute(self) -> None:
        if hasattr(self.app, "toggle_mute"):
            self.app.toggle_mute()
        self.refresh_status()

    def quit_app(self) -> None:
        if hasattr(self.app, "shutdown"):
            self.app.shutdown()

    def open_assets(self) -> None:
        folder = config_mod.assets_dir()
        try:
            os.startfile(folder)          # noqa: S606 - 打开资源管理器
        except Exception:
            messagebox.showinfo("表情素材文件夹", folder, parent=self.top)

    def focus(self) -> None:
        try:
            self.top.deiconify()
            self.top.lift()
            self.top.focus_force()
        except tk.TclError:
            pass
