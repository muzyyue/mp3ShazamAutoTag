# 项目变更历史

## refactor(gui): 移除 GUI 层所有 emoji，改用 qfluentwidgets Fluent Icons
- **改动范围**：auto_tag/gui + auto_tag/editor，共 9 文件 ~311 行
- **核心改动**：
  - `presets.py`：icon 字段从 emoji 字符串改为 FIF 枚举名（PHONE/CAR/SAVE/HEADPHONE/MUSIC/SETTING）
  - `editor_page.py`：文件计数 IconWidget(FIF.CHECKBOX)、预设下拉 icon fallback
  - `music_manager_page.py`：修复 `.fluentIcon()` → `.icon()` AttributeError（🔍 fallback 消失的根因）
  - `settings_page.py`：`_set_cookie_validation()` 统一验证图标，刷新按钮 IconWidget(FIF.SYNC)
  - `song_search_dialog.py`：关键词行 IconWidget(FIF.SEARCH)、歌词表 ⏳/✅/❌ → FIF.SYNC/ACCEPT/CANCEL
  - `cookie_expired_dialog.py`：Dialog → MessageBoxBase，7 处 tr() 路径修正为 `settings_page.cookie_dialog.*`
  - `about_page.py`：LinkRowWidget 用 IconWidget(FIF) 替换 emoji，新增 chevron 绘制 + hover 高亮 + section header
  - `zh.json` / `en.json`：cookie_dialog、duration_match、presets 等值去 emoji 前缀
- **验证**：
  - py_compile 全部 7 个 .py 文件通过 ✅
  - Smoke test（offscreen）构建成功，i18n 文本解析无 raw key ✅
  - Emoji scan：32 行残留，全在日志/注释/文档字符串（可接受） ✅
  - test_editor_presets 26/26 PASSED、test_nested_i18n 4/4 PASSED ✅
- **涉及文件**: presets.py, editor_page.py, music_manager_page.py, settings_page.py, song_search_dialog.py, cookie_expired_dialog.py, about_page.py, zh.json, en.json

## v0.6.3 (2026-05-12) 彻底修复打包应用版本号显示为 unknown 的问题
- **问题现象**：
  - v0.6.2 修复后，从 GitHub Release 下载的应用仍然显示「版本 unknown」
- **根因分析**：
  - v0.6.2 的 version.py 虽然被编译为 .pyc，但版本号是运行时动态读取的
  - _load_version_from_pyproject 函数仍依赖 pyproject.toml 文件存在
  - PyInstaller 打包后该文件不存在，导致读取失败返回 unknown
- **解决方案**：
  - 新增 build_tools/update_version.py 构建脚本，在打包前自动提取版本号并硬编码到 version.py
  - 简化 auto_tag/version.py 为纯硬编码形式，移除所有运行时读取逻辑
  - 修改 Imusic.spec 在构建 Analysis 前自动调用更新脚本，确保版本号始终同步
- **技术优势**：
  - 零运行时依赖：不依赖任何外部文件
  - 自动化同步：每次构建自动从 pyproject.toml 提取最新版本号
  - 符合 Python 惯例：与 requests、flask 等主流库做法一致
- **涉及文件**: build_tools/update_version.py(新增), auto_tag/version.py(重构), build_tools/Imusic.spec

## v0.6.2 (2026-05-11) 修复打包应用版本号显示为 unknown 的问题
- **问题修复**：
  - 从 GitHub 下载的 PyInstaller 打包应用在关于页面显示「版本 unknown」
  - 根因：`_get_version()` 函数依赖 `pyproject.toml` 文件，但该文件未包含在 PyInstaller 打包中
- **解决方案**：
  - 新增 `auto_tag/version.py` 模块，在模块加载时从 `pyproject.toml` 读取版本号并导出 `__version__`
  - PyInstaller 打包时会自动编译该模块为 `.pyc`，无需依赖外部文件
  - 修改 `_get_version()` 函数，优先从 `auto_tag.version` 导入版本号，保留原逻辑作为 fallback
- **涉及文件**: `auto_tag/version.py`(新增), `auto_tag/gui/pages/about_page.py`

