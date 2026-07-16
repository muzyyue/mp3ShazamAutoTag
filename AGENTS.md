# PROJECT KNOWLEDGE BASE

**Generated:** 2026-07-16
**Version:** 0.6.3
**Stack:** Python 3.12, PySide6, QFluentWidgets, ShazamIO, FFmpeg

## OVERVIEW

Imusic — 智能音频标签管理工具。使用 Shazam/Acoustid 音频指纹识别 + 多源关键词搜索（网易云/酷狗/QQ音乐）自动识别音乐文件，支持批量标签编辑、音频裁剪、响度标准化和格式转换。

## STRUCTURE

```
mp3ShazamAutoTag/
├── auto_tag/              # 主包: 识别/标签/编辑/转换/GUI
│   ├── audio_recognize/   # (包) Shazam/Acoustid 识别 + 多源搜索 + 标签写入
│   ├── gui/               # PySide6 + QFluentWidgets 界面 (6 子包, ~9k 行)
│   ├── converter/         # 音频格式转换 (5 预设 + 自定义格式)
│   ├── editor/            # 音频裁剪 + EBU R128 响度标准化
│   ├── lyric/             # 歌词管理: 获取/嵌入/提取/转换 (4 子模块)
│   └── utils/             # 工具函数 + ffmpeg 静默执行
├── tests/                 # pytest 测试套件 (~57 文件, ~14k 行)
├── build_tools/           # PyInstaller 构建 + 版本同步
├── tools/                 # Qt UI 调试工具
├── main.py                # CLI + GUI 双模入口
└── pre_release_validation.py
```

## WHERE TO LOOK

| 任务 | 位置 | 说明 |
|------|------|------|
| 音频识别 (Shazam) | `audio_recognize/_orchestrator.py` | 识别编排 + 多源搜索回退 |
| Acoustid 识别 | `audio_recognize/_recognizer.py` | Chromaprint 指纹识别 |
| 多源搜索 | `audio_recognize/_search.py` | 网易云/酷狗/QQ音乐搜索 |
| 标签写入 | `audio_recognize/_tags.py` | MP3/FLAC/OGG/M4A 标签 + 封面 |
| 音频元数据 | `audio_recognize/_metadata.py` | 文件名解析 + 元数据提取 |
| 网易云识别 | `netease_recognize.py` | 听歌识曲 API |
| GUI 配置 | `gui/config.py` | AppConfig 单例, 管理所有运行时配置 |
| 搜索源配置 | `gui/config.py` → `VALID_SEARCH_SOURCES` | acoustid/shazam/netease/kugou/qqmusic |
| 歌词管理 | `lyric/manager.py` (门面) | 委托给 lyric_fetcher/embedder/converter |
| 格式转换 | `converter/converter.py` | 5 预设 + 自定义格式 |
| 音频编辑 | `editor/audio_editor.py` | 裁剪 + loudnorm 标准化 |
| 国际化 | `gui/i18n/translator.py` | 中/英 JSON 翻译 |

## CONVENTIONS

- **导入**: 必须用统一入口 `from auto_tag.utils import ...`; `_legacy_utils` 直接导入被 CI 禁止
- **编码**: 所有 .py 文件 `# -*- coding: utf-8 -*-` (虽冗余但项目惯例)
- **文档字符串**: Google 风格, 中英文混用, 含 `Args:`/`Returns:`/`Raises:`/`Example:` 节
- **类型注解**: 旧式 `Optional[X]`/`Dict[K,V]`/`Tuple`; 部分文件有 `from __future__ import annotations`
- **异步**: pytest 使用 `asyncio_mode = "auto"`; GUI Worker 用 QThread
- **测试**: pytest, 测试文件 `tests/test_*.py`, 类 `Test*`, 函数 `test_*`
- **依赖管理**: uv (uv.lock + uv.toml), 清华 PyPI 镜像

## ANTI-PATTERNS (THIS PROJECT)

- **无代码质量工具**: 无 ruff/mypy/black/isort/editorconfig 配置 — 手动保持一致
- **`utils/__init__.py` 614 行**: 功能混杂 (sanitize + 子进程 + 文本分离), 建议拆分
- **`auto_tag/__init__.py` 为空**: 无包级 API 导出
- **缺失 `console_scripts`**: 无 CLI 命令入口 (`pyproject.toml` 缺 `[project.scripts]`)
- **旧式 typing 不一致**: 部分文件有 `from __future__ import annotations`, 部分没有
- **双 venv**: `venv/` (pip) 和 `.venv/` (uv) 并存

## REFACTORING HISTORY

| 文件 | 变更 | 日期 |
|------|------|------|
| `audio_recognize.py` (3884 行) | 拆分为 6 模块包 `audio_recognize/` | 2026-07-16 |
| `lyric/manager.py` (2412 行) | 拆分为 4 子模块 + 门面 | 2026-07-16 |
| `editor/audio_editor.py` | `trim_audio()` 拆为 4 私有方法 | 2026-07-16 |
| `editor/workers/editor_worker.py` | `run()` 提取 `_process_single_file()` | 2026-07-16 |
| `gui/pages/converter_page.py` | `refresh_texts()` 拆为 5 方法 | 2026-07-16 |
| `gui/pages/home_page.py` | 19 处 `logger.exception` 错误处理加固 | 2026-07-16 |
| `gui/pages/music_manager_page.py` | 13 处 `logger.exception` 错误处理加固 | 2026-07-16 |
| `gui/pages/converter_page.py` | 14 处 `logger.exception` 错误处理加固 | 2026-07-16 |
| `tests/test_lyric_comprehensive.py` | 消除 110 行重复代码 | 2026-07-16 |

## COMMANDS

```bash
uv run python main.py              # 启动 GUI (默认)
uv run python main.py --gui false  # CLI 模式
uv run pytest tests/ -v            # 运行全部测试
uv run pytest tests/test_XXX.py -v # 单文件测试
uv run pre_release_validation.py   # 发布前验证
```

## NOTES

- `config.json` 存储在 `~/.mp3shazamautotag/` (旧项目名, 非 Imusic)
- 搜索源可插拔: 通过 `AppConfig.search_sources` 配置启用/禁用
- 关键词搜索模式: `smart_fallback` (默认) / `title_only` / `artist_title` / `filename_first`
- Acoustid API Key 硬编码在 `audio_recognize.py` (免费 100 次/天)
- QQ音乐搜索需用户自行提供 Cookie
- CI 测试使用 `continue-on-error: true` — 测试失败不阻断构建
