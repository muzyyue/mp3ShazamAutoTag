# auto_tag/audio_recognize/_metadata.py
"""
Metadata extraction and keyword building module.

Handles reading audio file metadata via mutagen/eyed3, validating metadata,
extracting song names from filenames, and building search keywords.

Depends on: nothing internal (self-contained)
"""

from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)


def _safe_filename(text: str, ascii_only: bool = False) -> str:
    """
    生成安全的文件名（可选 ASCII-only 转换）

    使用新版 sanitize() 清理控制字符，并可选地使用 unidecode 转换为纯 ASCII。

    Args:
        text: 输入文本
        ascii_only: 是否转换为纯 ASCII（默认 False，保留原始 Unicode 字符）

    Returns:
        str: 安全的文件名字符串
    """
    from auto_tag.utils import sanitize as new_sanitize

    cleaned = new_sanitize(text)

    if ascii_only and cleaned:
        try:
            from unidecode import unidecode
            cleaned = unidecode(cleaned)
        except ImportError:
            logger.warning("unidecode 未安装，跳过 ASCII 转换")

    return cleaned or "Unknown"


def read_audio_metadata_mutagen(file_path: str) -> dict[str, str]:
    """
    使用 mutagen 库统一读取音频文件元数据

    支持所有常见音频格式：MP3, OGG (Vorbis/Opus), FLAC, M4A, WAV, WMA 等。
    作为通用的元数据提取接口，为识别流程提供回退搜索关键词。

    Args:
        file_path: 音频文件路径

    Returns:
        dict: 包含 title, artist, album 的字典，空字符串表示未找到
    """
    from mutagen import File

    metadata = {"title": "", "artist": "", "album": ""}

    try:
        audio = File(file_path)

        if audio is None:
            logger.debug(f"[MutagenMetadata] Unsupported format or corrupt file: {file_path}")
            return metadata

        # 统一标签键名映射（处理不同格式的大小写差异）
        tag_mappings = {
            "title": ["title", "TIT2", "\xa9nam"],  # 通用/Vorbis/ID3v2/iTunes
            "artist": ["artist", "TPE1", "\xa9ART"],
            "album": ["album", "TALB", "\xa9alb"],
        }

        for field, possible_keys in tag_mappings.items():
            value = ""
            for key in possible_keys:
                try:
                    if key in audio.tags:
                        raw_value = audio.tags[key]
                        if isinstance(raw_value, list):
                            value = raw_value[0] if raw_value else ""
                        else:
                            value = str(raw_value)
                        if value:
                            break
                except (KeyError, AttributeError, TypeError):
                    continue

            metadata[field] = value or ""

        logger.debug(
            f"[MutagenMetadata] Read from {os.path.basename(file_path)}: "
            f"title='{metadata['title']}', artist='{metadata['artist']}', album='{metadata['album']}'"
        )

    except Exception as e:
        logger.debug(f"[MutagenMetadata] Failed to read metadata: {e}")

    return metadata


def _read_audio_metadata_from_file(file_path: str) -> dict[str, str]:
    """
    从音频文件内部读取元数据标签（兼容层）

    优先使用 eyed3 处理 MP3 格式（保持向后兼容），
    其他格式统一使用 mutagen 库读取。
    当音频指纹引擎失败且文件名无意义时，使用此函数
    尝试从文件内部标签提取搜索关键词。

    Args:
        file_path: 音频文件路径

    Returns:
        dict: 包含 title, artist, album 的字典，空字符串表示未找到
    """
    import eyed3

    ext = os.path.splitext(file_path)[1].lower()

    # MP3 格式：继续使用 eyed3（历史原因，eyed3 对 ID3 标签支持更完善）
    if ext == ".mp3":
        metadata = {"title": "", "artist": "", "album": ""}
        try:
            audio = eyed3.load(file_path)
            if audio and audio.tag:
                metadata["title"] = audio.tag.title or ""
                metadata["artist"] = audio.tag.artist or ""
                metadata["album"] = audio.tag.album or ""
        except Exception as e:
            logger.debug(f"[MetadataFallback] eyed3 failed for {file_path}: {e}")
        return metadata

    # 其他所有格式：使用 mutagen 统一接口
    return read_audio_metadata_mutagen(file_path)