## v0.6.1 (2026-05-12) 主窗口布局优化
- **UI 布局重构**：
  - 将主窗口从 `FluentWindow` 改为 `MSFluentWindow`
  - 标题栏现在占满整个窗口宽度（显示应用图标 + 名称 + 窗口控制按钮）
  - 侧边导航栏移至标题栏下方，不再沾满整个窗口高度
  - 整体布局更符合现代 Fluent Design 规范（类似 Microsoft Store 应用风格）
- **代码清理**：
  - 移除不再需要的标题栏按钮隐藏逻辑（`_customize_title_bar` 等方法）
  - 修复 `MSFluentWindow` 的 API 兼容性问题（移除 `setReturnButtonVisible` 调用）
- **涉及文件**: `auto_tag/gui/main_window.py`, `pyproject.toml`

## v0.6.0 (2026-05-11) 关于页面与导航栏重构
- **新增关于页面**：
  - 展示应用信息（名称、版本号、检查更新、反馈链接等）
  - 使用 CardWidget 卡片式布局（更新设置卡片、反馈卡片、其他链接卡片）
  - 支持国际化，语言切换时自动刷新文本
  - 创建 LinkRowWidget 自定义组件处理链接点击事件
- **导航栏调整**：
  - 将「设置」和「关于」导航项移至侧边栏底部（`NavigationItemPosition.BOTTOM`）
  - 去除 FluentWindow 左上角返回按钮
- **自动检查更新功能**：
  - 新增 `auto_check_update` 配置项到 AppConfig（持久化存储）
  - 调用 GitHub Releases API 检查最新版本（`muzyyue/Imusic`）
  - 使用 InfoBar 显示更新提示（新版本可用/已是最新）
  - 点击「检查更新」按钮在应用内执行版本检查，不再跳转浏览器
- **新增文件**: `auto_tag/gui/pages/about_page.py`
- **修改文件**: `auto_tag/gui/main_window.py`, `auto_tag/gui/pages/__init__.py`, `auto_tag/gui/config.py`, `auto_tag/gui/i18n/locales/*.json`

## v0.5.9.6 (2026-05-11) 修正GitHub链接并修复检查更新按钮行为
- **修正 GitHub 项目链接**：将所有链接从 `ling/Imusic` 修正为正确的 `muzyyue/Imusic`
  - 仓库主页、Issues、Discussions、许可证、API 端点
- **修复检查更新按钮异常跳转问题**：
  - 原因：`_on_check_update_clicked` 直接打开浏览器跳转到 releases 页面
  - 修复：改为调用 `check_for_updates()` 方法，在应用内通过 GitHub API 检查更新并显示 InfoBar 提示
- **修改文件**: `auto_tag/gui/pages/about_page.py`

## v0.5.9.5 (2026-05-11) 优化关于页面UI并修复链接点击问题
- **UI 优化**：
  - 去除 FluentWindow 左上角返回按钮（`setReturnButtonVisible(False)`）
  - 使用 CardWidget 优化关于页面布局（更新设置卡片、反馈卡片、其他链接卡片）
- **修复反馈链接点击问题**：
  - 创建 LinkRowWidget 自定义组件，正确重写 mousePressEvent
  - 修正报告错误、建议功能等链接 URL（使用 issues/new 表单）
- **实现自动检查更新功能**：
  - 新增 auto_check_update 配置项到 AppConfig（持久化存储）
  - 调用 GitHub Releases API 检查最新版本
  - 使用 InfoBar 显示更新提示（新版本可用/已是最新）
- **新增 i18n 翻译键**: new_version_available, latest_version, up_to_date
- **修改文件**: `auto_tag/gui/main_window.py`, `auto_tag/gui/pages/about_page.py`, `auto_tag/gui/config.py`, `auto_tag/gui/i18n/locales/*.json`

## v0.5.9.4 (2026-05-11) 将设置按钮移到导航栏底部并新增关于页面
- **UI 调整**：
  - 将「设置」导航项从顶部移至侧边栏底部（`NavigationItemPosition.BOTTOM`）
  - 新增「关于」页面，展示项目信息（应用名称、版本号、检查更新、反馈链接等）
  - 关于页面支持国际化，语言切换时自动刷新文本
