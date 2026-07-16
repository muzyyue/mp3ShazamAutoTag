# -*- coding: utf-8 -*-
"""
歌词格式转换模块

提供 LyricConverter 类，负责在不同歌词格式之间进行转换，
支持 LRC、TTML、SRT、JSON 四种格式。
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class LyricConverter:
    """
    歌词格式转换类

    支持四种歌词格式互转：
    - LRC：标准 LRC 同步歌词格式
    - TTML：基于 XML 的字幕格式
    - SRT：SubRip 字幕格式
    - JSON：结构化歌词数据格式
    """

    def __init__(self, logger):
        """
        初始化歌词转换器

        Args:
            logger: 日志记录器实例
        """
        self.logger = logger

    def convert_lyrics(
        self,
        lyrics: str,
        from_format: str,
        to_format: str
    ) -> str | None:
        """
        转换歌词格式

        Args:
            lyrics: 歌词内容
            from_format: 源格式（'lrc', 'ttml', 'srt', 'json'）
            to_format: 目标格式（'lrc', 'ttml', 'srt', 'json'）

        Returns:
            str | None: 转换后的歌词内容，失败返回 None

        Raises:
            ValueError: 不支持的格式

        Example:
            >>> converter = LyricConverter(logger)
            >>> lrc_lyrics = "[00:00.00]第一行歌词"
            >>> json_lyrics = converter.convert_lyrics(lrc_lyrics, 'lrc', 'json')
        """
        supported_formats = ['lrc', 'ttml', 'srt', 'json']

        if from_format.lower() not in supported_formats:
            raise ValueError(
                f"不支持的源格式: {from_format}, 支持的格式: {supported_formats}"
            )

        if to_format.lower() not in supported_formats:
            raise ValueError(
                f"不支持的目标格式: {to_format}, 支持的格式: {supported_formats}"
            )

        if from_format.lower() == to_format.lower():
            return lyrics

        try:
            # 使用本地转换器
            return self._convert_lyrics_local(lyrics, from_format, to_format)
        except Exception as e:
            self.logger.error(
                f"转换歌词格式失败: {from_format} -> {to_format}, 错误: {e}"
            )
            return None

    def _convert_lyrics_local(
        self,
        lyrics: str,
        from_format: str,
        to_format: str
    ) -> str:
        """
        本地歌词格式转换

        Args:
            lyrics: 歌词内容
            from_format: 源格式
            to_format: 目标格式

        Returns:
            str: 转换后的歌词内容
        """
        # 先解析为统一格式
        parsed_data = self._parse_lyrics(lyrics, from_format)

        # 再生成目标格式
        return self._generate_lyrics(parsed_data, to_format)

    def _parse_lyrics(self, lyrics: str, format: str) -> list[dict]:
        """
        解析歌词为统一格式

        Args:
            lyrics: 歌词内容
            format: 歌词格式

        Returns:
            list[dict]: 解析后的歌词数据，格式为：
                [{'time': 毫秒, 'text': '歌词文本'}, ...]
        """
        import re

        parsed = []

        if format == 'lrc':
            # 解析 LRC 格式
            # 格式: [mm:ss.xx]歌词文本
            pattern = r'\[(\d{2}):(\d{2})\.(\d{2,3})\](.*)'
            for line in lyrics.split('\n'):
                match = re.match(pattern, line.strip())
                if match:
                    minutes = int(match.group(1))
                    seconds = int(match.group(2))
                    milliseconds = int(match.group(3).ljust(3, '0'))
                    time_ms = (minutes * 60 + seconds) * 1000 + milliseconds
                    text = match.group(4).strip()
                    if text:
                        parsed.append({'time': time_ms, 'text': text})

        elif format == 'json':
            # 解析 JSON 格式
            try:
                data = json.loads(lyrics)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and 'time' in item and 'text' in item:
                            parsed.append({
                                'time': item['time'],
                                'text': item['text']
                            })
            except json.JSONDecodeError:
                pass

        elif format == 'srt':
            # 解析 SRT 格式
            # 格式:
            # 序号
            # 00:00:00,000 --> 00:00:05,000
            # 歌词文本
            lines = lyrics.split('\n')
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                # 查找时间轴
                if '-->' in line:
                    time_match = re.match(
                        r'(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})',
                        line
                    )
                    if time_match:
                        hours = int(time_match.group(1))
                        minutes = int(time_match.group(2))
                        seconds = int(time_match.group(3))
                        milliseconds = int(time_match.group(4))
                        time_ms = (hours * 3600 + minutes * 60 + seconds) * 1000 + milliseconds

                        # 下一行是歌词文本
                        i += 1
                        if i < len(lines):
                            text = lines[i].strip()
                            if text:
                                parsed.append({'time': time_ms, 'text': text})
                i += 1

        elif format == 'ttml':
            # 解析 TTML 格式（简化版）
            # 格式: <p begin="00:00:00.000" end="00:00:05.000">歌词文本</p>
            pattern = r'<p\s+begin="([^"]+)"[^>]*>([^<]+)</p>'
            for match in re.finditer(pattern, lyrics):
                time_str = match.group(1)
                text = match.group(2).strip()

                # 解析时间
                time_parts = time_str.split(':')
                if len(time_parts) == 3:
                    hours, minutes, seconds = time_parts
                    seconds_parts = seconds.split('.')
                    secs = int(seconds_parts[0])
                    ms = int(seconds_parts[1].ljust(3, '0')) if len(seconds_parts) > 1 else 0
                    time_ms = (int(hours) * 3600 + int(minutes) * 60 + secs) * 1000 + ms

                    if text:
                        parsed.append({'time': time_ms, 'text': text})

        return parsed

    def _generate_lyrics(self, data: list[dict], format: str) -> str:
        """
        从统一格式生成歌词

        Args:
            data: 歌词数据
            format: 目标格式

        Returns:
            str: 生成的歌词内容
        """
        if format == 'lrc':
            # 生成 LRC 格式
            lines = []
            for item in data:
                time_ms = item['time']
                text = item['text']

                minutes = time_ms // 60000
                seconds = (time_ms % 60000) // 1000
                milliseconds = time_ms % 1000

                lines.append(f"[{minutes:02d}:{seconds:02d}.{milliseconds:03d}]{text}")

            return '\n'.join(lines)

        elif format == 'json':
            # 生成 JSON 格式
            return json.dumps(data, ensure_ascii=False, indent=2)

        elif format == 'srt':
            # 生成 SRT 格式
            lines = []
            for i, item in enumerate(data, 1):
                time_ms = item['time']
                text = item['text']

                hours = time_ms // 3600000
                minutes = (time_ms % 3600000) // 60000
                seconds = (time_ms % 60000) // 1000
                milliseconds = time_ms % 1000

                # SRT 时间格式: 00:00:00,000 --> 00:00:05,000
                start_time = f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
                # 假设每行歌词持续5秒
                end_ms = time_ms + 5000
                end_hours = end_ms // 3600000
                end_minutes = (end_ms % 3600000) // 60000
                end_seconds = (end_ms % 60000) // 1000
                end_milliseconds = end_ms % 1000
                end_time = f"{end_hours:02d}:{end_minutes:02d}:{end_seconds:02d},{end_milliseconds:03d}"

                lines.append(str(i))
                lines.append(f"{start_time} --> {end_time}")
                lines.append(text)
                lines.append('')

            return '\n'.join(lines)

        elif format == 'ttml':
            # 生成 TTML 格式
            lines = ['<?xml version="1.0" encoding="UTF-8"?>']
            lines.append('<tt xmlns="http://www.w3.org/ns/ttml" xml:lang="zh">')
            lines.append('  <body>')
            lines.append('    <div>')

            for item in data:
                time_ms = item['time']
                text = item['text']

                hours = time_ms // 3600000
                minutes = (time_ms % 3600000) // 60000
                seconds = (time_ms % 60000) // 1000
                milliseconds = time_ms % 1000

                begin_time = f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"

                lines.append(f'      <p begin="{begin_time}">{text}</p>')

            lines.append('    </div>')
            lines.append('  </body>')
            lines.append('</tt>')

            return '\n'.join(lines)

        return ''
