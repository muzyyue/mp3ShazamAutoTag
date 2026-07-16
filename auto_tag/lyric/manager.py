# auto_tag/lyric/manager.py
"""
歌词管理器模块（Facade）

提供统一的 LyricManager 接口，将歌词获取、嵌入、提取和格式转换
功能委托给专门的子模块处理。
"""

from __future__ import annotations

import logging
import time
import os
from typing import Any, Callable

import eyed3
from mutagen import File
from mutagen.flac import Picture
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis
from urllib.error import HTTPError, URLError

from .provider import get_provider, get_provider_api
from .rate_limiter import get_rate_limiter, RequestMetrics
from auto_tag.audio_recognize._infra import get_netease_api, get_kugou_api

from .lyric_utils import (
    parse_lrc_duration,
    calculate_duration_match_ratio,
    extract_audio_metadata,
    build_search_keyword,
    parse_search_result,
    merge_lyrics_with_translation,
    calculate_match_score,
)
from .lyric_fetcher import LyricFetcher
from .lyric_embedder import LyricEmbedder
from .lyric_converter import LyricConverter

# Backward compatibility for tests that patch auto_tag.lyric.manager.converter
converter = None


class LyricManager:
    """
    歌词管理器类（Facade）

    封装歌词的获取、嵌入、提取和格式转换功能，
    将具体实现委托给 LyricFetcher、LyricEmbedder 和 LyricConverter。

    支持的音频格式：
    - MP3：使用 eyed3 处理 ID3 标签（USLT/SYLT 帧）
    - FLAC：使用 mutagen.flac.FLAC（LYRICS Vorbis Comment）
    - M4A：使用 mutagen.mp4.MP4（©lyr iTunes 原子）
    - OGG：使用 mutagen.oggvorbis.OggVorbis（LYRICS Vorbis Comment）
    - OPUS：使用 mutagen.oggopus.OggOpus（LYRICS Vorbis Comment）
    """

    def __init__(self):
        """初始化歌词管理器，配置日志和请求限速器"""
        self.logger = logging.getLogger(__name__)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

        # 初始化请求限速器（全局单例，控制 API 请求频率）
        self._rate_limiter = get_rate_limiter()

        # 初始化请求监控指标（记录成功率、响应时间等）
        self._metrics = RequestMetrics()

        # 初始化子模块委托
        self._fetcher = LyricFetcher(self.logger, self._rate_limiter, self._metrics)
        self._embedder = LyricEmbedder(self.logger)
        self._converter = LyricConverter(self.logger)

    # ──────────────── 公开方法：获取歌词 ────────────────

    def fetch_lyrics(
        self,
        file_path: str,
        provider: str = 'netease',
        lyric_mode: str = 'merged'
    ) -> dict[str, Any] | None:
        """从指定提供商获取歌词"""
        return self._fetcher.fetch_lyrics(file_path, provider, lyric_mode)

    def search_songs(
        self,
        file_path: str,
        provider: str = 'netease'
    ) -> list[dict[str, Any]]:
        """搜索歌曲（仅返回搜索结果列表，不获取歌词）"""
        return self._fetcher.search_songs(file_path, provider)

    def check_lyric_exists(
        self,
        song_id: int | str,
        provider: str = 'netease',
        timeout: int = 5
    ) -> bool:
        """轻量级检查歌曲是否有歌词"""
        return self._fetcher.check_lyric_exists(song_id, provider, timeout)

    def fetch_lyric_by_id(
        self,
        song_id: int | str,
        provider: str = 'netease',
        lyric_mode: str = 'merged'
    ) -> dict[str, Any] | None:
        """根据歌曲 ID 获取歌词"""
        return self._fetcher.fetch_lyric_by_id(song_id, provider, lyric_mode)

    def select_best_match(
        self,
        songs: list[dict[str, Any]],
        file_path: str,
        provider: str = 'netease'
    ) -> dict[str, Any] | None:
        """从搜索结果中自动选择最佳匹配的歌曲"""
        return self._fetcher.select_best_match(songs, file_path, provider)

    def batch_fetch_lyrics(
        self,
        file_paths: list[str],
        provider: str = 'lrclib'
    ) -> dict[str, dict[str, Any] | None]:
        """批量获取歌词"""
        return self._fetcher.batch_fetch_lyrics(file_paths, provider)

    # ──────────────── 公开方法：嵌入和提取歌词 ────────────────

    def embed_lyrics(
        self,
        file_path: str,
        lyrics: str,
        format: str = 'lrc',
        mode: str = 'embed_only'
    ) -> bool:
        """将歌词嵌入到音频文件"""
        return self._embedder.embed_lyrics(file_path, lyrics, format, mode)

    def extract_lyrics(self, file_path: str) -> dict[str, Any] | None:
        """从音频文件提取歌词"""
        return self._embedder.extract_lyrics(file_path)

    def batch_embed_lyrics(
        self,
        file_lyrics_pairs: list[tuple[str, str]],
        format: str = 'lrc',
        mode: str = 'embed_only'
    ) -> dict[str, bool]:
        """批量嵌入歌词"""
        return self._embedder.batch_embed_lyrics(file_lyrics_pairs, format, mode)

    # ──────────────── 公开方法：格式转换 ────────────────

    def convert_lyrics(
        self,
        lyrics: str,
        from_format: str,
        to_format: str
    ) -> str | None:
        """转换歌词格式"""
        return self._converter.convert_lyrics(lyrics, from_format, to_format)

    # ──────────────── 静态方法 ────────────────

    @staticmethod
    def parse_lrc_duration(lrc_text: str) -> float:
        """解析 LRC 歌词文本，提取总时长（秒）"""
        return parse_lrc_duration(lrc_text)

    @staticmethod
    def calculate_duration_match_ratio(
        song_duration: float,
        lyric_duration: float,
        threshold: float = 0.10
    ) -> dict[str, Any]:
        """计算歌曲时长与歌词时长的匹配度"""
        return calculate_duration_match_ratio(song_duration, lyric_duration, threshold)

    # ──────────────── 向后兼容的内部方法 ────────────────

    def _get_netease_api(self):
        """获取 NetEase API 实例（全局单例）"""
        return get_netease_api()

    def _get_kugou_api(self):
        """获取 KuGou API 实例（全局单例）"""
        return get_kugou_api()

    def _extract_audio_metadata(self, file_path: str) -> dict[str, Any] | None:
        """从音频文件提取元数据"""
        return extract_audio_metadata(file_path)

    def _build_search_keyword(self, title: str, artist: str) -> str:
        """构建搜索关键词"""
        return build_search_keyword(title, artist)

    def _parse_search_result(
        self,
        result: dict[str, Any],
        provider: str
    ) -> list[dict[str, Any]]:
        """解析搜索结果"""
        return parse_search_result(result, provider)

    def _merge_lyrics_with_translation(
        self,
        original_lrc: str,
        translation_lrc: str
    ) -> str:
        """合并原始歌词和翻译歌词"""
        return merge_lyrics_with_translation(original_lrc, translation_lrc)

    def _search_netease_rest_api(
        self,
        keyword: str,
        limit: int = 10
    ) -> list[dict[str, Any]]:
        """使用网易云 REST API 搜索歌曲"""
        return self._fetcher._search_netease_rest_api(keyword, limit)