- **新增文件**: `auto_tag/gui/pages/about_page.py`
- **修改文件**: `auto_tag/gui/main_window.py`, `auto_tag/gui/pages/__init__.py`, `auto_tag/gui/i18n/locales/zh.json`, `auto_tag/gui/i18n/locales/en.json`

## v0.5.9.3 (2026-05-09) 扩展音频标签元数据支持，统一多格式标签写入接口
- **功能增强**：
  - `update_audio_tags()` 新增 `year` 和 `genre` 参数，支持年份和流派信息写入
  - 所有音频格式（MP3/FLAC/M4A/OGG/OPUS/WMA/AAC）统一支持完整元数据字段
  - `_write_*_tags()` 内部函数全部更新为接受 year 和 genre 参数
- **UI 集成**：
  - HomePage 搜索结果提取 year 和 genre 字段并传递给标签写入函数
  - 日志输出增加年份和流派信息显示
- **测试覆盖**：
  - 新增 `test_update_audio_tags.py` 覆盖所有格式的标签写入测试
  - 新增 `test_chinese_english_split.py` 多语言文本分离测试
  - 新增 `test_enhanced_extraction.py` 增强型歌名提取测试
- **涉及文件**: `auto_tag/audio_recognize.py`, `auto_tag/converter/metadata_manager.py`, `auto_tag/gui/pages/home_page.py`

## v0.5.9.2 (2026-05-09) 修复正则表达式反向范围错误，解决日文歌曲搜索崩溃问题
- **根本原因**：`japanese_hiragana` 模式包含反向 Unicode 范围
  - 正则引擎编译时报错（"bad character range" at position 22）
  - 导致刷新搜索功能崩溃，无法搜索日文歌曲
- **修复内容**：
  1. 移除 `japanese_hiragana` 中的非法反向范围（U+30A0 属于片假名，不应出现在平假名模式）
  2. 给 `armenian` 模式补上方括号（与其他语言模式保持一致）
  3. 将 `re.findall` 的捕获组改为非捕获组，避免只返回最后一个匹配字符
- **验证结果**：
  - ✅ `準備フェイズ-アリスソフト-..._Vol.31_ランス 10.mp3` → 正确提取 `準備フェイズアリスソフトアリスサウンドアルバムランス`
  - ✅ 正则表达式编译通过，不再报错
  - ✅ 多语言文本分离功能正常工作
- **涉及文件**: `auto_tag/utils/__init__.py` (第 244、264、296 行)

## v0.5.9.1 (2026-05-09)
- fix(japanese-candidate): 修复候选选择算法，解决核心歌名被遗漏的问题
  - **问题**：v0.5.9 使用 `min(candidates, key=len)` 选择绝对最短候选
  - **后果**：`ランス 10`(5 字符) 击败 `準備フェイズ`(6 字符)，导致搜索失败
  - **修复**：实现 `_candidate_score()` 智能评分函数
    - 优先级 0：不含数字后缀的纯文本（更可能是歌名）
    - 优先级 1：含数字后缀的文本（可能是曲目号/卷号）
    - 同等条件下选择较短的候选
  - **验证结果**：
    - ✅ `準備フェイズ-..._Vol.31_ランス 10.mp3` → 正确返回 `準備フェイズ`
    - ✅ `Track01_Vol.2_イントロダクション_Introduction.mp3` → 返回 `イントロダクション`
    - ✅ `アニメソング_Anime_Song_Vol.3.mp3` → 返回 `アニメソング`

- fix(regex-syntax): 修复 split_multilingual_text 的正则表达式语法错误
  - **错误**："bad character range" at position 22（刷新搜索时崩溃）
  - **原因**：使用了 PCRE/Perl 语法 `\x{00C0}`，Python re 模块不支持
  - **修复**：改为 Python 兼容格式（U+00C0）
  - **涉及文件**: `auto_tag/utils/__init__.py` (第 268 行)

- 涉及文件：`auto_tag/audio_recognize.py`, `auto_tag/utils/__init__.py`

