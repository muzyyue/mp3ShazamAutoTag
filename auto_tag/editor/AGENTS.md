# EDITOR MODULE

Audio trimming and EBU R128 loudness normalization (~1400 LOC, 6 files).

## STRUCTURE

```
editor/
├── audio_editor.py       # Core: AudioEditor class, 3-pass loudnorm, trim(4 modes)
├── config.py             # EditorConfig/NormalizeConfig/TrimConfig dataclasses + TrimMode enum
├── presets.py            # PresetManager: 5 builtin presets + custom preset CRUD
├── __init__.py           # Public API exports (AudioEditor, EditorConfig, PresetManager, ...)
└── workers/
    ├── editor_worker.py  # EditorWorker(QThread): async trim/normalize execution
    └── __init__.py
```

## WHERE TO LOOK

| Component | File | Key details |
|-----------|------|-------------|
| Core editor | `audio_editor.py` | `AudioEditor.trim_audio()`: AUTO(silence detect)/MANUAL(time)/DURATION(fixed)/NONE; fade in/out; 3-pass EBU R128 loudnorm; overwrite-original mode |
| Config model | `config.py` | `TrimMode`(AUTO/MANUAL/DURATION), `TrimConfig`(silence_threshold/-50dB, min_silence/1s, fade), `NormalizeConfig`(target_loudness/-16 LUFS, true_peak/-1.5, LRA/11), `EditorConfig`(composite) |
| Presets | `presets.py` | 5 builtin(ringtone/car_audio/hifi_archive/podcast/music_share), custom preset save/load to `~/.imusic/custom_presets.json`, i18n name/description(zh/en) |
| Worker | `workers/editor_worker.py` | QThread wrapping trim_audio(), progress signal, error handling |
| GUI page | `gui/pages/editor_page.py` | PySide6 editor interface (not in this module) |
| Tests | `tests/test_audio_editor.py` | 10 tests: trim modes, fade, silence detection, overwrite |
| Tests | `tests/test_editor_presets.py` | 26 tests: builtin/custom preset CRUD, validation, serialization |
| Tests | `tests/test_editor_overwrite.py` | 5 tests: overwrite original file safety |

## NOTES

- Trim mode NONE means trim is disabled (pass-through). AUTO uses `silencedetect` FFmpeg filter with configurable threshold/duration.
- Normalize is a 3-pass process: first pass measures loudness statistics, second pass applies gain, third pass verifies. Controlled via `NormalizeConfig`.
- `OutputQuality` enum (HIGH/STANDARD/SMALL) controls VBR quality and max bitrate independent of `QualityPreset`.
- Builtin presets are immutable (cannot be overwritten). Custom presets validate before save.
- Quality differentiation is covered by parametric tests across all trim/normalize/output combinations.