def _is_metadata_valid(metadata: dict[str, str]) -> bool:
    """
    检查从文件读取的元数据是否有效（可用于搜索）

    有效的元数据至少包含标题或艺术家，且不是默认的占位符值。

    Args:
        metadata: 包含 title, artist 的字典

    Returns:
        bool: 元数据是否有效
    """
    title = metadata.get("title", "").strip()
    artist = metadata.get("artist", "").strip()

    if not title and not artist:
        return False

    # 排除常见的占位符值
    placeholder_values = {
        "unknown", "unknown title", "unknown artist", "unknown album",
        "", "n/a", "none",
    }

    title_lower = title.lower()
    artist_lower = artist.lower()

    if title_lower in placeholder_values and artist_lower in placeholder_values:
        return False

    return True


def _build_keyword_from_metadata(metadata: dict[str, str]) -> str:
    """
    从元数据构建搜索关键词

    Args:
        metadata: 包含 title, artist 的字典

    Returns:
        str: 搜索关键词（格式："Artist Title" 或 "Title"）
    """
    title = metadata.get("title", "").strip()
    artist = metadata.get("artist", "").strip()

    if artist and title:
        return f"{artist} {title}"
    elif title:
        return title
    elif artist:
        return artist
    return ""


def _is_filename_like_song_name(file_path: str) -> bool:
    """
    判断文件名是否像歌曲名

    识别以下情况为"不像歌曲名"：
    - 包含连续数字/下划线组合（如 32671414_da3-1-30216）
    - 纯数字或数字占主导
    - 包含常见无意义前缀/后缀（如 download, temp, rec）
    - 文件名过长且无空格/分隔符
    - 仅包含特殊字符

    Args:
        file_path: 文件完整路径

    Returns:
        bool: True 表示像歌曲名，False 表示不像歌曲名
    """
    import re

    filename = os.path.basename(file_path)
    name_without_ext, ext = os.path.splitext(filename)
    name_without_ext = name_without_ext.strip()

    # 处理只有扩展名没有文件名的情况（如 ".mp3"）
    if not name_without_ext or name_without_ext.startswith('.'):
        return False

    # 规则1: 包含连续数字+下划线+数字模式（如 32671414_da3-1-30216）
    if re.search(r'\d+[_\-]\w+[_\-]\d+', name_without_ext):
        logger.info(f"[FilenameCheck] Not song-like (pattern): {filename}")
        return False

    # 规则2: 纯数字或数字占比超过70%
    digit_count = sum(1 for c in name_without_ext if c.isdigit())
    total_chars = len(name_without_ext.replace(' ', '').replace('-', ''))
    if total_chars > 0 and digit_count / total_chars > 0.7:
        logger.info(f"[FilenameCheck] Not song-like (too many digits): {filename}")
        return False

    # 规则3: 包含常见无意义关键词（英文使用单词边界或下划线/连字符边界匹配，中文直接使用 in 检查）
    meaningless_keywords = [
        'download', 'temp', 'rec', 'record', 'recording', 'audio',
        'sound', 'untitled', 'noname', 'unknown',
        '新建', '未命名', '录音', '音频'
    ]
    name_lower = name_without_ext.lower()
    for kw in meaningless_keywords:
        if re.match(r'^[a-zA-Z]+$', kw):
            # 英文短词：匹配开始/结束或空白/下划线/连字符边界
            pattern = r'(?:^|[\s_\-])' + re.escape(kw) + r'(?:$|[\s_\-])'
            if re.search(pattern, name_lower):
                logger.info(f"[FilenameCheck] Not song-like (keyword '{kw}'): {filename}")
                return False
        else:
            if kw in name_lower:
                logger.info(f"[FilenameCheck] Not song-like (keyword '{kw}'): {filename}")
                return False

    # 规则4: 文件名过长（>50字符）且无空格/分隔符
    if len(name_without_ext) > 50 and ' ' not in name_without_ext and '-' not in name_without_ext:
        logger.info(f"[FilenameCheck] Not song-like (too long): {filename}")
        return False

    # 规则5: 仅包含特殊字符（添加韩文范围 \uac00-\ud7af）
    if re.match(r'^[^a-zA-Z\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]+$', name_without_ext):
        logger.info(f"[FilenameCheck] Not song-like (no valid chars): {filename}")
        return False

    logger.info(f"[FilenameCheck] Song-like filename: {filename}")
    return True


