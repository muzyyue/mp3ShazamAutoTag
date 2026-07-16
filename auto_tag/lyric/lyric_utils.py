# -*- coding: utf-8 -*-
"""
歌词工具函数模块

提供纯函数工具，用于 LRC 解析、歌词合并、元数据提取、搜索关键词构建等。
所有函数均为模块级函数，不依赖类实例。
"""

from __future__ import annotations

import difflib
import logging
import os
import re
from typing import Any

import eyed3
from mutagen import File

logger = logging.getLogger(__name__)

# 无效值列表（用于构建搜索关键词）
INVALID_VALUES = {
    'unknown_album', 'unknown_artist', 'unknown_title',
    'unknown', 'n/a', '', 'none'
}


def parse_lrc_duration(lrc_text: str) -> float:
    """
    解析 LRC 歌词文本，提取总时长（秒）

    通过正则表达式匹配所有时间戳 [mm:ss.xx] 或 [mm:ss.xxx]，
    返回最大的时间值作为歌词总时长。

    Args:
        lrc_text (str): LRC 格式的歌词文本

    Returns:
        float: 歌词总时长（秒），无法解析时返回 0.0

    Example:
        >>> lrc = "[00:00.00]故事的小黄花\\n[04:29.65]从出生那年就飘着"
        >>> duration = parse_lrc_duration(lrc)
        >>> print(f"歌词总时长: {duration:.2f} 秒")
        歌词总时长: 269.65 秒
    """
    if not lrc_text or not isinstance(lrc_text, str):
        return 0.0

    # 匹配 LRC 时间戳格式：[mm:ss.xx] 或 [mm:ss.xxx]
    # 支持毫秒精度为 2 位或 3 位
    pattern = r'\[(\d{1,2}):(\d{2})\.(\d{2,3})\]'
    matches = re.findall(pattern, lrc_text)

    if not matches:
        return 0.0

    max_duration = 0.0
    for minutes, seconds, milliseconds in matches:
        try:
            # 转换为秒
            total_seconds = (
                int(minutes) * 60 +
                int(seconds) +
                int(milliseconds.ljust(3, '0')[:3]) / 1000.0  # 统一为 3 位毫秒
            )
            if total_seconds > max_duration:
                max_duration = total_seconds
        except (ValueError, IndexError):
            continue

    return round(max_duration, 2)


def calculate_duration_match_ratio(
    song_duration: float,
    lyric_duration: float,
    threshold: float = 0.10
) -> dict[str, Any]:
    """
    计算歌曲时长与歌词时长的匹配度

    对比音频文件实际时长和歌词总时长，
    计算差异百分比并判断是否在可接受范围内。

    Args:
        song_duration (float): 歌曲实际时长（秒）
        lyric_duration (float): 歌词总时长（秒）
        threshold (float): 允许的差异阈值（默认 10%）

    Returns:
        dict: 匹配结果字典，包含：
            - song_duration: 歌曲时长（格式化字符串）
            - lyric_duration: 歌词时长（格式化字符串）
            - difference: 差异（秒）
            - ratio: 差异百分比
            - is_match: 是否匹配（布尔值）
            - match_level: 匹配等级 ('excellent' | 'good' | 'warning' | 'mismatch')
            - message: 提示消息

    Example:
        >>> result = calculate_duration_match_ratio(269, 265)
        >>> print(result['match_level'])
        excellent
    """
    if song_duration <= 0 or lyric_duration <= 0:
        return {
            'song_duration': '--:--',
            'lyric_duration': '--:--',
            'difference': 0,
            'ratio': 0,
            'is_match': False,
            'match_level': 'unknown',
            'message': tr('duration_unknown') if 'tr' in dir() else '时长信息未知'
        }

    # 计算差异
    difference = abs(song_duration - lyric_duration)
    ratio = difference / song_duration if song_duration > 0 else 1.0

    # 格式化时长显示
    def format_duration(seconds: float) -> str:
        if seconds <= 0:
            return '--:--'
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins:02d}:{secs:02d}"

    # 判断匹配等级
    if ratio <= 0.03:  # 差异 ≤ 3%
        match_level = 'excellent'
        is_match = True
        message = tr('duration_excellent_match') if 'tr' in dir() else '时长完美匹配'
    elif ratio <= 0.07:  # 差异 ≤ 7%
        match_level = 'good'
        is_match = True
        message = tr('duration_good_match') if 'tr' in dir() else '时长基本匹配'
    elif ratio <= threshold:  # 差异 ≤ 阈值（默认 10%）
        match_level = 'warning'
        is_match = True
        message = tr('duration_warning') if 'tr' in dir() else f'时长差异 {ratio*100:.1f}%，请确认'
    else:  # 差异 > 阈值
        match_level = 'mismatch'
        is_match = False
        message = tr('duration_mismatch') if 'tr' in dir() else f'时长差异过大 ({ratio*100:.1f}%)，可能不匹配'

    return {
        'song_duration': format_duration(song_duration),
        'lyric_duration': format_duration(lyric_duration),
        'difference': round(difference, 2),
        'ratio': round(ratio * 100, 2),
        'is_match': is_match,
        'match_level': match_level,
        'message': message
    }


