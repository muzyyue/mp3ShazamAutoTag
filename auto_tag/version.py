# -*- coding: utf-8 -*-
"""
版本号模块

版本号由 build_tools/update_version.py 自动从 pyproject.toml 提取。
PyInstaller 打包后，此文件被编译为 .pyc，无需依赖外部文件。

Attributes:
    __version__ (str): 应用版本号
"""

__version__ = "0.6.4"