def _enhanced_extract_song_name(file_path: str) -> str:
    """
    增强版歌曲名提取器（多阶段解析流水线）

    支持的文件名格式：
    - OST 格式: "01. A Small Miracle 小小奇迹 (Instrumental).flac"
    - Track 格式: "Track 01 Title.mp3" / "01 Title.mp3"
    - 标准格式: "Artist - Title.mp3" / "Title - Artist.mp3"
    - 简单格式: "Title.mp3"

    处理流程：
    1. 预处理：移除扩展名、序号前缀
    2. 清理：移除括号标签（(Instrumental)、(Off Vocal) 等）
    3. 解析：多模式智能匹配
    4. 输出：清理后的关键词

    Args:
        file_path: 文件完整路径

    Returns:
        str: 提取的歌曲名/关键词
    """
    import re

    filename = os.path.basename(file_path)
    name_without_ext = os.path.splitext(filename)[0].strip()

    if not name_without_ext or name_without_ext.startswith('.'):
        return ""

    name = name_without_ext

    # 阶段 1: 移除序号前缀
    # 匹配: "01.", "1.", "Track 01", "Track01", "01 ", "01-" 等
    track_patterns = [
        r'^Track\s*[\.\-\s]?\d+[\.\-\s]+',      # Track 01, Track.01, Track-01
        r'^\d+[\.\-\s]{1,2}',                     # 01., 01-, 01 , 01_ (最多2个分隔符)
        r'^\[\d+\]\s*',                            # [01]
    ]
    for pattern in track_patterns:
        name = re.sub(pattern, '', name, flags=re.IGNORECASE).strip()

    # 阶段 2: 移除括号标签（保留核心名称）
    # 常见标签: (Instrumental), (Off Vocal), (TV Size), (Full Version), [OP], [ED] 等
    tag_patterns = [
        r'\s*\([^)]*(?:Instrumental|Off.Vocal|TV.Size|Full.Version|Short.Version|Radio.Edit|Extended|Remix)[^)]*\)\s*$',
        r'\s*\[[^\]]*(?:OP|ED|Insert.Song|Theme|Ending|Opening)[^\]]*\]\s*$',
        r'\s*\([^)]*\)\s*$',                      # 移除末尾任意括号内容（兜底）
        r'\s*\[[^\]]*\]\s*$',                      # 移除末尾任意方括号内容（兜底）
    ]
    for pattern in tag_patterns:
        name = re.sub(pattern, '', name, flags=re.IGNORECASE).strip()

    # 阶段 3: 多余空白标准化
    name = re.sub(r'\s+', ' ', name).strip()

    # 阶段 4: 智能分离艺术家和歌曲名
    # 优先级 1: 标准 " - " 分隔符（最可靠）
    if ' - ' in name:
        parts = name.split(' - ', 1)
        parts = [p.strip() for p in parts if p.strip()]
        if len(parts) >= 2:
            result = f"{parts[0]} {parts[1]}"
            logger.info(f"[EnhancedKeyword] Standard format '{filename}': {result}")
            return result

    # 优先级 2: OST 格式检测（多方向支持）

    # 模式 A: 英文 + 日文/中文 (传统 OST)
    # "English Title 中文名称" 或 "A Small Miracle 小小奇迹"
    ost_pattern_en_first = r'^([A-Za-z0-9\s\'\-\,\.\!\?]+)([\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]+.*)$'
    ost_match_a = re.match(ost_pattern_en_first, name)
    if ost_match_a:
        english_part = ost_match_a.group(1).strip()
        native_part = ost_match_a.group(2).strip()
        result = f"{english_part} {native_part}".strip()
        logger.info(f"[EnhancedKeyword] OST-A format '{filename}': '{result}' (EN-first)")
        return result

    # 模式 B: 日文/中文 + 英文 (反向 OST) ★新增★
    # "日本語タイトル English Title" 或 "準備フェイズ Vol.31"
    # 支持日文/中文开头的混合文本
    ost_pattern_native_first = r'^([\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af\u0e00-\u0e7f]+.*?)([A-Za-z][A-Za-z0-9\s\'\-]*[0-9]+.*)$'
    ost_match_b = re.match(ost_pattern_native_first, name)
    if ost_match_b:
        native_part = ost_match_b.group(1).strip()
        latin_part = ost_match_b.group(2).strip()

        # 对于日文开头的文本，尝试提取核心歌曲名（通常是第一个短片段）
        # 例如: "準備フェイズ-アリスソフト-..." → 核心是 "準備フェイズ"
        if '-' in native_part or '_' in native_part:
            # 有分隔符，取第一部分作为歌曲名
            core_name = re.split(r'[-_]', native_part)[0].strip()
            if len(core_name) >= 2 and len(core_name) < len(native_part):
                result = f"{core_name} {latin_part}".strip()
                logger.info(f"[EnhancedKeyword] OST-B format '{filename}': '{result}' (native-first, extracted core)")
                return result

        # 无分隔符或提取失败，返回完整混合
        result = f"{native_part} {latin_part}".strip()
        logger.info(f"[EnhancedKeyword] OST-B format '{filename}': '{result}' (native-first)")
        return result

    # 优先级 2.5: 多语言智能提取 ★关键优化★
    # 对于包含非拉丁字符的文本（中日韩泰等），在处理下划线/分隔符之前
    # 先尝试提取核心歌曲名，避免返回过长的关键词
    from auto_tag.utils import is_multilingual_text

    if is_multilingual_text(name):
        # 检测是否有多个分隔符（可能是 "艺术家-专辑_卷号-歌曲名" 格式）
        separators = ['-', '_']
        has_multiple_seps = any(name.count(sep) >= 2 for sep in separators)

        if has_multiple_seps:
            # 元数据词汇黑名单（这些词不可能是歌名）
            METADATA_BLACKLIST = {
                'vol', 'volume', 'track', 'disc', 'cd', 'part',
                'chapter', 'act', 'scene', 'ep', 'episode',
                'no', 'number', 'ver', 'version', 'remix',
                'ost', 'original', 'soundtrack', 'album',
            }

            def _is_metadata_word(text: str) -> bool:
                """检测是否是元数据词汇（如 Volume, Track 等）"""
                text_lower = text.lower().replace('.', '').replace('-', '').replace('_', '').strip()
                return text_lower in METADATA_BLACKLIST or bool(re.match(r'^(vol|track|disc|cd)\s*\.?\s*\d+$', text_lower))

            NON_LATIN_PATTERN = r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3040-\u309f\u31f0-\u31ff\u30a0-\u30ff\uac00-\ud7af\u1100-\u11ff\u0e00-\u0e7f]'

            # 策略：两轮筛选 - 优先选择非拉丁字符的核心歌名
            non_latin_candidates = []   # 包含日文/中文的候选
            latin_candidates = []       # 纯英文候选

            for sep in reversed(separators):  # 优先用 _
                if name.count(sep) >= 2:
                    parts = name.split(sep)
                    for part in parts:
                        part = part.strip()
                        if not (2 <= len(part) <= 25):
                            continue

                        has_non_latin = bool(re.search(NON_LATIN_PATTERN, part))
                        has_english = bool(re.search(r'[a-zA-Z]{2,}', part))

                        # 排除元数据词汇和纯数字
                        if _is_metadata_word(part) or re.match(r'^[\d\s\.\-]+$', part):
                            logger.debug(f"[EnhancedKeyword] Skip metadata word: '{part}'")
                            continue

                        if has_non_latin:
                            non_latin_candidates.append(part)
                        elif has_english:
                            latin_candidates.append(part)

            # 优先级 1: 返回最佳的非拉丁候选（智能选择策略）
            # 策略：优先选择"纯文本"（无数字后缀），因为歌曲名通常不包含数字
            # 例如: '準備フェイズ' > 'ランス10' （前者是歌名，后者是曲目号）
            if non_latin_candidates:
                def _candidate_score(candidate: str) -> tuple:
                    """
                    候选评分函数 - 返回 (优先级, 长度) 元组用于排序

                    排序规则：
                    1. 不含数字的纯文本优先（更可能是歌名）
                    2. 长度适中的优先（太短可能是缩写，太长可能是专辑名）
                    3. 同等条件下选较短的
                    """
                    has_trailing_digits = bool(re.search(r'\d+$', candidate))
                    length = len(candidate)

                    # 优先级：0 = 无数字（高优），1 = 有数字（低优）
                    priority = 0 if not has_trailing_digits else 1

                    return (priority, length)

                # 按评分排序，选择最佳候选
                sorted_candidates = sorted(non_latin_candidates, key=_candidate_score)
                best_candidate = sorted_candidates[0]

                logger.info(
                    f"[EnhancedKeyword] Multi-lang native priority '{filename}': '{best_candidate}' "
                    f"(from {len(non_latin_candidates)} candidates, score={_candidate_score(best_candidate)})"
                )
                return best_candidate

            # 优先级 2: 返回最短的英文候选（排除元数据词后）
            if latin_candidates:
                best_candidate = min(latin_candidates, key=len)
                logger.info(f"[EnhancedKeyword] Multi-lang latin fallback '{filename}': '{best_candidate}' (from {len(latin_candidates)} candidates)")
                return best_candidate

            # 如果上面的策略失败，使用 OST-B 的逻辑
            ost_pattern_native_first = r'^([\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af\u0e00-\u0e7f]+.*?)([A-Za-z][A-Za-z0-9\s\'\-]*[0-9]+.*)$'
            ost_match_b = re.match(ost_pattern_native_first, name)
            if ost_match_b:
                native_part = ost_match_b.group(1).strip()
                latin_part = ost_match_b.group(2).strip()

                if '-' in native_part or '_' in native_part:
                    core_name = re.split(r'[-_]', native_part)[0].strip()
                    if len(core_name) >= 2 and len(core_name) < len(native_part) * 0.5:
                        result = f"{core_name} {latin_part}".strip()
                        logger.info(f"[EnhancedKeyword] Multi-lang OST-B '{filename}': '{result}' (core extracted)")
                        return result

    # 优先级 3: 其他常见分隔符
    # 对于下划线，替换所有出现；对于其他分隔符，只分割一次
    if '_' in name:
        result = name.replace('_', ' ')
        logger.info(f"[EnhancedKeyword] Underscore format '{filename}': {result}")
        return result

    other_separators = ['-', '–', '—']
    for sep in other_separators:
        if sep in name and sep != ' - ':  # 避免重复处理
            parts = name.split(sep, 1)
            parts = [p.strip() for p in parts if p.strip()]
            if len(parts) >= 2 and all(len(p) > 1 for p in parts):
                result = f"{parts[0]} {parts[1]}"
                logger.info(f"[EnhancedKeyword] Separator format '{filename}' ({sep}): {result}")
                return result

    # 兜底: 使用清理后的完整文件名
    logger.info(f"[EnhancedKeyword] Fallback '{filename}': {name}")
    return name


