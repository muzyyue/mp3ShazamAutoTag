# -*- coding: utf-8 -*-
"""
Imusic GUI 后台启动器。

用 python.exe（而非 pythonw.exe）启动，因为本机 .venv 的 pythonw.exe
与 PySide6 存在兼容问题（Qt 窗口无法显示，仅出现伪控制台）。

此脚本启动后立即隐藏自身控制台窗口，再运行 GUI。
- 优点：Qt 窗口 100% 正常显示，无持久黑框。
- 缺点：启动瞬间控制台约闪现 100ms（可接受）。
"""
import asyncio
import ctypes
import os
import sys

# 隐藏当前进程的控制台窗口（python.exe 才会创建控制台）
try:
    _hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    if _hwnd:
        ctypes.windll.user32.ShowWindow(_hwnd, 0)  # SW_HIDE
except Exception:
    pass

# 定位项目根目录（本文件所在目录）
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(_PROJECT_ROOT)
sys.path.insert(0, _PROJECT_ROOT)

import main  # noqa: E402

if __name__ == "__main__":
    asyncio.run(main.main())