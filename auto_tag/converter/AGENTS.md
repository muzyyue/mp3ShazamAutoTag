# CONVERTER MODULE KNOWLEDGE BASE

**Stack:** ffmpeg-python, mutagen, eyed3

## OVERVIEW

Audio format conversion module with 5 preset quality levels and custom format support, handling 12 input formats and 6 output formats via ffmpeg-python with metadata preservation.

## STRUCTURE

```
converter/
├── config.py             # ConverterConfig, FormatConfig, OutputFormat/QualityPreset enums (218 行)
├── converter.py          # AudioConverter — 格式检测, 单文件/批量转换 (501 行)
├── custom_format.py      # CustomFormatManager — 用户自定义格式增删改查+验证 (286 行)
├── metadata_manager.py   # MetadataManager — 跨格式元数据读写, 覆盖 MP3/FLAC/OGG/M4A (961 行)
├── workers/
│   └── converter_worker.py  # ConverterWorker(QThread) — 异步转换+进度信号 (244 行)
└── __init__.py           # 导出 AudioConverter, MetadataManager, ConverterConfig
```

## WHERE TO LOOK

| 任务 | 位置 | 说明 |
|------|------|------|
| 核心转换逻辑 | `converter.py` | AudioConverter: detect_format(), convert(), batch_convert() |
| 质量预设参数 | `config.py` → `FormatConfig._apply_quality_preset()` | low/medium/high/lossless 四档, 每种格式独立配置 |
| 自定义格式 | `custom_format.py` | CustomFormatManager: 增删改查, 验证扩展名/编解码器 |
| 元数据转移 | `metadata_manager.py` | 转换时从源文件读取并写入目标格式, 支持封面图 |
| 后台任务 | `workers/converter_worker.py` | QThread + progress_updated/file_converted/all_done 信号 |
| 输入格式列表 | `config.py:167-169` | 支持 mp3/flac/aac/ogg/wav/m4a/mp4/mkv/avi/mov/wmv/webm |

## NOTES

- 质量预设 (QualityPreset) 分 4 档: low/medium/high/lossless, 各输出格式参数独立配置
- MetadataManager 通过 mutagen + eyed3 处理跨格式元数据, 转换时自动迁移
- CustomFormatManager 管理用户自定义格式, 持久化在 config.json 中
- ConverterWorker 通过信号机制与 GUI 解耦, progress_updated(index, total, filename)
- 测试覆盖: `tests/test_audio_format_quality.py` (21 用例) 验证质量参数正确性
- 反模式: metadata_manager.py 达 961 行, 缺少独立单元测试
- 输入含视频格式 (mp4/mkv/avi/mov/wmv/webm) — 仅提取音频轨
