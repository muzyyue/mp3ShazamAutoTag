# GUI KNOWLEDGE BASE

## OVERVIEW

PySide6 + QFluentWidgets Fluent Design GUI layer -- 24 files, ~9200 lines across 6 subpackages.

## STRUCTURE

```
gui/
├── __init__.py          # launch_gui(): app lifecycle orchestrator
├── main_window.py       # MSFluentWindow with sidebar nav (6 pages)
├── config.py            # AppConfig singleton, JSON persistence
├── style.qss            # Fluent Design overrides
├── pages/               # 6 page views
│   ├── home_page.py          # File list, recognize, tag preview
│   ├── music_manager_page.py # Batch tag editing GUI
│   ├── converter_page.py     # Format conversion presets + custom
│   ├── editor_page.py        # Audio trim + loudnorm controls
│   ├── settings_page.py      # All config: sources, cookie, theme, lang
│   └── about_page.py         # Version, credits
├── components/          # Reusable widgets
│   ├── cover_preview_dialog.py
│   ├── song_result_card.py
│   └── song_search_dialog.py
├── dialogs/
│   └── cookie_expired_dialog.py
├── workers/             # QThread async workers
│   ├── recognize_worker.py
│   ├── lyric_worker.py
│   └── song_search_worker.py
└── i18n/
    ├── translator.py    # Translator singleton, tr() function
    └── locales/{zh,en}.json
```

## WHERE TO LOOK

| Task | File | Notes |
|------|------|-------|
| App entry, lifecycle | `__init__.py` | `launch_gui()`: ffmpeg init, MusicLibrary, QApplication, theme/lang |
| Nav structure, page wiring | `main_window.py` | Subclass of `MSFluentWindow`, items at bottom: Settings, About |
| Runtime config | `config.py` | AppConfig singleton, stores to `~/.mp3shazamautotag/config.json` |
| Recognize flow orchestration | `pages/home_page.py` | File drop, Shazam/acoustid/netease trigger, results display |
| Batch tag editor | `pages/music_manager_page.py` | ID3 tag table, inline editing |
| Format conversion | `pages/converter_page.py` | 5 presets, custom format config |
| Audio editor | `pages/editor_page.py` | Trim start/end, loudnorm params, preview |
| Settings, search sources | `pages/settings_page.py` | Source enable/disable, keyword mode, QQ Cookie input |
| Async tasks (QThread) | `workers/recognize_worker.py` | Pattern for all workers |
| Lyric fetch + embed | `workers/lyric_worker.py` | LRCLib/Apple/MusixMatch providers |
| Song search (multiple sources) | `workers/song_search_worker.py` | Orchestrates netease/kugou/qqmusic search |
| Translation | `i18n/translator.py` | Singleton, `tr()` helper, JSON locale files |
| Search widget | `components/song_search_dialog.py` | Multi-source keyword search dialog |
| Cover preview | `components/cover_preview_dialog.py` | Album art display |
| Cookie expired prompt | `dialogs/cookie_expired_dialog.py` | QQ Music cookie re-auth dialog |

## CONVENTIONS

- **Async in GUI**: QThread pattern (not asyncio). Workers subclass `QObject`, moved to `QThread` via `moveToThread()`.
- **i18n**: Always use `from auto_tag.gui.i18n import tr`; never use raw strings for user-facing text.
- **Config access**: Singleton pattern: `from auto_tag.gui.config import config` (note: lowercase instance).
- **Signal/Slot**: All worker results communicated via Qt signals (`finished`, `error`, `progress`).
- **Page registration**: Pages registered in `main_window.py` via `addSubInterface()`; order determined by `NavigationItemPosition`.
- **Theme switching**: Uses `qfluentwidgets.setTheme()` with light/dark/auto.

## NOTES

- 4 files lack unit tests: `home_page.py`, `editor_page.py`, `about_page.py`, `song_search_dialog.py`.
- AppConfig holds ALL runtime config: search sources, keyword mode, QQ Music cookie, ascii-only filenames, editor params.
- Cookie validation: `config.py` checks `uin`, `qm_keyst`, `qqmusic_key` in QQ Cookie string.
- Keyword modes (set in settings): `smart_fallback` (default), `title_only`, `artist_title`, `filename_first`.
- Search sources: `acoustid`, `shazam`, `netease`, `kugou`, `qqmusic` -- all configurable via `settings_page.py`.
- `style.qss` applies Fluent Design overrides; loaded in `MainWindow.__init__()`.
- No lazy page loading -- all pages created at startup in `MainWindow.__init__()`.