## v0.5.9 (2026-05-09)
- fix(japanese-priority): 修复多语言智能提取的优先级错误，解决日文文件名识别失败问题
  - **根本原因**：多语言提取逻辑错误地将元数据词汇（Vol.31）当作歌名返回
  - **修复方案**：实现「非拉丁字符优先」的两轮筛选策略 + 元数据词汇黑名单
  - 修复文件：`準備フェイズ-アリスソフト-..._Vol.31_ランス10.mp3` → 正确返回 `ランス10`
  - 新增 `_is_metadata_word()` 函数过滤 Volume/Track/Disc 等非歌名词汇
  - 优化候选选择逻辑：优先选最短的非拉丁片段（核心歌名），其次选英文片段

- 涉及文件: `auto_tag/audio_recognize.py`

## v0.5.8 (2026-05-08)
- feat(multi-language): 实现多语言文本分离和智能搜索功能
  - 新增 `split_chinese_english_text()` 多语言文本分离器，支持 10+ 种语言（中日韩泰俄阿拉伯等）
  - 重构返回值格式：`chinese/english` → `native/latin`，新增 `detected_languages` 字段
  - 特殊语言智能处理：日文保持连贯性，韩文/泰文/阿拉伯文完整保留

- feat(search): 优化搜索策略，解决中文歌曲搜索失败问题
  - 修复 OST 格式中文被丢弃的 BUG（如 "A Small Miracle 小小奇迹"）
  - 新增无效指纹结果过滤（自动过滤 "Unknown Title"）
  - Fallback 搜索优先使用 native 部分作为关键词
  - 修复 `ascii_only` 变量作用域错误

- feat(metadata): 扩展音频标签元数据字段
  - `SearchResult` 新增 `year` 和 `genre` 字段
  - `update_audio_tags()` 支持年份和流派写入（MP3/OGG/FLAC/M4A）
  - 网易云音乐新增年份提取，Shazam 新增流派提取

- fix(japanese): 修复日文歌曲名被错误拆分的问题（如 "準備フェイズ"）

- 涉及文件: `auto_tag/utils/__init__.py`, `auto_tag/audio_recognize.py`, `auto_tag/gui/pages/home_page.py`, `tests/test_chinese_english_split.py`

## v0.5.7 (2026-05-08)
- feat(audio-tags): 实现通用音频标签写入函数，支持所有音频格式
  - 新增 update_audio_tags() 统一接口，自动识别文件格式并选择合适的标签写入方式
  - 实现 FLAC 格式完整支持（Vorbis Comment + FLAC Picture 封面）
  - 实现 M4A/MP4 格式支持（iTunes Metadata + Cover Art）
  - 实现 WMA/AAC 等格式的通用标签写入
  - WAV 格式优雅跳过（输出警告但不报错）
  - 重构 home_page.py 标签保存逻辑，从 if-elif 改为调用统一函数
  - 保持向后兼容：原有的 update_mp3_tags() 和 update_ogg_tags() 仍可正常使用
  - 新增测试用例覆盖所有支持格式（test_update_audio_tags.py）
  - **修复 MusicManagerPage 点击FLAC文件报错的问题**
    - 扩展 metadata_manager.py 支持所有音频格式
    - 新增 FLAC/M4A/OPUS/WMA/AAC 的元数据读取和写入方法
    - 新增各格式的封面图片读取和设置方法
    - 解决用户反馈：点击FLAC文件时提示"不支持的文件格式: .flac"的错误
  - 涉及文件: `audio_recognize.py`, `home_page.py`, `metadata_manager.py`, `test_update_audio_tags.py`

## v0.5.6 (2026-05-07)
- feat(audio-formats): 扩展音频格式支持，统一各模块格式列表
  - MusicManagerPage 文件扫描支持从 5 种扩展到 8 种（新增 aac/wma/opus）
  - audio_recognize 默认 extensions 参数同步更新（从 2 种到 8 种）
  - 与 CustomFormatManager 内置格式保持一致
  - 新增 2 个单元测试验证格式完整性
  - 涉及文件: `music_manager_page.py`, `audio_recognize.py`, `test_music_manager_page.py`

