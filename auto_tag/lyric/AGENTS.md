# Lyric Module Knowledge Base

## OVERVIEW
多提供者歌词管理模块 — 从 LRCLib/Apple Music/MusixMatch/网易云/酷狗获取歌词，支持嵌入/提取/格式转换，覆盖 MP3/FLAC/M4A/OGG/OPUS 格式。

## STRUCTURE

```
auto_tag/lyric/
├── __init__.py         # 包入口: 导出 LyricManager, LyricFetcher, LyricEmbedder 等
├── provider.py         # 提供商抽象: LyricProvider 数据类 + PROVIDERS 字典 + 动态导入
├── manager.py          # LyricManager (门面, ~230 行): 委托给子模块
├── lyric_utils.py      # 纯函数工具: LRC 解析, 元数据提取, 评分, 文本清理
├── lyric_fetcher.py    # LyricFetcher: 歌词获取/搜索/重试 (携 rate_limiter)
├── lyric_embedder.py   # LyricEmbedder: 歌词嵌入/提取 (MP3/FLAC/M4A/OGG)
├── lyric_converter.py  # LyricConverter: 格式转换 (LRC/TTML/SRT/JSON)
└── rate_limiter.py     # 令牌桶限流 + RequestMetrics 监控 (380 行)
```

## WHERE TO LOOK

| 任务 | 位置 | 说明 |
|------|------|------|
| 歌词获取/搜索 | `lyric_fetcher.py` → `LyricFetcher` | 携带 rate_limiter 状态 |
| 歌词嵌入/提取 | `lyric_embedder.py` → `LyricEmbedder` | 嵌入 MP3/FLAC/M4A/OGG |
| 格式转换 | `lyric_converter.py` → `LyricConverter` | 纯逻辑, 无状态 |
| 工具函数 | `lyric_utils.py` | LRC 解析, 元数据提取, 评分 |
| 提供商元数据 | `provider.py` → `PROVIDERS` | 5 个提供商: netease/kugou/lrclib/applemusic/musixmatch |
| 提供商路由 | `provider.py` → `get_provider()` / `get_provider_api()` | 名称→配置/API 动态导入 |
| 请求频率控制 | `rate_limiter.py` → `get_rate_limiter()` | 线程安全令牌桶 |
| 测试 (管理器) | `tests/test_lyric_manager.py` | 14 测试, CI 忽略 |
| 测试 (获取) | `tests/test_lyric_fetch.py` | 40 测试, 重 mock, CI 忽略 |
| 测试 (全面) | `tests/test_lyric_comprehensive.py` | 61 测试, 参数化 |
| 测试 (限流) | `tests/test_rate_limiter.py` | 17 测试 |

## CONVENTIONS

- **导入**: `from .provider import get_provider` / `from .rate_limiter import get_rate_limiter`
- **限流**: 所有 API 请求必须通过 `get_rate_limiter()` 令牌桶放行
- **线程安全**: `rate_limiter.py` 使用 `threading.Lock`; `manager.py` 使用 `threading.local()` 存储线程级 API 实例
- **文档字符串**: Google 风格, 中英混用, 含 `Example:` 节

## NOTES

- 后端通过 `importlib.import_module()` 动态加载 `lrxy` 或 `pymusiclibrary` 的提供商 API 模块
- 嵌入格式: MP3(eyed3 USLT/SYLT) / FLAC(Vorbis Comment) / M4A(©lyr) / OGG/OPUS(Vorbis Comment)
- 输出格式: LRC / TTML / SRT / JSON
- `manager.py` (2045 行) 违反单一职责, 应拆分: 获取/嵌入/提取/转换各为独立模块
- 两个测试文件被 CI 忽略 (`test_lyric_manager.py`, `test_lyric_fetch.py`), 重构前需先修复网络依赖
- 父级 AGENTS.md 仅列出 LRCLib/Apple/MusixMatch 三个提供商, 实际 `provider.py` 包含 netease 和 kugou 共五个
- 新增提供商步骤: `provider.py` 添加 `LyricProvider` 数据类 → 注册到 `PROVIDERS` 字典 → 确保后端库有对应 API 模块
