# 桌面表情 Ping（Windows 11 悬浮层）

按下全局快捷键 → 鼠标点击桌面任意位置 → 点击处弹出**你的图片**（含 GIF 动图）+ **你的音效**，
置顶显示、点击穿透，3 秒后淡出消失。像英雄联盟的 ping 信号，只是素材完全由你自己准备。

```
Ctrl+Alt+Q  →  鼠标旁出现提示条  →  左键点击任意位置  →  图片 + 音效出现，3 秒后淡出
```

> **素材都是你自己的。** 程序不内置任何图形和音效：不画字形、不生成图片、不带音效资源。
> 你给它 PNG / GIF / WAV，它负责"在鼠标点击的地方漂亮地放出来"。

## 功能一览

| 能力 | 说明 |
| --- | --- |
| 全局快捷键 | `WH_KEYBOARD_LL` 低级键盘钩子，任何界面、任何程序里都生效 |
| 点击处显示 | `WH_MOUSE_LL` 低级鼠标钩子取屏幕坐标，在坐标处创建置顶窗口 |
| 置顶 + 点击穿透 | `WS_EX_TOPMOST` + `WS_EX_TRANSPARENT` + `WS_EX_NOACTIVATE`，不吃鼠标、不抢焦点、不进 Alt+Tab |
| 3 秒淡出 | 每个表情一个独立窗口，用窗口整体 alpha 做淡出 |
| 图片 / 动图 | PNG / GIF / JPG…；多帧 GIF 按每帧自己的延时循环播放 |
| 每个表情配自己的音效 | 指一个 WAV / MP3 文件即可；支持音量和静音快捷键 |
| 素材管理 | 「添加图片」可多选、「添加文件夹」批量导入；文件自动收进「表情素材」文件夹 |
| 托盘图标 | 右键菜单：设置 / 暂停监听 / 静音 / 退出；左键或双击直接打开设置台 |
| 设置台 | 启动就直接看到：表情列表 + 预览（动图会动）+ 状态栏（暂停 / 静音 / 退出） |
| 免安装 exe | `python build_exe.py` 打包成单个 `dist\桌面表情Ping.exe`，双击即用 |
| 依赖 | **零第三方依赖**，只用标准库（`ctypes` + `tkinter` + `winsound`） |

## 运行环境