def parse_lrc_to_list(lrc_content: str) -> list[tuple[str, str]]:
    """
    解析LRC歌词为列表格式

    Args:
        lrc_content: LRC格式歌词内容

    Returns:
        list[tuple[str, str]]: [(时间戳字符串, 歌词文本), ...]

    Example:
        >>> lrc = "[00:00.00]第一行\\n[00:05.00]第二行"
        >>> result = parse_lrc_to_list(lrc)
        >>> print(result)
        [('00:00.00', '第一行'), ('00:05.00', '第二行')]
    """
    lines = []
    # LRC格式：[mm:ss.xx]歌词文本 或 [mm:ss.xxx]歌词文本
    pattern = r'\[(\d{2}:\d{2}\.\d{2,3})\](.*)'

    for line in lrc_content.split('\n'):
        match = re.match(pattern, line.strip())
        if match:
            timestamp = match.group(1)
            text = match.group(2).strip()
            # 只添加非空歌词行
            if text:
                lines.append((timestamp, text))

    return lines


def parse_lrc_to_dict(lrc_content: str) -> dict[str, str]:
    """
    解析LRC歌词为字典格式

    Args:
        lrc_content: LRC格式歌词内容

    Returns:
        dict[str, str]: {时间戳字符串: 歌词文本}

    Example:
        >>> lrc = "[00:00.00]第一行\\n[00:05.00]第二行"
        >>> result = parse_lrc_to_dict(lrc)
        >>> print(result)
        {'00:00.00': '第一行', '00:05.00': '第二行'}
    """
    lrc_dict = {}
    # LRC格式：[mm:ss.xx]歌词文本 或 [mm:ss.xxx]歌词文本
    pattern = r'\[(\d{2}:\d{2}\.\d{2,3})\](.*)'

    for line in lrc_content.split('\n'):
        match = re.match(pattern, line.strip())
        if match:
            timestamp = match.group(1)
            text = match.group(2).strip()
            # 只添加非空歌词行
            if text:
                lrc_dict[timestamp] = text

    return lrc_dict


def merge_lyrics_with_translation(
    original_lrc: str,
    translation_lrc: str
) -> str:
    """
    合并原始歌词和翻译歌词（一句原始+一句翻译交替排列）

    Args:
        original_lrc: 原始歌词（LRC格式）
        translation_lrc: 翻译歌词（LRC格式）

    Returns:
        str: 合并后的歌词（LRC格式）

    Example:
        >>> original = "[00:00.00]故事的小黄花\\n[00:05.00]从出生那年就飘着"
        >>> translation = "[00:00.00]The small yellow flower\\n[00:05.00]Has been floating since birth"
        >>> merged = merge_lyrics_with_translation(original, translation)
        >>> print(merged)
        [00:00.00]故事的小黄花
        [00:00.00]The small yellow flower
        [00:05.00]从出生那年就飘着
        [00:05.00]Has been floating since birth
    """
    # 如果没有翻译歌词，直接返回原始歌词
    if not translation_lrc or not translation_lrc.strip():
        return original_lrc

    # 如果没有原始歌词，返回空字符串
    if not original_lrc or not original_lrc.strip():
        return ''

    # 解析原始歌词为列表 [(时间戳字符串, 歌词文本), ...]
    original_lines = parse_lrc_to_list(original_lrc)

    # 解析翻译歌词为字典 {时间戳字符串: 歌词文本}
    translation_dict = parse_lrc_to_dict(translation_lrc)

    # 合并歌词
    merged_lines = []
    for timestamp, text in original_lines:
        # 添加原始歌词行
        merged_lines.append(f"[{timestamp}]{text}")

        # 查找对应时间戳的翻译
        if timestamp in translation_dict and translation_dict[timestamp]:
            # 添加翻译歌词行（使用相同的时间戳）
            merged_lines.append(f"[{timestamp}]{translation_dict[timestamp]}")

    return '\n'.join(merged_lines)


