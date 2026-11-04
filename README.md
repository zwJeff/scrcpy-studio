# Scrcpy Studio

macOS 桌面程序：集中管理 adb / scrcpy，用**手机桌面**的方式浏览手机上所有可投屏的应用，
双击即在独立虚拟显示中单独投屏；还能从 Mac 直接往手机输入框推文字。

![界面预览](screenshot-mock.png)

## 环境准备

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

运行前需确保 `scrcpy`（5.x，需支持 `--new-display`）与 `adb` 可用，推荐装到 `~/.local/bin/`；
程序会自动在 PATH、`~/.local/opt/`、Homebrew 路径下查找。macOS 12+ / Apple Silicon 与 Intel 均可。

## 启动

```bash
open ScrcpyStudio.app   # 或双击
./run.sh                # 命令行
```

## 功能

### 手机桌面与应用信息

- 应用以**手机屏幕**形态展示：圆角外框、状态栏（时间 / 设备名 / 信号电量）、
  渐变壁纸、4 列图标网格、底部 Dock；可切换成紧凑列表视图。
- 双击图标 → `scrcpy --new-display --start-app=+包名`，在独立虚拟显示中只投这一个应用。
- 应用列表来自 `cmd package query-activities`，只保留真正带桌面入口的应用。
- **自动获取真实应用名与图标**：Android shell 接口读不到 label / icon，程序会从设备端
  APK 解析二进制 `AndroidManifest.xml` + `resources.arsc`（基于 `pyaxmlparser`）：
  - 优先走**轻量路径** —— 设备支持 `unzip -p` 时只取 manifest / resources.arsc / 图标，
    合计通常不到 1 MB，不用把几十 MB 的整包拉回电脑；
  - 不支持时自动回退 `adb pull` 整包解析，解析完立即删除临时 APK；
  - 结果与图标 PNG 缓存在 `~/Library/Application Support/ScrcpyStudio/appinfo/`，
    按 APK 路径做 key，应用更新会自动重取；3 线程并发，顶部显示提取进度，可点「重载图标」强制刷新；
  - 图标缺失或为 adaptive XML 时会回退到按分类配色的占位图标。
- 名称优先级：手动改的显示名 > APK 真实 label > 内置中文词典 > 包名。
- 右键图标：投屏、复制包名、改名、固定到 Dock、手动归类、恢复自动分类。

### 应用分组

内置 15 类规则：社交、影音、游戏、购物、金融、智能家居、出行、阅读、摄影、办公、
健康运动、教育、工具、系统、其他。匹配顺序为
**手动指定 > 精确包名表 > 关键词规则 > 系统应用 > 其他**。

- 顶部分类栏可一键筛选，「按类型分区」开启时在桌面里按分类分段显示标题与数量；
- 右键「归类到…」可覆盖自动分类，选择「恢复自动分类」还原，覆盖关系会持久化；
- 规则表在 `core/categories.py`，可直接加包名或关键词。

### 设备输入

底部「设备输入」把 Mac 上敲的文字推送到手机**当前获得焦点的输入框**：

| 模式 | 通道 | 适用 |
|---|---|---|
| 自动 | 纯 ASCII 走 `input text`，含中文走 ADBKeyBoard | 默认 |
| 仅英文 | `adb shell input text` | 空格转 `%s`，shell 层安全转义 |
| ADBKeyBoard | `am broadcast -a ADB_INPUT_B64 --es msg <base64>` | 中文 / emoji，需设备装 `com.android.adbkeyboard` |

- 快捷键：`⌘↵` 发送、`⌘K` 聚焦输入框、`Esc` 清空（输入框有焦点时）
- 「发送后回车」会在文本后追加 `keyevent 66`；另有回车 / 退格 / 返回三个按键
- 「复制」把文本放进 Mac 剪贴板，到 scrcpy 窗口按 `⌘V` 即可粘贴任意语言
  （scrcpy 会同步剪贴板并自动粘贴，无需额外输入法）
- 最近 20 条发送记录保存在「历史」

### 投屏参数

码率 / 分辨率上限 / 帧率 / H.264·H.265·AV1 / 音频 / 无边框·置顶·全屏 /
键盘鼠标模式 / 熄屏投屏 / 保持唤醒 / 录制 MP4 / 虚拟显示尺寸与 DPI，
全部映射到 scrcpy 5.x 命令行参数并持久化。底部控制台实时显示 adb 与 scrcpy 输出。

## 无线连接流程（Android 11+，一次性）

1. 手机：开发者选项 → 无线调试 → 打开 → 「使用配对码配对设备」
2. App：设备栏 → 配对 → 填弹窗里的地址和 6 位码
3. App：设备栏 → 无线连接 → 填无线调试页面上的地址（和配对地址不同）
4. 成功后 App 会记住设备，之后只要无线调试开着，点「刷新」即可直连

## 已知限制

- 手机重启后无线调试默认关闭，App 无权替你打开（无 root / 无 Shizuku 的固有限制）。
- `input text` 只支持 ASCII；中文要么装 ADBKeyBoard，要么用剪贴板 + scrcpy `⌘V`。
- 首次连接设备后提取图标会占用一些时间（取决于应用数量与设备端是否有 `unzip`），
  之后走本地缓存，几乎瞬时。
- 未做正式代码签名，首次 `open` 若被 Gatekeeper 拦截：右键 App → 打开。

## 目录结构

```
app.py                  入口
run.sh                  启动脚本
requirements.txt        Python 依赖
ScrcpyStudio.app/       macOS 应用壳（双击启动）
core/adb.py             adb 封装（设备 / 应用 / 连接 / 配对 / mDNS）
core/apkinfo.py         APK 名称与图标提取、轻量取数、本地缓存
core/categories.py      应用分组规则引擎
core/textinput.py       文本注入与 ADBKeyBoard 广播
core/config.py          参数建模与持久化
core/aliases.py         包名 → 中文名映射
core/tasks.py           线程池异步包装
ui/desktop.py           手机桌面视图与图标绘制
ui/panels.py            三栏面板与筛选
ui/inputpanel.py        设备输入面板
ui/dialogs.py           无线连接 / 配对对话框
ui/main_window.py       主窗口与业务接线
scripts/                离屏截图自检脚本
```
