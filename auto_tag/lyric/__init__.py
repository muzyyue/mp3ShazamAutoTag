# auto_tag/lyric/__init__.py
"""
歌词处理模块
提供歌词的获取、嵌入、提取和格式转换功能
"""

from .manager import LyricManager
from .provider import (
    LyricProvider,
    PROVIDERS,
    get_provider,
    get_provider_api,
    list_providers
)
from .lyric_fetcher import LyricFetcher
from .lyric_embedder import LyricEmbedder
from .lyric_converter import LyricConverter
from .lyric_utils import parse_lrc_duration, calculate_duration_match_ratio

__all__ = [
    'LyricManager',
    'LyricFetcher',
    'LyricEmbedder',
    'LyricConverter',
    'LyricProvider',
    'PROVIDERS',
    'get_provider',
    'get_provider_api',
    'list_providers',
    'parse_lrc_duration',
    'calculate_duration_match_ratio',
]
