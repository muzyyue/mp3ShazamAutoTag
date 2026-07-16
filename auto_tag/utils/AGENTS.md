# auto_tag/utils — 工具模块知识库

## OVERVIEW

统一工具函数入口，提供文本处理、FFmpeg静默执行、文件操作、Cookie验证等基础设施，历史遗留的双版本共存模块。

## STRUCTURE

```
utils/
├── __init__.py          # 614行 — 统一API入口（含所有公有函数）
├── ffmpeg_utils.py      # 24行 — 纯重导出层，函数实现在 __init__.py
└── validation.py        # 180行 — QQ音乐Cookie验证/脱敏工具
```

## WHERE TO LOOK

| 函数 | 位置 | 说明 |
|------|------|------|
| `sanitize()` / `sanitize_filename_safe()` | `__init__.py:54,78` | 字符串清理 + 文件名安全化（200字符限制） |
| `find_deepest_metadata_key()` | `__init__.py:20` | 递归字典键搜索（不区分大小写） |
| `split_multilingual_text()` | `__init__.py:181` | 多语言文本分离（中文/日文/韩文→native, 英文→latin） |
| `is_file_in_use_error()` / `retry_on_file_in_use()` | `__init__.py:109,140` | 文件占用检测 + 自动重试装饰器 |
| `setup_ffmpeg_silent_mode()` / `run_ffmpeg_command()` | `__init__.py:566,448` | FFmpeg静默模式（monkey-patch subprocess.Popen） |
| `validate_qq_music_cookie()` | `validation.py:22` | QQ音乐Cookie完整性校验 |
| `test_legacy_import_restriction.py` | `tests/` | CI门禁 — 禁止直接导入 `_legacy_utils` |
| `test_ffmpeg_silent_mode.py` / `test_chinese_english_split.py` | `tests/` | 静默模式(21) + 多语言分离(10) 测试 |

## CRITICAL RULES

1. **导入铁律**: 所有外部模块必须 `from auto_tag.utils import <func>`。直接 `from auto_tag._legacy_utils import ...` 会被CI拦截，`test_legacy_import_restriction.py` 门禁守卫。
2. **函数实现在 `__init__.py`**: `ffmpeg_utils.py` 仅为重导出层，所有FFmpeg相关函数（`setup_ffmpeg_silent_mode`, `run_ffmpeg_command` 等）实现在 `__init__.py`。修改FFmpeg行为请直接编辑 `__init__.py`。
3. **monkey-patch 副作用**: `setup_ffmpeg_silent_mode()` 全局替换 `subprocess.Popen` 以隐藏Windows CMD窗口。调用后所有子进程均受影响。确保在 `main.py` 启动早期调用一次。
4. **旧版适配器已移除 (v0.6+)**: `__init__.py` 不再导出 `_legacy_*` 别名。所有模块已迁移至新版API。若遇到旧调用需先升级。
5. **`__init__.py` 拆分待办**: 614行混合了 sanitize、子进程、文本分离职责。新功能应放在独立模块（如 `text_utils.py`, `file_utils.py`），不要继续膨胀 `__init__.py`。

## NOTES

- `split_multilingual_text()` 原名 `chinese_english_split()`（历史遗留），测试文件未改名。
- `async_run_ffmpeg_command()` 通过重导出层访问，实际实现在 `__init__.py` 用 `run_ffmpeg_command` 配合 asyncio 封装。
- `validation.py` 中 `mask_cookie_for_logging()` 在日志脱敏场景复用，不限于QQ音乐。
- Cookie校验触发外部请求，测试时需 mock 网络层。