def _build_search_keyword_from_filename(file_path: str) -> str:
    """
    从文件名提取搜索关键词（增强版）

    支持的文件名格式：
    - OST 格式: "01. A Small Miracle 小小奇迹 (Instrumental).flac" → "A Small Miracle"
    - 标准格式: "艺术家 - 歌曲名.mp3" → "艺术家 歌曲名"
    - 简单格式: "歌曲名.mp3" → "歌曲名"

    Args:
        file_path: 文件完整路径

    Returns:
        str: 提取的关键词（去除扩展名和特殊字符），无法解析时返回空字符串
    """
    return _enhanced_extract_song_name(file_path)


def _build_smart_keyword(
    file_path: str,
    title: str,
    artist: str,
    mode: str = "smart_fallback",
) -> tuple[str, list[str]]:
    """
    智能构建搜索关键词（支持多种模式）

    根据用户选择的模式，从不同来源构建搜索关键词。
    智能回退模式下会返回多个备选关键词供依次尝试。
    自动过滤无效值（Unknown Album/Unknown Artist 等）

    Args:
        file_path: 音频文件完整路径
        title: Shazam识别的歌曲标题
        artist: Shazam识别的艺术家
        mode: 关键词构建模式
            - "title_only": 仅使用歌曲名
            - "artist_title": 使用"艺术家 歌曲名"组合
            - "filename_first": 优先使用文件名
            - "smart_fallback": 智能回退模式（推荐）

    Returns:
        tuple[str, list[str]]: (首选关键词, 备选关键词列表)
            首选关键词用于第一次搜索，如果无结果则尝试备选列表
    """
    import re

    # 无效值列表（这些值不应该出现在搜索关键词中）
    INVALID_VALUES = {
        'unknown_album', 'unknown_artist', 'unknown_title',
        'unknown', 'n/a', 'none'
    }

    def _clean_keyword(text: str) -> str:
        """清理关键词：移除无效后缀和无效值"""
        if not text:
            return ''

        text = text.strip()

        # 移除 " - Unknown_Album" / " - Unknown Artist" 等无效后缀
        # 使用简单可靠的模式，避免复杂正则表达式匹配失败
        # 支持 "Unknown_Album" (下划线) 和 "Unknown Album" (空格) 两种格式
        patterns = [
            r'\s+[-–—]\s+(Unknown[_\s]*(Album|Artist|Title)|N/A|None)\s*$',
            r'\s{2,}(Unknown[_\s]*(Album|Artist|Title)|N/A|None)\s*$',
            r'\s*:\s*(Unknown[_\s]*(Album|Artist|Title)|N/A|None)\s*$',
        ]

        for pattern in patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE).strip()

        # 如果清理后是无效值或太短，返回空字符串
        if text.lower() in INVALID_VALUES or len(text) < 2:
            return ''

        return text

    # 清理输入参数
    title = _clean_keyword(title)
    artist = _clean_keyword(artist)

    filename_base = os.path.splitext(os.path.basename(file_path))[0].strip()

    if mode == "title_only":
        return title, []

    elif mode == "artist_title":
        if artist and artist.lower() not in INVALID_VALUES:
            return f"{artist} {title}" if title else artist, []
        else:
            return title, []

    elif mode == "filename_first":
        filename_kw = _build_search_keyword_from_filename(file_path)
        if filename_kw:
            alternatives = [title]
            if artist and artist.lower() not in INVALID_VALUES and title:
                alternatives.append(f"{artist} {title}")
            return filename_kw, alternatives
        else:
            return title, []

    elif mode == "smart_fallback":
        keywords_to_try = []
        primary_keyword = title

        def _contains_non_ascii(s: str) -> bool:
            """检查字符串是否包含非ASCII字符（中文/日文/韩文等）"""
            return bool(re.search(r'[^\x00-\x7F]', s))

        def _is_meaningful_filename(name: str) -> bool:
            """检查文件名是否有意义（非纯数字、非无意义字符串）"""
            if not name or len(name) < 2:
                return False
            if re.match(r'^[\d\s_\-\.]+$', name):
                return False
            return True

        strategy_order = []

        if _is_meaningful_filename(filename_base) and _contains_non_ascii(filename_base):
            filename_keyword = _build_search_keyword_from_filename(file_path)

            logger.info(
                f"[SmartKeyword] Processing filename: '{filename_base}' -> '{filename_keyword}'"
            )

            # 新增：中英文分离智能处理
            from auto_tag.utils import split_multilingual_text, is_multilingual_text

            if filename_keyword and is_multilingual_text(filename_keyword):
                split_result = split_multilingual_text(filename_keyword)

                if split_result['has_both']:
                    native_part = split_result['native']
                    latin_part = split_result['latin']

                    logger.warning(
                        f"[SmartKeyword] ★★★ Detected multi-language text! ★★★"
                    )
                    logger.warning(
                        f"[SmartKeyword]   Original: '{filename_keyword}'"
                    )
                    logger.warning(
                        f"[SmartKeyword]   Native: '{native_part}' (will be PRIMARY keyword)"
                    )
                    logger.warning(
                        f"[SmartKeyword]   Latin:  '{latin_part}' (will be FALLBACK)"
                    )

                    # 优先使用 native 部分作为主要关键词
                    if native_part and len(native_part) >= 2:
                        strategy_order.append(("native_primary", native_part))

                    # latin 部分作为备选（用于回退）
                    if latin_part and len(latin_part) >= 2:
                        strategy_order.append(("latin_fallback", latin_part))

                    # 原始文件名作为最终回退
                    strategy_order.append(("filename_original", filename_keyword))
                else:
                    # 非混合情况，使用原始逻辑
                    strategy_order.append(("filename", filename_keyword))
            else:
                # 无混合，使用原始逻辑
                strategy_order.append(("filename", filename_keyword))
        elif _is_meaningful_filename(filename_base):
            strategy_order.append(("filename", _build_search_keyword_from_filename(file_path)))
        if title and title.lower() not in INVALID_VALUES:
            strategy_order.append(("title", title))
        if artist and artist.lower() not in INVALID_VALUES and title:
            strategy_order.append(("combined", f"{artist} {title}"))
        if title and title not in [s[1] for s in strategy_order]:
            strategy_order.append(("title_fallback", title))

        if strategy_order:
            primary_keyword = strategy_order[0][1]
            keywords_to_try = [s[1] for s in strategy_order[1:]]

            # 使用 WARNING 级别确保用户能看到关键信息
            logger.warning(
                f"[SmartKeyword] ★★★ FINAL SEARCH STRATEGY ★★★"
            )
            logger.warning(
                f"[SmartKeyword] File: '{os.path.basename(file_path)}'"
            )
            logger.warning(
                f"[SmartKeyword] PRIMARY keyword (will search first): '{primary_keyword}'"
            )
            if keywords_to_try:
                logger.warning(
                    f"[SmartKeyword] ALTERNATIVES (if primary fails): {keywords_to_try[:3]}"
                )
            else:
                logger.warning("[SmartKeyword] No alternatives (only primary will be used)")
            logger.warning(
                f"[SmartKeyword] Full strategy order: {[(name, kw[:30]+'...' if len(kw)>30 else kw) for name, kw in strategy_order]}"
            )
        else:
            primary_keyword = title

        return primary_keyword, keywords_to_try

    else:
        logger.warning(f"[SmartKeyword] Unknown mode '{mode}', falling back to title_only")
        return title, []