def extract_audio_metadata(file_path: str) -> dict[str, Any] | None:
    """
    从音频文件提取元数据

    Args:
        file_path: 音频文件路径

    Returns:
        dict | None: 元数据字典，包含 title, artist, album, duration
    """
    ext = os.path.splitext(file_path)[1].lower()

    try:
        if ext == '.mp3':
            audio = eyed3.load(file_path)
            if audio and audio.tag:
                return {
                    'title': audio.tag.title or '',
                    'artist': audio.tag.artist or '',
                    'album': audio.tag.album or '',
                    'duration': int(audio.info.time_secs) if audio.info else 0
                }
        else:
            audio = File(file_path)
            if audio:
                return {
                    'title': audio.get('title', [''])[0],
                    'artist': audio.get('artist', [''])[0],
                    'album': audio.get('album', [''])[0],
                    'duration': int(audio.info.length) if audio.info else 0
                }
    except Exception as e:
        logger.error(f"提取元数据失败: {file_path}, 错误: {e}")

    return None


def clean_text(text: str) -> str:
    """清理文本：过滤无效值和无意义后缀"""
    if not text:
        return ''

    text = text.strip()

    # 检查是否是无效值
    if text.lower() in INVALID_VALUES:
        return ''

    # 移除各种格式的无效后缀（使用简单可靠的模式）
    # 支持格式：
    #   "Song Name - Unknown_Album" (下划线)
    #   "Song Name - Unknown Album" (空格)
    #   "Song Name  Unknown_Album" (多空格)
    #   "Song Name : N/A"
    patterns = [
        r'\s+[-–—]\s+(Unknown[_\s]*(Album|Artist|Title)|N/A|None)\s*$',
        r'\s{2,}(Unknown[_\s]*(Album|Artist|Title)|N/A|None)\s*$',
        r'\s*:\s*(Unknown[_\s]*(Album|Artist|Title)|N/A|None)\s*$',
    ]

    for pattern in patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE).strip()

    # 只清理明显的版本后缀，保留核心歌名
    text = re.sub(
        r'\s*[\-–—]\s*(Movie|Piano|Short|Full)\s*Ver\.?\s*$'
        r'|\s*[\(\[]\s*(Live|Acoustic|Remix|Cover|Inst\.?|Instrumental)\s*[\)\]]\s*$',
        '',
        text,
        flags=re.IGNORECASE
    ).strip()

    return text

    # 再次检查清理后是否变成空或无效值
    if text.lower() in INVALID_VALUES or len(text) < 2:
        return ''

    return text


def build_search_keyword(title: str, artist: str) -> str:
    """
    构建搜索关键词

    策略：优先使用完整标题（不过度清理），REST API 本身支持模糊匹配
    如果标题为空或太短，则组合艺术家和标题
    自动过滤无效值（Unknown Album/Unknown Artist 等）

    Args:
        title (str): 歌曲标题
        artist (str): 艺术家名称

    Returns:
        str: 构建好的搜索关键词
    """
    # 清理标题和艺术家
    clean_title = clean_text(title)
    clean_artist = clean_text(artist)

    # 优先使用完整标题（REST API 支持模糊匹配，不需要过度清理）
    if clean_title:
        return clean_title
    elif clean_artist:
        return clean_artist
    else:
        # 最后尝试：如果原始 title 包含 ' - '，取第一部分
        if ' - ' in title:
            parts = title.split(' - ', 1)
            first_part = clean_text(parts[0])
            if first_part and len(first_part) >= 2:
                return first_part

        return ''


