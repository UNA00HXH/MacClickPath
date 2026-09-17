# ClickFlow

#本工具的灵感来源于作者本人的朋友大一下期末赶welearn的作业刷时长，平台要求30min内要有操作，否则就会自动退出，他叫豆包写了个小脚本让鼠标在welearn的翻页界面反复点，这样就不会自己时不时点一下了，难道他真的是天才？(= 3 =)

> A lightweight mouse automation tool for macOS.<br>
> 轻量级 macOS 鼠标自动化工具。

[English](#english) | [中文](#中文)

---

## Architecture / 项目架构

```text
click/
├── app.py                       # Tkinter 窗口、执行编排与程序入口
├── clickflow/
│   ├── __init__.py              # 对外导出的公共接口
│   ├── models.py                # Step、执行状态和权限状态
│   ├── steps.py                 # 步骤校验、鼠标操作和
时间格式化
│   └── accessibility.py         # macOS 辅助功能权限与系统设置入口
├── tests/
│   ├── test_steps.py            # 步骤校验与动作语义
│   ├── test_execution.py        # 顺序、暂停、停止、异常和统计
│   ├── test_accessibility.py    # macOS 权限处理
│   └── test_gui_acceptance.py   # 不操作真实鼠标的 GUI 集成验收
└── requirements.txt
```

`app.py` 是界面层，通过 `clickflow` 包调用业务和系统能力。鼠标操作集中在
`clickflow.steps`，macOS 权限处理集中在 `clickflow.accessibility`，测试可以分别
替换这些边界，因此不会在自动测试中误操作真实鼠标。

---

## English

### Introduction

**ClickFlow** is a lightweight Python utility for building and running mouse
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

Run the automated test suite with:

```bash
python3 -m unittest discover -s tests -v
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

**ClickFlow** 是一个用于 macOS 的轻量级 Python 鼠标自动化工具。

它可以编排带有自定义坐标和等待时间的移动、单击和双击步骤，减少重复鼠标操作。

### 功能

- 🖱️ 自动控制鼠标
- ⚡ 轻量、简单
- 🐍 基于 Python
- 💻 面向 macOS
- 🧩 支持可配置、可排序的操作步骤
- 🖱️ 支持用于打开文件和文件夹的原子双击

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
