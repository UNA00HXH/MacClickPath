# MacClickPath — macOS Mouse Workflow Automation

本工具的灵感来源于作者本人的朋友大一下期末赶 welearn 的作业刷时长，平台要求 30 min 内要有操作，否则就会自动退出。他叫豆包写了个小脚本让鼠标在 welearn 的翻页界面反复点，这样就不用自己时不时点一下了，难道他真的是天才？(= 3 =)

> A lightweight mouse automation tool for macOS.<br>
> 轻量级 macOS 鼠标自动化工具。

[English](#english) | [中文](#中文)

---

## Architecture / 项目架构

```text
mac-click-path/
├── app.py                       # Tkinter 界面、事件消费和入口
├── clickflow/
│   ├── __init__.py              # clickflow 包的稳定公共接口
│   ├── models.py                # 结构化动作/条件、Step、Workflow 和状态
│   ├── coordinates.py           # 显示器/窗口识别、坐标解析、安全检查与预览
│   ├── runner.py                # 执行循环、事件、活动时钟与可取消动作边界
│   ├── steps.py                 # 表单校验、原子鼠标动作和时间格式化
│   ├── workflow.py              # 校验、条件求值、JSON 版本迁移与文件读写
│   └── accessibility.py         # macOS 辅助功能权限检测和设置入口
├── tests/
│   ├── test_steps.py            # 输入校验与原子动作语义
│   ├── test_execution.py        # 循环、分支、重试、超时、暂停和停止
│   ├── test_workflow.py         # 工作流校验与 JSON 往返
│   ├── test_accessibility.py    # macOS 权限边界
│   └── test_gui_acceptance.py   # 不操作真实鼠标的 Tk 集成验收
├── TODO.md                      # 后续能力规划与完成状态
└── requirements.txt             # Python 运行依赖
```

### Runtime flow / 运行数据流

```text
Tk step editor
      │ creates / loads
      ▼
Workflow + stable-ID Step values ──► validation and migrated JSON v2
      │ snapshot on Start
      ▼
clickflow.runner ──► condition evaluation ──► action executor
      │
      └── typed event queue ──► Tk main thread updates status and statistics
```

Tk 控件只在主线程访问。`app.py` 把不可变的工作流快照交给
`WorkflowRunner`，后者独立处理等待、循环、ID 跳转、重试和动作，并只通过
`RunnerEvent` 队列向界面回报。条件等待和单步超时共用可暂停的活动时钟；
长时动作可通过 `CancellableActionExecutor` 协作响应取消；无法安全取消时，
使用 `IsolatedActionExecutor` 在独立进程中执行。

### Extension boundaries / 后续开发边界

- 新增动作时应新建独立动作数据类，再扩展 JSON 编解码、执行器与界面；键盘、
  窗口和图像参数不应回填到 `Step` 的通用字段。
- 新增条件时应新建条件数据类，并同步扩展校验、求值、JSON 编解码和界面。
- JSON 的 `version` 是持久化兼容边界。字段含义变更或移除时必须升级版本，并向
  `MIGRATIONS` 添加从前一版本到新版本的单步迁移。
- 可协作取消的动作使用进程内执行器；可能长期阻塞且不能安全取消的动作必须
  使用 `IsolatedActionExecutor`，不应依赖无法终止的后台线程。

---

## English

### Introduction

**MacClickPath** is a lightweight Python utility for building and running mouse
automation workflows on macOS.

It lets you arrange move, click, and double-click steps with configurable coordinates and
wait times, reducing repetitive mouse operations.

### Features

- 🖱️ Automatically controls the mouse cursor
- ⚡ Lightweight and simple
- 🐍 Built with Python
- 💻 Designed for macOS
- 🧩 Supports configurable, ordered action steps
- 🖱️ Supports atomic double-clicks for opening files and folders
- 🔁 Supports finite or infinite workflow loops and per-step repeats
- 🎲 Supports randomized wait ranges, conditions, jumps, retries, and timeouts
- 💾 Saves and loads versioned JSON workflows
- 🎯 Resolves absolute, per-display percentage, and target-window coordinates at run time
- 🛡️ Offers screenshot previews, pre-click color checks, and allowed-region limits

### Requirements

- macOS
- Python 3.9 or newer
- The Python dependency listed in [`requirements.txt`](requirements.txt)

### Installation

Install the required dependency:

```bash
python3 -m pip install -r requirements.txt
```

Verify the installation:

```bash
python3 -c "import pyautogui; print('pyautogui OK')"
```

Expected output:

```text
pyautogui OK
```

### Usage

Launch the desktop application:

```bash
python3 app.py
```

The window displays the live mouse position and can capture a coordinate after
a three-second countdown. On macOS, it also shows the current Accessibility
permission status. Use the step editor to add, edit, delete, and reorder move,
click, or double-click actions, each with its own coordinate and pre-action wait time. The
execution controls support a three-second start countdown, pause, resume, and
stop. Moving the pointer to the upper-left corner triggers PyAutoGUI's
emergency stop. The execution panel reports the current state and step,
highlights the active row, and tracks active run time and completed operations.

Advanced step fields provide a random wait upper bound, repeat and retry counts,
a timeout, and 1-based success/failure jump targets. Conditions can always pass,
wait for the mouse to reach the step coordinate, or wait for the pixel at the
step coordinate to match an `R,G,B` value. A failed condition or timed-out step
uses its failure jump when configured; otherwise execution stops with an error.
Use **Save JSON** and **Load JSON** to persist all steps and loop settings.

Choose a coordinate mode per step: absolute desktop coordinates, percentages of
a selected display, or offsets from a selected target window. **Refresh Targets**
discovers the current displays and windows, while **Screenshot Preview** marks the
resolved target (or captures the configured allowed region). For click actions,
an optional expected `R,G,B` color and tolerance are checked immediately before
the click; a mismatch follows the step's retry/failure branch. An allowed region
(`X,Y,width,height`, in global desktop coordinates) blocks every mouse action
whose resolved target falls outside it.

Run the automated test suite with:

```bash
python3 -m unittest discover -s tests -v
```

Tk acceptance tests require an interactive macOS desktop session and are opt-in:

```bash
CLICKFLOW_GUI_TESTS=1 python3 -m unittest tests.test_gui_acceptance -v
```

### macOS Permission

Because the script controls your mouse, macOS may require Accessibility permission.

Go to:

**System Settings → Privacy & Security → Accessibility**

Then enable permission for the application running the script, such as:

- Visual Studio Code
- Terminal

### Notes

The position of the **"Allow Once"** button may vary depending on:

- Screen resolution
- VS Code window position
- UI scaling
- External monitor setup

If the mouse clicks the wrong position, configure the button coordinates again.

---

## 中文

### 简介

**MacClickPath** 是一个用于 macOS 的轻量级 Python 鼠标自动化工具。

它可以编排带有自定义坐标和等待时间的移动、单击和双击步骤，减少重复鼠标操作。

### 功能

- 🖱️ 自动控制鼠标
- ⚡ 轻量、简单
- 🐍 基于 Python
- 💻 面向 macOS
- 🧩 支持可配置、可排序的操作步骤
- 🖱️ 支持用于打开文件和文件夹的原子双击
- 🔁 支持整套流程有限/无限循环和单步重复
- 🎲 支持随机等待、条件、跳转、重试和超时
- 💾 支持保存和载入带版本号的 JSON 工作流
- 🎯 支持绝对坐标、指定显示器百分比坐标和目标窗口相对坐标
- 🛡️ 支持目标截图预览、点击前颜色检查和鼠标允许区域

### 环境要求

- macOS
- Python 3.9 或更高版本
- [`requirements.txt`](requirements.txt) 中列出的 Python 依赖

### 安装

安装依赖：

```bash
python3 -m pip install -r requirements.txt
```

检查是否安装成功：

```bash
python3 -c "import pyautogui; print('pyautogui OK')"
```

如果输出：

```text
pyautogui OK
```

说明安装成功。

### 使用方法

启动桌面应用：

```bash
python3 app.py
```

窗口会实时显示鼠标位置，并可在 3 秒倒计时后将坐标填入步骤表单。在
macOS 上，窗口还会显示当前的辅助功能权限状态。步骤编辑器支持添加、
编辑、删除和调整“移动”“点击”“双击”操作的顺序，每一步可独立设置坐标和执行前等待时间。
执行区支持开始前 3 秒倒计时、暂停、继续和停止；将鼠标移动到屏幕左上角可触发
PyAutoGUI 紧急停止。执行区还会显示当前状态和步骤、高亮正在执行的步骤，并统计
本次有效运行时间与已完成操作数；暂停期间不计时。

高级步骤字段可设置随机等待上限、单步重复、失败重试、单步超时，以及从 1 开始的
成功/失败跳转步骤号。执行条件支持“始终执行”“鼠标位于坐标”和“像素颜色匹配”；
像素颜色的条件值填写为 `R,G,B`。条件等待或单步执行失败后，如配置了失败跳转则进入
对应步骤，否则停止并显示错误。使用“保存 JSON”和“载入 JSON”可持久化全部步骤与
整套循环设置。

每一步可选择屏幕绝对坐标、所选显示器的宽高百分比，或目标窗口左上角的相对坐标。
“刷新目标”会重新识别当前显示器和窗口；“截图预览”会用红色十字标出运行时解析的
目标位置，也可预览所配置的允许区域。点击/双击步骤可填写期望的 `R,G,B` 与颜色容差，
程序会在点击前即时检查，不匹配时进入该步骤的重试或失败跳转。允许区域填写
`X,Y,宽,高`（全局桌面坐标），任何解析后落在区域外的鼠标操作都会被阻止。

运行自动测试：

```bash
python3 -m unittest discover -s tests -v
```

### macOS 权限设置

由于程序需要控制鼠标，因此 macOS 可能会要求授予 **辅助功能（Accessibility）** 权限。

打开：

**系统设置 → 隐私与安全性 → 辅助功能**

然后为运行脚本的应用开启权限，例如：

- Visual Studio Code
- Terminal

### 注意事项

**「允许一次」** 按钮的位置可能受到以下因素影响：

- 屏幕分辨率
- VS Code 窗口位置
- UI 缩放比例
- 外接显示器

如果鼠标点击的位置不正确，请重新配置按钮坐标。

---

## Disclaimer / 免责声明

This project is a small automation utility intended for personal workflows. Always verify the target before running an automated click sequence.

本项目是用于个人工作流的简单自动化工具。执行自动点击序列前，请始终确认目标位置正确。