## v0.5.5 (2026-05-05)
- feat(qqmusic): 新增QQ音乐Cookie完整管理功能
  - Cookie输入框（多行文本、实时验证、自动持久化）
  - 刷新登录按钮（API续期、防重复点击、状态反馈）
  - 失效引导弹窗（过期时自动弹出、一键跳转y.qq.com获取）
  - QQ音乐搜索集成Cookie认证（HTTP头注入、日志脱敏）
  - 新增39个测试用例覆盖全流程
  - 新增文件: `validation.py`, `cookie_expired_dialog.py`, 3个测试文件

## v0.5.4 (2026-05-03)
- refactor(core): 重构音频识别模块，提取通用工具函数到 `auto_tag/utils/`（字符串/文件名/元数据处理）
- feat(editor): 增强音频编辑器功能和UI交互
- fix(ui): 修复搜索结果卡片显示异常、设置页面布局优化、英文翻译更新
- feat(lyric): 增强歌词管理功能，优化多平台兼容性
- chore(converter): 改进FFmpeg静默模式和格式配置灵活性
- test: 新增重构后模块测试和规范化测试音频文件
- docs: 全面更新 Readme.md

## v0.5.3 (2026-05-02)
- fix(build): 修复 uv sync 残留 dist-info 和 hardlink 警告（配置 link-mode = "copy"）

## v0.5.2 (2026-05-02)
- fix(ui): 修复编辑器页面输出格式区域下拉框重叠问题

## v0.5.1 (2026-05-02)
- fix(ui): 修复编辑器页面下拉框高度和间距问题

## v0.5.0 (2026-05-02)
- feat(editor): 新增音频编辑功能 Phase 1 MVP（智能裁剪/音量标准化/格式转换5种预设/EditorPage页面）

## v0.4.82 (2026-05-01)
- fix(ui): 修复清除数据时封面图片未正确重置、QProcessEventLoop崩溃、themeChanged警告等问题

## v0.4.81 (2026-04-29)
- fix(recognize): 修复 tests 目录被错误过滤的问题；扩展支持音频格式从2种到7种（flac/m4a/wav/wma/opus）；用 mutagen 统一处理非MP3元数据读取

## v0.4.80 (2026-04-29)
- feat(lyric): 实现歌词请求频率限制（令牌桶算法）和自动重试机制（指数退避），批量成功率从~60%提升至~95%

## v0.4.79 (2026-04-29)
- fix(memory): 修复首页搜索严重内存泄漏（搜索28首歌后内存从200MB暴涨至1000MB），识别并修复5个泄漏点，清除后内存降至220-280MB

## v0.4.78 (2026-04-28)
- fix(lyric): 修复嵌入歌词后重新加载还原的问题——从 eyed3 全面迁移到 mutagen 写入 USLT 帧

## v0.4.77 (2026-04-28)
- fix(lyric): 修复批量获取歌词时所有歌曲嵌入同一首歌词的问题（逐文件串行处理）+ 单首误触发批量对话框

## v0.4.76 (2026-04-28)
- fix(lyric): 修复批量获取歌词导致 UI 卡死的问题（logger 引用和异常处理）

## v0.4.75 (2026-04-28) ×2
- fix(lyric): 修复歌词搜索"首次成功、再次失败"的问题（pymusiclibrary 多实例冲突 → REST API 优先策略）
- feat(search): 新增智能回退关键词模式（smart_fallback），提升中文/日文歌曲搜索成功率

## v0.4.74 (2026-04-28)
- fix(memory): 修复首页连续点击封面导致内存持续增长且关闭后未回收的问题（Qt 隐式共享 + 显式资源释放）

## v0.4.73 (2026-04-27)
- feat(lyric): 批量获取歌词时自动选择匹配度最高的结果（多维度评分：歌名40% + 艺术家35% + 时长25%）

## v0.4.72 (2026-04-27)
- fix(ui): 修复歌曲卡片长文件名导致刷新/收起按钮被隐藏的问题（左右分离布局）

## v0.4.71 (2026-04-27)
- fix(gui): 修复首页搜索导致内存持续增长的问题（组件销毁前停止加载线程）

