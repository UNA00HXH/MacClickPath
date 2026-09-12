# Codex Auto Allow

> Stop clicking "Allow Once" manually.  
> 告别手动点击 Codex「允许一次」。

[English](#english) | [中文](#中文)

---

## English

### Introduction

**Codex Auto Allow** is a tiny Python utility for macOS that helps automatically move the mouse cursor and click the **"Allow Once"** button when using Codex.

It is designed to reduce repetitive permission clicks during development.

### Features

- 🖱️ Automatically controls the mouse cursor
- ⚡ Lightweight and simple
- 🐍 Built with Python
- 💻 Designed for macOS
- 🔧 Works with Codex workflows in VS Code

### Requirements

- macOS
- Python 3
- `pyautogui`

### Installation

Install the required dependency:

```bash
python3 -m pip install pyautogui
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

Run the script:

```bash
python3 main.py
```

Follow the terminal instructions to configure the position of the **"Allow Once"** button.

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

**Codex Auto Allow** 是一个用于 macOS 的轻量级 Python 小工具。

在使用 Codex 开发时，它可以帮助你自动移动鼠标并点击 **「允许一次 / Allow Once」** 按钮，减少反复手动确认权限的操作。

### 功能

- 🖱️ 自动控制鼠标
- ⚡ 轻量、简单
- 🐍 基于 Python
- 💻 面向 macOS
- 🔧 适用于 VS Code 中的 Codex 工作流

### 环境要求

- macOS
- Python 3
- `pyautogui`

### 安装

安装依赖：

```bash
python3 -m pip install pyautogui
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

运行：

```bash
python3 main.py
```

按照终端提示配置 **「允许一次 / Allow Once」** 按钮的位置即可。

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

This project is a small automation utility intended for personal development workflows. Please review Codex actions before granting permissions.

本项目是用于个人开发工作流的简单自动化工具。建议在授予权限前确认 Codex 即将执行的操作。