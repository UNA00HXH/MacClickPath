import time
import pyautogui

# 给你 3 秒钟切换回 Codex 窗口
print("3 秒后点击「允许一次」...")
time.sleep(3)

# 把下面坐标改成「允许一次」按钮所在的位置
x = 1200
y = 800

pyautogui.click(x, y)

print("已点击")