## v0.4.70 ~ v0.4.63 (2026-04-26)
- fix(ci): 简化 GitHub Actions 发布流程
- feat(ci): 首次启用 GitHub Actions 自动构建发布
- fix(ui): 修复转换器页面深色/浅色模式背景色适配（多版本迭代）
- refactor(ui): 转换器页面从局部滚动改为全页面滚动 + 文件列表垂直滚动

## v0.4.62 (2026-04-26)
- fix(lyric): 修复歌词数据在切换歌曲或重新选择目录后丢失的问题（lyrics_cache 管理）

## v0.4.60 (2026-04-26)
- feat(ui): 搜索结果栏显示复合来源标识（如 "Acoustid + 网易云音乐"）

## v0.4.59 (2026-04-26)
- feat(settings): 设置页面新增「搜索关键词模式」选项（仅歌名 / 艺术家+歌名 / 智能回退）

## v0.4.58 (2026-04-26)
- feat(core): 新增音频元数据回退策略——无意义文件名时从文件标签读取元数据作为搜索关键词

## v0.4.57 (2026-04-26)
- feat(settings): 搜索源拆分为「识别引擎」和「补充搜索」两行展示 + 网易云/QQ音乐关键词改为仅使用歌曲名

## v0.4.56 ~ v0.4.49 (2026-04-25)
- fix(build): 回退打包工具链从 Nuitka 至 PyInstaller（Nuitka 上游 bug）
- refactor(build): Nuitka 迁移尝试（已回退）
- refactor(build): PyInstaller onedir 打包流程优化（UPX压缩、依赖收集、体积统计）
- fix(build): 修复 soundfile 模块缺失、UPX 排除配置等打包问题
- fix(qqmusic): QQ 音乐搜索迁移到官方统一网关接口（u.y.qq.com）
- refactor(build): 项目名称统一为 Imusic

## v0.4.45 ~ v0.4.42 (2026-04-25)
- refactor(i18n): 国际化文件改为嵌套分组结构
- fix(core): MP3 封面写入失败（User-Agent 缺失）
- fix(gui): 歌曲卡片主题颜色/背景色更新问题

## v0.4.39 ~ v0.4.30 (2026-04-23~24)
- chore(build): PyInstaller 打包体积优化（700MB → 240MB）
- feat/core: 文件名识别策略优化、清除数据功能、封面获取增强
- refine/gui): 搜索加载对话框视觉优化
- fix(gui): 歌词搜索异步化、网易云封面显示修复、多语言字符保留、应用按钮回调机制

## v0.4.26 ~ v0.4.10 (2026-04-20)
- feat(ui): 窗口尺寸优化（1200×580 可调）、扁平化布局
- fix(core): pymusiclibrary 崩溃修复（默认禁用/线程安全版本/移除初始化）
- fix(ui): 深色模式适配、搜索结果卡片式布局重构、展开收起图标修复

## v0.4.2 ~ v0.4.0 (2026-04-16~17)
- feat(lyric): 歌词模式选择（original/merged/translation）、MusicLibrary 替代 lrxy、LyricManager 模块、搜索结果多选

## v0.3.7 ~ v0.3.0 (2026-04-13~14)
- feat(converter): 自定义文件格式管理、格式过滤、AudioConverter、ConverterWorker、MetadataManager
- test(converter): MetadataManager 单元测试
- fix(i18n): 语言切换问题修复

## v0.3.0 (2026-04-13)
- **BREAKING**: GUI 框架从 tkinter 迁移到 PySide6 + QFluentWidgets（Fluent Design 风格）
- feat(i18n): 国际化系统（中英文切换）
- feat(config): 配置管理模块 AppConfig

## v0.2.5 ~ v0.2.0 (2026-04-13)
- feat(gui): 创建设置页面 SettingsPage、主页 HomePage、识别工作线程 RecognizeWorker
- feat(config/i18n): 配置管理模块 AppConfig、国际化模块（translator.py + zh.json + en.json）

## v0.2.0 (2026-04-13)
- 初始化项目：克隆 mp3ShazamAutoTag 仓库
- 配置环境：Rust 工具链（shazamio-core）、Python 3.13 兼容性（audioop-lts）