def calculate_match_score(
    song: dict[str, Any],
    file_title: str,
    file_artist: str,
    file_duration: float
) -> float:
    """
    计算单个搜索结果与音频文件的匹配度分数

    使用加权评分算法：
    - 歌名相似度（权重 40%）：基于字符串包含关系和编辑距离
    - 艺术家匹配度（权重 35%）：基于完全匹配或包含关系
    - 时长接近度（权重 25%）：基于时长差异百分比

    Args:
        song: 搜索结果歌曲字典
        file_title: 音频文件标题（小写）
        file_artist: 音频文件艺术家（小写）
        file_duration: 音频文件时长（秒）

    Returns:
        float: 匹配度分数（0-100）
    """
    song_name = song.get('name', '').strip().lower()
    song_artist = song.get('artist', '').strip().lower()
    song_duration = song.get('duration', 0)

    # === 1. 歌名相似度评分 (0-40分) ===
    name_score = 0.0
    if file_title and song_name:
        if file_title == song_name:
            name_score = 40.0
        elif file_title in song_name or song_name in file_title:
            name_score = 35.0
        else:
            similarity = difflib.SequenceMatcher(None, file_title, song_name).ratio()
            name_score = similarity * 30

    # === 2. 艺术家匹配度评分 (0-35分) ===
    artist_score = 0.0
    if file_artist and song_artist:
        if file_artist == song_artist:
            artist_score = 35.0
        elif file_artist in song_artist or song_artist in file_artist:
            artist_score = 28.0
        else:
            similarity = difflib.SequenceMatcher(None, file_artist, song_artist).ratio()
            artist_score = similarity * 20

    # 如果文件没有艺术家信息，不扣分
    if not file_artist:
        artist_score = 25.0

    # === 3. 时长接近度评分 (0-25分) ===
    duration_score = 0.0
    if file_duration > 0 and song_duration > 0:
        duration_diff = abs(file_duration - song_duration)
        diff_ratio = duration_diff / file_duration

        if diff_ratio <= 0.03:
            duration_score = 25.0
        elif diff_ratio <= 0.07:
            duration_score = 20.0
        elif diff_ratio <= 0.10:
            duration_score = 15.0
        elif diff_ratio <= 0.20:
            duration_score = 10.0
        else:
            duration_score = max(0, 5.0 - diff_ratio * 10)
    else:
        duration_score = 15.0

    total_score = name_score + artist_score + duration_score

    return round(total_score, 2)


def parse_search_result(
    result: dict[str, Any],
    provider: str
) -> list[dict[str, Any]]:
    """
    解析搜索结果

    Args:
        result: API 返回的搜索结果
        provider: 提供商名称

    Returns:
        list[dict]: 标准化的歌曲列表
    """
    songs = []

    try:
        if provider == 'netease':
            # 网易云音乐搜索结果格式
            result_data = result.get('result', {})
            song_list = result_data.get('songs', [])

            for song in song_list:
                songs.append({
                    'id': song.get('id'),
                    'name': song.get('name', ''),
                    'artist': song.get('artists', [{}])[0].get('name', '') if song.get('artists') else '',
                    'album': song.get('album', {}).get('name', ''),
                    'duration': song.get('duration', 0) // 1000  # 转换为秒
                })
        else:
            # 酷狗音乐搜索结果格式
            # 格式: {"data": {"lists": [...]}}
            data = result.get('data', {})
            song_list = data.get('lists', [])

            for song in song_list:
                songs.append({
                    'id': song.get('Hash') or song.get('hash'),
                    'name': song.get('SongName') or song.get('songname', ''),
                    'artist': song.get('SingerName') or song.get('singername', ''),
                    'album': song.get('AlbumName') or song.get('album_name', ''),
                    'duration': song.get('Duration', song.get('duration', 0))
                })

    except Exception as e:
        logger.error(f"解析搜索结果失败: {e}")

    return songs