* Windows 10 / 11（按 Win11 编写，Win10 同样可用）
* Python 3.8+（用 [python.org](https://www.python.org/downloads/windows/) 官方安装包，自带 tkinter）
* 不需要管理员权限

**不想装 Python？** 用已经打好的 `dist\桌面表情Ping.exe`，双击即用（见「打包成 exe」）。

## 快速开始

### 方式一：直接用 exe（推荐，免安装）

1. 双击 `dist\桌面表情Ping.exe` → **直接打开设置台**，同时在托盘待命。
2. 点「添加图片」选你的图（可多选），或「添加文件夹」批量导入，然后点「保存并应用」。
3. 按 `Ctrl+Alt+Q` → 左键点击桌面任意位置 → 图片 + 音效出现，3 秒淡出。

第一次运行时，`config.json` 和「表情素材」文件夹会自动生成在 **exe 同目录**，
整个文件夹拷到别的电脑也能用。

### 方式二：跑源码

1. 安装 Python 时勾选 **Add python.exe to PATH** 和 **tcl/tk**。
2. 先跑一次环境自检，确认各项都是 `[OK ]`：

   ```bat
   python selftest.py
   ```

3. 双击 `启动.bat` 就开工了（会弹出设置台窗口，同时常驻托盘）。
   想改配置：双击 `打开设置.bat`，或者按 `Ctrl+Alt+S`，或者右键托盘图标。
   想看日志：双击 `调试运行.bat`。

不想每次启动都弹设置台：在设置台「选项」页取消勾选「启动时打开本窗口」，
或者用 `python main.py --no-settings` 启动。

## 操作方式

| 操作 | 说明 |
| --- | --- |
| `Ctrl+Alt+Q` | 进入「待放置」，鼠标旁出现提示条（带当前表情缩略图） |
| 左键点击 | 在点击位置显示图片并播放该表情的音效 |
| 滚轮 | 在待放置状态下切换表情（选择会记回 `config.json`） |
| 右键 / `Esc` | 退出待放置状态 |
| `Ctrl+Alt+S` | 打开设置台 |
| `Ctrl+Alt+M` | 静音开 / 关 |
| `Ctrl+Alt+Shift+Q` | 退出程序 |

想连续放好几个表情，把设置里的「触发方式」改成 `hold（按住）`：按住快捷键期间可以一直点击。

## 素材怎么给

### 图片 / 动图

* 设置台「添加图片」可以多选，或「添加文件夹」把一个文件夹里的图片全部导入；
* 选中后程序会把文件**复制到程序目录下的「表情素材」文件夹**，`config.json` 里记的是
  相对路径，所以整个文件夹搬到别的电脑也不会失效；
* 点「打开素材夹」可以直接打开那个文件夹，手动往里丢文件也行（再「添加图片」选它）；
* **动图**：多帧 GIF 会自动当成动图播放，每一帧用自己的延时（上限 120 帧），
  放置期间循环播放，设置台里的预览也会动。想要什么动效就做什么 GIF；
* 建议用**带透明通道的 PNG / GIF**，边缘会干净很多；
* 装了 Pillow（`pip install pillow`）可用 JPG、缩放也更细腻，不装也能跑（PNG / GIF 原生支持）。

### 音效

* 在设置台给某个表情「选文件」，或改 `default_sound` 让所有表情默认用同一个音效；
* `.wav` 用 `winsound` 异步播放，必定可用；`.mp3` / `.m4a` / `.wma` 走系统 MCI
  （失败时设置台会显示原因，转成 WAV 最稳）；
* 「音量」是总音量：「无音效」的表情不出声，`Ctrl+Alt+M` 可以随时全局静音；
* 连续点击有最小间隔（`sound_min_interval_ms`），避免声音糊成一片。

### config.json

设置台能改的东西都会写回这个文件，也可以在程序没运行时直接编辑：

```json
{
  "hotkey": "ctrl+alt+q",
  "items": [
    {"image": "表情素材/question.png", "sound": "", "size": 0, "label": ""},
    {"image": "表情素材/fire.gif", "sound": "表情素材/boom.wav", "size": 140},
    {"image": "D:/pics/随便放哪都行.png", "sound": "none"}
  ],
  "size": 96,
  "duration_ms": 3000,
  "fade_ms": 700
}
```

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `hotkey` / `hotkey_mode` | `ctrl+alt+q` / `toggle` | 放置快捷键；`hold` = 按住期间可连续点击 |
| `settings_hotkey` | `ctrl+alt+s` | 打开设置台 |
| `mute_hotkey` | `ctrl+alt+m` | 静音开关 |
| `exit_hotkey` | `ctrl+alt+shift+q` | 退出，留空表示不启用 |
| `items` | `[]` | 表情列表（见上面注释），`image` 必填 |
| `current_index` | 0 | 当前选中项 |
| `size` | 96 | 表情默认像素尺寸（图片按这个缩放） |
| `duration_ms` / `fade_ms` | 3000 / 700 | 停留时长 / 淡出时长（毫秒），`fade_ms=0` 表示直接消失 |
| `sound_enabled` / `default_sound` / `sound_volume` | true / `""` / 0.7 | 音效总开关、默认音效文件、音量 |
| `consume_click` | true | 放置时吞掉这次左键点击，避免顺手点到下层按钮 |
| `stay_armed` | false | 放完是否继续保持待放置（连续放置） |
| `cycle_on_wheel` / `show_hint` | true / true | 滚轮切换 / 鼠标提示条 |
| `hint_thumb_size` | 40 | 提示条里缩略图的大小 |
| `offset_x` / `offset_y` | 0 / -6 | 表情相对点击点的偏移 |
| `transparent_color` | `#FF00FF` | 透明色键；桌面有粉色元素导致镂空时换一个 |
| `enable_tray` / `open_settings_on_start` | true / true | 托盘图标 / 启动就打开设置台 |

## 打包成 exe

```bat
pip install pyinstaller      :: 只装一次
python build_exe.py          :: 或者双击 打包exe.bat
```

产物是 `dist\桌面表情Ping.exe`（约 15 MB，单文件、免安装、无控制台窗口）。
双击运行后，`config.json`、`表情素材`、`app.ico` 都会生成在 exe 同目录。

两个说明：

* **为什么这么大**：里面装了 Python 运行时 + Tk 界面库 + Tcl/Tk 脚本库，tkinter 程序打包的正常体积。
* **为什么要写 `build_exe.py` 而不是一条命令**：Python 3.12 之后官方 Windows 版把
  Tcl/Tk 的脚本库塞进了 zip（解释器里看到的是 `//zipfs:/lib/tcl/tcl_library` 这种路径），
  PyInstaller 收集不到，直接打包出来的 exe 会报 `Cannot find a usable init.tcl`。
  脚本里先把 zip 解成普通目录再 `--add-data` 塞进去，就正常了。

打包好的 exe 也能自检（结果写在 exe 旁的 `selftest-report.txt`）：

```bat
桌面表情Ping.exe --selftest
```

改完源码要重新打包时，**先确认没有 exe 进程在运行**（否则文件被占用会打包失败）。

## 原理简述

* **全局监听**：低级钩子回调跑在安装它的线程里，所以 `input_monitor.py` 单独开一个线程跑
  Win32 消息循环，事件通过 `queue.Queue` 交给 Tk 主线程（回调里碰 Tk 会卡死）。
* **透明置顶窗口**：每个表情是一个 `overrideredirect` 的 Toplevel，背景设为透明色键
  （`-transparentcolor`），只有图片可见；淡出用窗口整体 alpha。
* **图片与动图**：`images.py` 逐帧读入 GIF（`PhotoImage(file=..., format="gif -index N")`），
  帧延时直接解析 GIF 文件结构得到；Tk 只能整数倍缩放，就挑最接近目标尺寸的倍数。
* **色键与 alpha 的兼容性**：两者能否共存取决于 Tk 版本，启动时用 1×1 隐藏窗口实测一次
  （`overlay.py: probe_layer_mode`），据此决定是否启用淡出，避免出现「不透明方块」。
* **点击穿透**：改扩展样式有可能重置分层属性，所以样式齐了就不再改，改完也会重设一次透明属性。
* **DPI**：启动即开启 Per-Monitor-V2 DPI 感知，125%/150% 缩放下点击位置不偏移。
* **托盘**：`tray.py` 用纯 ctypes 注册窗口类 + `Shell_NotifyIcon`，自己跑消息循环，
  菜单项通过队列交给主线程。任何一步失败都只是「没有托盘图标」，不影响其它功能。
* **打包**：exe 版里 `__file__` 指向临时解包目录，所以程序目录统一用 `config.app_dir()`
  （打包后取 exe 所在目录）。
* 更细的拆解见 [技术梳理.md](技术梳理.md)。

## 常见问题

**图片显示不出来 / 提示「缺图片」？**
设置台列表里这一行会标「缺图片」。检查 `image` 路径是否有效（相对路径会先在程序目录、
再在「表情素材」里找）；换行显示「⚠️」时「预览」也会说明原因。

**动图不动？**
确认是**多帧 GIF**（单帧 GIF 就是静态图）；帧数上限 120，超过会被截断。

**点击位置和图片位置对不上？**
先看 `selftest.py` 里「DPI 感知」是否 OK。多显示器 + 不同缩放时若仍有偏差，
用 `offset_x`、`offset_y` 微调。

**没有声音？**
设置里确认「启用音效」没关、音量不为 0，且没按过 `Ctrl+Alt+M` 静音；
再确认这个表情选了音效文件（或设置了默认音效）。MP3 依赖系统 MCI，打不开就换成 WAV。

**在独占全屏游戏里看不到？**
独占全屏会绕开桌面合成，任何普通置顶窗口都画不上去；把游戏改成「无边框窗口」即可。

**提示「程序已经在运行」？**
默认单实例：第二次启动会**请求已运行的实例打开设置台**（`打开设置.bat` 就是这么用的）。
要多开就加参数 `--allow-multiple`；退出用 `Ctrl+Alt+Shift+Q` 或托盘菜单。

**托盘没图标？**
远程桌面 / 沙箱桌面 / 精简版系统里可能没有通知区域，程序会自动跳过，其它功能照常。

**想开机自启？**
`Win+R` 输入 `shell:startup`，把 exe（或 `启动.bat`）的快捷方式丢进去。
想静默开机（不弹设置台），快捷方式目标后面加 ` --no-settings`。

**双击 exe 没反应 / 杀毒软件报毒？**
先看 exe 旁边有没有 `selftest-report.txt`，或者用 `桌面表情Ping.exe --selftest`
跑一遍看哪项失败。PyInstaller 打包的程序有时会被杀软/浏览器误报，加个信任即可；
也可以改用源码方式运行（`启动.bat`）。

## 命令行参数

```
桌面表情Ping.exe --settings        exe 版：启动并打开设置台
桌面表情Ping.exe --no-settings     exe 版：只在托盘待命，不弹窗口
桌面表情Ping.exe --selftest        exe 版：环境自检，结果写到 exe 旁的 txt

python main.py --settings          启动并直接打开设置台
python main.py --no-settings       启动时不打开设置台
python main.py --hotkey ctrl+alt+p 本次启动换快捷键
python main.py --mode hold         本次启动用按住模式
python main.py --image 图.png      本次启动加入一张图片（会复制进素材夹）
python main.py --no-tray           不要托盘图标
python main.py --list-items        列出所有表情后退出
python main.py --selftest          环境自检并退出
python selftest.py                 环境自检

python build_exe.py                打包成 dist\桌面表情Ping.exe
```

## 文件结构

```
main.py            入口：串起配置、监听线程、悬浮层、音效、托盘、设置台
input_monitor.py   全局键鼠钩子（独立线程 + 消息循环）+ 快捷键录制
overlay.py         悬浮层：图片/动图窗口、淡出动画、鼠标提示条
images.py          图片加载：静态图 + GIF 逐帧与延时解析 + 整数倍缩放
settings_ui.py     设置台（表情列表、素材导入、音效、快捷键、状态栏）
audio.py           音效：播放你的 WAV / MP3 文件（不内置音效）
tray.py            托盘图标与右键菜单（纯 ctypes）
iconasset.py       用代码画"程序图标"（app.ico，只用于程序自身，不是表情素材）
winapi.py          ctypes 封装：DPI、钩子、窗口样式
hotkeys.py         快捷键字符串解析与匹配
config.py          config.json 的读写、校验、旧格式升级、素材目录管理
selftest.py        环境自检
build_exe.py       打包脚本（处理 Tcl/Tk zip 库再调 PyInstaller）
config.json        配置文件（首次运行自动生成）
表情素材/          你放图片/动图/音效的地方（选文件时会自动复制进来）
启动.bat / 打开设置.bat / 调试运行.bat / 打包exe.bat
dist/              打包产物：桌面表情Ping.exe（及运行后生成的配置、素材）
技术梳理.md        代码逻辑 / 原理 / 技术栈的详细梳理
```

## 二次开发提示

* 想让表情"弹"出来、带缓动和缩放（像游戏里的 ping / 炉石表情）：见
  [技术梳理.md](技术梳理.md) 的「下一步：更华丽的出现/消失动画」一节。
* 想画线、圈、箭头：把 `Label` 换成 `Canvas`，在 `PingWindow` 里按 `item` 绘制。
* 想更细腻的图片缩放 / JPG：`pip install pillow`，`images.py` 会自动走 Pillow 分支。
