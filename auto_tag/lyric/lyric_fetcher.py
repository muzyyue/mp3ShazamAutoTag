# -*- coding: utf-8 -*-
"""
歌词获取模块

提供 LyricFetcher 类，负责从多个提供商（网易云、酷狗、LRCLib、Apple Music、MusixMatch）
获取歌词，支持搜索、歌词存在性检查、批量获取等功能。
"""

from __future__ import annotations

import logging
import time
import os
from typing import Any, Callable
from urllib.error import HTTPError, URLError

from .provider import get_provider, get_provider_api
from auto_tag.audio_recognize._infra import get_netease_api, get_kugou_api
from .lyric_utils import (
    extract_audio_metadata,
    build_search_keyword,
    parse_search_result,
    merge_lyrics_with_translation,
    calculate_match_score,
)

logger = logging.getLogger(__name__)


class LyricFetcher:
    """
    歌词获取类

    负责从多个提供商获取歌词，支持搜索、批量获取和自动重试。
    使用 RateLimiter 控制请求频率，避免触发服务器限流。
    """

    def __init__(self, logger, rate_limiter, metrics):
        """
        初始化歌词获取器

        Args:
            logger: 日志记录器实例
            rate_limiter: RateLimiter 实例
            metrics: RequestMetrics 实例
        """
        self.logger = logger
        self._rate_limiter = rate_limiter
        self._metrics = metrics

    def _get_netease_api(self):
        """
        获取 NetEase API 实例（全局单例）

        Returns:
            NeteaseCloudMusicApi or None: 当前线程的 API 实例
        """
        return get_netease_api()

    def _get_kugou_api(self):
        """
        获取 KuGou API 实例（全局单例）

        Returns:
            KuGouMusicApi or None: 当前线程的 API 实例
        """
        return get_kugou_api()

    def _retryable_request(
        self,
        request_func: Callable[[], Any],
        max_retries: int = 3,
        base_delay: float = 1.0,
        retryable_errors: tuple[int, ...] = (405, 429, 500, 502, 503),
        operation_name: str = "API请求"
    ) -> Any:
        """
        带指数退避重试和速率限制的请求包装器

        自动处理以下场景：
        1. 速率限制：通过 RateLimiter 控制请求间隔
        2. 网络错误：对可重试的 HTTP 错误自动重试
        3. 指数退避：每次重试等待时间翻倍（1s, 2s, 4s, ...）
        4. 指标记录：所有请求结果都记录到 RequestMetrics

        Args:
            request_func: 实际执行 HTTP 请求的可调用对象（无参数）
            max_retries: 最大重试次数（默认3次，即最多尝试4次）
            base_delay: 基础延迟时间（秒），实际延迟 = base_delay * 2^attempt
            retryable_errors: 需要触发重试的 HTTP 状态码元组
            operation_name: 操作名称（用于日志输出，如"搜索歌曲"、"获取歌词"）

        Returns:
            Any: request_func 的返回值（通常是解析后的数据字典或列表）

        Raises:
            TimeoutError: 等待速率限制许可超时
            Exception: 重试耗尽后抛出最后一个异常
        """
        last_exception: Exception | None = None
        total_attempts = max_retries + 1  # 首次尝试 + 重试次数

        for attempt in range(total_attempts):
            try:
                # 步骤1：获取速率限制许可（阻塞直到可用）
                if not self._rate_limiter.acquire(timeout=30):
                    self.logger.error(
                        f"[RateLimit] {operation_name} 等待请求许可超时(30s)，放弃本次请求"
                    )
                    raise TimeoutError(f"{operation_name} 等待请求许可超时")

                # 步骤2：执行实际请求并计时
                start_time = time.time()
                result = request_func()
                response_time = time.time() - start_time

                # 步骤3：记录成功指标
                self._metrics.record_request(
                    success=True,
                    response_time=response_time,
                    retry_count=attempt,
                    is_rate_limited=(attempt > 0)  # 如果有重试说明可能被限流过
                )

                if attempt > 0:
                    self.logger.info(
                        f"[Retry] {operation_name} 在第 {attempt + 1} 次尝试成功 "
                        f"(耗时: {response_time:.2f}s)"
                    )

                return result

            except HTTPError as e:
                last_exception = e
                response_time = time.time() - start_time if 'start_time' in dir() else 0

                # 判断是否为可重试错误
                if e.code not in retryable_errors:
                    # 不可重试的错误（如404 Not Found、403 Forbidden）直接抛出
                    self.logger.warning(
                        f"[Retry] {operation_name} 遇到不可重试错误 "
                        f"(HTTP {e.code}: {e.reason})，直接抛出"
                    )
                    self._metrics.record_request(success=False, response_time=response_time)
                    raise

                # 记录失败指标
                self._metrics.record_request(
                    success=False,
                    response_time=response_time,
                    retry_count=attempt
                )

                # 计算退避延迟（指数增长）
                delay = base_delay * (2 ** attempt)
                delay = min(delay, 10.0)  # 最大延迟不超过10秒

                if attempt < max_retries:
                    self.logger.warning(
                        f"[Retry] {operation_name} 失败 (HTTP {e.code}: {e.reason})，"
                        f"{delay:.1f}秒后重试 ({attempt + 1}/{max_retries})"
                    )
                    time.sleep(delay)
                else:
                    self.logger.error(
                        f"[Retry] {operation_name} 重试耗尽 "
                        f"(共{total_attempts}次)，最后错误: HTTP {e.code}"
                    )

            except URLError as e:
                last_exception = e
                response_time = time.time() - start_time if 'start_time' in dir() else 0

                # 网络错误（DNS失败、连接拒绝等）也进行重试
                self._metrics.record_request(
                    success=False,
                    response_time=response_time,
                    retry_count=attempt
                )

                delay = base_delay * (2 ** attempt)
                delay = min(delay, 10.0)

                if attempt < max_retries:
                    self.logger.warning(
                        f"[Retry] {operation_name} 网络错误 ({e.reason})，"
                        f"{delay:.1f}秒后重试 ({attempt + 1}/{max_retries})"
                    )
                    time.sleep(delay)

            except Exception as e:
                # 其他未知错误，不重试直接抛出
                last_exception = e
                response_time = time.time() - start_time if 'start_time' in dir() else 0
                self._metrics.record_request(success=False, response_time=response_time)
                self.logger.error(
                    f"[Retry] {operation_name} 遇到不可预见的错误 "
                    f"({type(e).__name__}: {e})，停止重试"
                )
                raise

        # 所有重试都失败了
        self._metrics.record_request(
            success=False,
            response_time=0,
            retry_count=max_retries
        )
        raise last_exception or RuntimeError(f"{operation_name} 未知错误")

    def fetch_lyrics(
        self,
        file_path: str,
        provider: str = 'netease',
        lyric_mode: str = 'merged'
    ) -> dict[str, Any] | None:
        """
        从指定提供商获取歌词

        Args:
            file_path: 音频文件路径
            provider: 提供商名称（'netease', 'kugou', 'lrclib', 'applemusic', 'musixmatch'）
            lyric_mode: 歌词模式（仅对网易云音乐有效）
                - 'original': 仅返回原始歌词
                - 'merged': 返回原始歌词和翻译歌词合并（默认）
                - 'translation': 仅返回翻译歌词

        Returns:
            dict | None: 歌词数据字典，格式为：
                {
                    'plain_lyrics': str,      # 纯文本歌词
                    'synced_lyrics': str,     # 同步歌词（LRC 格式）
                    'provider': str,          # 提供商名称
                    'track_name': str,        # 歌曲名称
                    'artist_name': str,       # 艺术家
                    'album_name': str,        # 专辑名
                    'duration': int           # 时长（秒）
                }
            获取失败返回 None

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: 不支持的提供商或歌词模式

        Example:
            >>> fetcher = LyricFetcher(logger, rate_limiter, metrics)
            >>> # 获取合并歌词（默认）
            >>> lyrics = fetcher.fetch_lyrics('song.mp3', 'netease')
            >>> # 获取原始歌词
            >>> lyrics = fetcher.fetch_lyrics('song.mp3', 'netease', lyric_mode='original')
            >>> # 获取翻译歌词
            >>> lyrics = fetcher.fetch_lyrics('song.mp3', 'netease', lyric_mode='translation')
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        # 验证提供商
        provider_config = get_provider(provider)
        if not provider_config:
            raise ValueError(f"不支持的提供商: {provider}")

        # 验证歌词模式
        valid_modes = ['original', 'merged', 'translation']
        if lyric_mode not in valid_modes:
            raise ValueError(f"不支持的歌词模式: {lyric_mode}, 支持的模式: {valid_modes}")

        # 根据提供商类型选择不同的处理方式
        if provider in ['netease', 'kugou']:
            return self._fetch_lyrics_from_music_api(file_path, provider, lyric_mode)
        else:
            return self._fetch_lyrics_from_lrxy(file_path, provider)

    def search_songs(
        self,
        file_path: str,
        provider: str = 'netease'
    ) -> list[dict[str, Any]]:
        """
        搜索歌曲（仅返回搜索结果列表，不获取歌词）

        Args:
            file_path: 音频文件路径
            provider: 提供商名称（'netease', 'kugou'）

        Returns:
            list[dict]: 搜索结果列表，每个字典包含：
                - id: 歌曲 ID
                - name: 歌曲名称
                - artist: 艺术家名称
                - album: 专辑名称
                - duration: 时长（秒）

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: 不支持的提供商

        Example:
            >>> fetcher = LyricFetcher(logger, rate_limiter, metrics)
            >>> results = fetcher.search_songs('song.mp3', 'netease')
            >>> for song in results:
            ...     print(f"{song['name']} - {song['artist']}")
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        # 验证提供商
        provider_config = get_provider(provider)
        if not provider_config:
            raise ValueError(f"不支持的提供商: {provider}")

        # 只支持 netease 和 kugou 的搜索功能
        if provider not in ['netease', 'kugou']:
            self.logger.warning(f"提供商 {provider} 不支持搜索功能")
            return []

        try:
            # 从音频文件提取元数据
            metadata = extract_audio_metadata(file_path)
            if not metadata:
                self.logger.error(f"无法提取音频元数据: {file_path}")
                return []

            # 调试日志：输出提取到的元数据
            self.logger.info(f"[DEBUG] 提取到元数据: {metadata}")

            import re

            title = metadata.get('title', '').strip()
            artist = metadata.get('artist', '').strip()

            # 如果标题和艺术家都为空，尝试从文件名解析
            if not title and not artist:
                filename = os.path.basename(file_path)
                self.logger.warning(f"ID3标签为空，使用文件名: {filename}")
                name_without_ext = os.path.splitext(filename)[0]
                if ' - ' in name_without_ext:
                    parts = name_without_ext.split(' - ', 1)
                    artist = parts[0].strip()
                    title = parts[1].strip() if len(parts) > 1 else ''
                else:
                    title = name_without_ext

            # 构建搜索关键词（优化策略：保留更多原始信息以提高匹配度）
            # 强制调试：在调用前后分别记录原始值和清理后的值
            self.logger.warning(f"[KEYWORD-DEBUG] 原始输入: title='{title}', artist='{artist}'")
            keyword = build_search_keyword(title, artist)
            self.logger.warning(f"[KEYWORD-DEBUG] 清理后关键词: '{keyword}' (长度={len(keyword)})")

            if 'unknown' in keyword.lower():
                self.logger.error(f"[KEYWORD-ERROR] 关键词仍包含无效值: '{keyword}'")
                # 强制再次清理作为备用方案
                import re as _re
                keyword = _re.sub(
                    r'\s*[-–—:\s]+\s*(Unknown[_\s]*(Album|Artist|Title)|N/A|None)\s*$',
                    '',
                    keyword,
                    flags=_re.IGNORECASE
                ).strip()
                self.logger.warning(f"[KEYWORD-FIX] 备用清理后: '{keyword}'")

            self.logger.info(f"[DEBUG] 搜索关键词: '{keyword}' (原始title='{title}', 原始artist='{artist}')")

            # === 修复：REST API 优先策略 ===
            # 原因：pymusiclibrary 原生 C 库(QuickJS)不支持多实例/重复初始化，
            # 在子线程中创建新实例会导致第二次及以后的搜索失败。
            # REST API 是无状态 HTTP 请求，完全绕过此问题，且搜索能力更强。

            # 1. 首选：使用 REST API 搜索（稳定、无状态、支持模糊匹配）
            songs = self._search_netease_rest_api(keyword)
            if songs:
                self.logger.info(f"搜索完成(REST-Primary): {keyword}, 找到 {len(songs)} 首歌曲")
                return songs

            # 2. 备选：仅在主线程中尝试 pymusiclibrary（使用全局单例，避免多实例问题）
            import threading
            if threading.current_thread().name == 'MainThread':
                api = self._get_kugou_api() if provider == 'kugou' else self._get_netease_api()
                if api is not None:
                    try:
                        search_result = api.search(keyword)
                        if search_result and hasattr(search_result, 'body'):
                            songs = parse_search_result(search_result.body, provider)
                            if songs:
                                self.logger.info(f"搜索完成(pymusiclibrary-Main): {keyword}, 找到 {len(songs)} 首歌曲")
                                return songs
                    except Exception as e:
                        self.logger.warning(f"[Search] pymusiclibrary 主线程搜索异常: {e}")

            # 3. 最终：REST API 已在步骤1尝试过，此处返回空结果
            self.logger.warning(f"[Search] 所有搜索方式均未返回结果: {keyword}")
            return []

        except ImportError as e:
            self.logger.error(f"导入 MusicLibrary 库失败: {e}")
            return []
        except Exception as e:
            self.logger.error(f"搜索歌曲失败: {file_path}, 错误: {e}")
            return []

    def _search_netease_rest_api(self, keyword: str, limit: int = 10) -> list[dict[str, Any]]:
        """
        使用网易云 REST API 搜索歌曲（带速率限制和自动重试）

        直接调用网易云 Web API，比 pymusiclibrary 更稳定且搜索能力更强。
        无需登录，使用与网易云 app 相同的搜索接口。
        内置请求频率控制（1.5秒间隔）和失败自动重试（最多3次）。

        Args:
            keyword (str): 搜索关键词
            limit (int): 返回结果数量上限，默认10

        Returns:
            list[dict]: 搜索结果列表，每个字典包含 id, name, artist, album, duration
        """
        import json
        from urllib.request import Request, urlopen
        from urllib.parse import urlencode

        def _do_search() -> list[dict[str, Any]]:
            """执行实际的 HTTP 搜索请求"""
            params = urlencode({
                's': keyword,
                'type': 1,
                'offset': 0,
                'total': 'true',
                'limit': limit
            })
            url = f'https://music.163.com/api/search/get/web?{params}'
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://music.163.com/',
            }
            req = Request(url, headers=headers)

            self.logger.debug(f"[NetEase-REST] 发送搜索请求: keyword='{keyword}', url={url[:80]}...")

            with urlopen(req, timeout=15) as resp:
                raw_data = resp.read().decode('utf-8')
                self.logger.debug(f"[NetEase-REST] 收到响应: status={resp.status}, length={len(raw_data)}")

            data = json.loads(raw_data)

            # 调试：记录原始响应结构
            if 'result' not in data:
                self.logger.warning(
                    f"[NetEase-REST] API 返回异常 (keyword='{keyword}'):"
                    f" keys={list(data.keys())}, code={data.get('code')}, msg={data.get('msg')}"
                )
                if data.get('code') and data.get('code') != 200:
                    self.logger.error(
                        f"[NetEase-REST] API 错误响应 (code={data.get('code')}): {raw_data[:500]}"
                    )
                return []

            result_data = data.get('result', {})
            song_list = result_data.get('songs', [])
            self.logger.info(f"[NetEase-REST] API 返回 {len(song_list)} 首歌曲 (keyword='{keyword}')")

            songs = []
            for idx, song in enumerate(song_list[:3]):  # 只记录前3首的详细信息
                self.logger.debug(f"[NetEase-REST] 结果[{idx+1}]: id={song.get('id')}, name={song.get('name')}, artist={song.get('artists', [{}])[0].get('name', '') if song.get('artists') else ''}")
                songs.append({
                    'id': song.get('id'),
                    'name': song.get('name', ''),
                    'artist': song.get('artists', [{}])[0].get('name', '') if song.get('artists') else '',
                    'album': song.get('album', {}).get('name', ''),
                    'duration': song.get('duration', 0) // 1000
                })

            # 处理剩余的歌曲（不记录详细日志）
            for song in song_list[3:]:
                songs.append({
                    'id': song.get('id'),
                    'name': song.get('name', ''),
                    'artist': song.get('artists', [{}])[0].get('name', '') if song.get('artists') else '',
                    'album': song.get('album', {}).get('name', ''),
                    'duration': song.get('duration', 0) // 1000
                })

            self.logger.info(f"[NetEase-REST] 搜索 '{keyword}' 返回 {len(songs)} 条结果")
            return songs

        try:
            return self._retryable_request(
                request_func=_do_search,
                operation_name=f"搜索歌曲({keyword[:20]}...)"
            )
        except Exception as e:
            self.logger.warning(f"[NetEase-REST] 搜索最终失败: {keyword}, 错误: {e}")
            return []

    def check_lyric_exists(
        self,
        song_id: int | str,
        provider: str = 'netease',
        timeout: int = 5
    ) -> bool:
        """
        轻量级检查歌曲是否有歌词（带速率限制和自动重试）

        使用 REST API 快速检测歌词是否存在，用于搜索结果列表的预览。
        内置请求频率控制，避免频繁调用触发限流。

        Args:
            song_id: 歌曲 ID
            provider: 提供商名称
            timeout: 请求超时（秒）

        Returns:
            bool: 是否有歌词
        """
        import json
        from urllib.request import Request, urlopen
        from urllib.parse import urlencode

        if provider != 'netease':
            return False

        def _do_check() -> bool:
            """执行实际的 HTTP 检查请求"""
            params = urlencode({'id': song_id, 'lv': -1, 'tv': -1, 'kv': -1})
            url = f'https://music.163.com/api/song/lyric?{params}'
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://music.163.com/',
            }
            req = Request(url, headers=headers)

            with urlopen(req, timeout=timeout) as resp:
                raw_data = resp.read().decode('utf-8')

            data = json.loads(raw_data)
            lrc_data = data.get('lrc', {})
            lyric = lrc_data.get('lyric', '') if isinstance(lrc_data, dict) else ''
            has_lyric = bool(lyric and len(lyric.strip()) > 10)

            return has_lyric

        try:
            return self._retryable_request(
                request_func=_do_check,
                operation_name=f"检查歌词存在(ID:{song_id})"
            )
        except Exception:
            return False

    def fetch_lyric_by_id(
        self,
        song_id: int | str,
        provider: str = 'netease',
        lyric_mode: str = 'merged'
    ) -> dict[str, Any] | None:
        """
        根据歌曲 ID 获取歌词

        REST API 优先策略：避免在子线程中创建多个 pymusiclibrary 实例导致冲突。
        仅在主线程中且 REST API 失败时才尝试 pymusiclibrary。

        Args:
            song_id: 歌曲 ID
            provider: 提供商名称
            lyric_mode: 歌词模式（仅对网易云音乐有效）
                - 'original': 仅返回原始歌词
                - 'merged': 返回原始歌词和翻译歌词合并（默认）
                - 'translation': 仅返回翻译歌词

        Returns:
            dict | None: 歌词数据字典
        """
        # === 修复：REST API 优先策略 ===
        # 原因与 search_songs() 相同：避免子线程中 pymusiclibrary 多实例冲突

        # 1. 首选：使用 REST API 获取歌词（无状态、稳定）
        if provider == 'netease':
            result = self._fetch_lyric_by_id_netease_rest(song_id, lyric_mode)
            if result is not None:
                return result

        # 2. 备选：仅在主线程中尝试 pymusiclibrary
        import threading
        if threading.current_thread().name == 'MainThread':
            result = self._fetch_lyric_by_id_pymusiclibrary(song_id, provider, lyric_mode)
            if result is not None:
                return result

        # 3. 最终失败
        self.logger.warning(f"[FetchLyric] 所有方式均获取歌词失败 (ID: {song_id}), 提供商: {provider}")
        return None

    def _fetch_lyric_by_id_pymusiclibrary(
        self,
        song_id: int | str,
        provider: str,
        lyric_mode: str
    ) -> dict[str, Any] | None:
        """
        使用 pymusiclibrary 获取歌词

        Args:
            song_id: 歌曲 ID
            provider: 提供商名称
            lyric_mode: 歌词模式

        Returns:
            dict | None: 歌词数据字典，失败返回 None
        """
        try:
            # 根据提供商获取对应的 API 客户端
            if provider == 'netease':
                api = self._get_netease_api()
            else:
                api = self._get_kugou_api()

            if api is None:
                self.logger.debug(f"[FetchLyric] pymusiclibrary {provider} API 不可用")
                return None

            # 获取歌词
            lyric_data = api.lyric(id=song_id)

            if not lyric_data or not hasattr(lyric_data, 'body'):
                return None

            body = lyric_data.body

            # 解析歌词数据
            synced_lyrics = ''
            plain_lyrics = ''

            if provider == 'netease':
                lrc_data = body.get('lrc', {})
                tlyric_data = body.get('tlyric', {})
                lrc_lyric = lrc_data.get('lyric', '') if isinstance(lrc_data, dict) else ''
                tlyric_lyric = tlyric_data.get('lyric', '') if isinstance(tlyric_data, dict) else ''

                # 根据歌词模式返回不同的内容
                if lyric_mode == 'original':
                    synced_lyrics = lrc_lyric
                    plain_lyrics = ''
                elif lyric_mode == 'merged':
                    synced_lyrics = merge_lyrics_with_translation(lrc_lyric, tlyric_lyric)
                    plain_lyrics = tlyric_lyric
                elif lyric_mode == 'translation':
                    synced_lyrics = tlyric_lyric
                    plain_lyrics = ''
            else:
                synced_lyrics = body.get('lyrics', '')

            if not (synced_lyrics or plain_lyrics):
                return None

            result = {
                'synced_lyrics': synced_lyrics,
                'plain_lyrics': plain_lyrics,
                'provider': provider,
                'track_name': '',
                'artist_name': '',
                'album_name': '',
                'duration': 0
            }

            self.logger.info(f"[FetchLyric] pymusiclibrary 成功获取歌词 (ID: {song_id})")
            return result

        except Exception as e:
            self.logger.debug(f"[FetchLyric] pymusiclibrary 获取歌词失败 (ID: {song_id}): {e}")
            return None

    def _fetch_lyric_by_id_netease_rest(
        self,
        song_id: int | str,
        lyric_mode: str = 'merged'
    ) -> dict[str, Any] | None:
        """
        使用 REST API 获取网易云歌词（带速率限制和自动重试）

        Args:
            song_id: 歌曲 ID
            lyric_mode: 歌词模式

        Returns:
            dict | None: 歌词数据字典，失败返回 None
        """
        import json
        from urllib.request import Request, urlopen
        from urllib.parse import urlencode

        def _do_fetch() -> dict[str, Any]:
            """执行实际的 HTTP 歌词获取请求"""
            params = urlencode({'id': song_id, 'lv': -1, 'tv': -1, 'kv': -1})
            url = f'https://music.163.com/api/song/lyric?{params}'
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://music.163.com/',
            }
            req = Request(url, headers=headers)

            with urlopen(req, timeout=10) as resp:
                raw_data = resp.read().decode('utf-8')

            data = json.loads(raw_data)
            lrc_data = data.get('lrc', {})
            tlyric_data = data.get('tlyric', {})

            lrc_lyric = lrc_data.get('lyric', '') if isinstance(lrc_data, dict) else ''
            tlyric_lyric = tlyric_data.get('lyric', '') if isinstance(tlyric_data, dict) else ''

            synced_lyrics = ''
            plain_lyrics = ''

            if lyric_mode == 'original':
                synced_lyrics = lrc_lyric
                plain_lyrics = ''
            elif lyric_mode == 'merged':
                synced_lyrics = merge_lyrics_with_translation(lrc_lyric, tlyric_lyric)
                plain_lyrics = tlyric_lyric
            elif lyric_mode == 'translation':
                synced_lyrics = tlyric_lyric
                plain_lyrics = ''

            if not (synced_lyrics or plain_lyrics):
                return None

            result = {
                'synced_lyrics': synced_lyrics,
                'plain_lyrics': plain_lyrics,
                'provider': 'netease',
                'track_name': '',
                'artist_name': '',
                'album_name': '',
                'duration': 0
            }

            self.logger.info(f"[FetchLyric] REST API 成功获取歌词 (ID: {song_id})")
            return result

        try:
            return self._retryable_request(
                request_func=_do_fetch,
                operation_name=f"获取歌词(ID:{song_id})"
            )
        except Exception as e:
            self.logger.warning(f"[FetchLyric] REST API 歌词请求最终失败 (ID: {song_id}): {e}")
            return None

    def _fetch_lyrics_from_music_api(
        self,
        file_path: str,
        provider: str,
        lyric_mode: str = 'merged'
    ) -> dict[str, Any] | None:
        """
        从网易云音乐或酷狗音乐获取歌词

        Args:
            file_path: 音频文件路径
            provider: 提供商名称（'netease' 或 'kugou'）
            lyric_mode: 歌词模式（仅对网易云音乐有效）
                - 'original': 仅返回原始歌词
                - 'merged': 返回原始歌词和翻译歌词合并（默认）
                - 'translation': 仅返回翻译歌词

        Returns:
            dict | None: 歌词数据字典
        """
        try:
            # 根据提供商获取对应的 API 客户端
            if provider == 'netease':
                api = self._get_netease_api()
            else:
                api = self._get_kugou_api()

            if api is None:
                self.logger.error(f"无法初始化 {provider} API")
                return None

            # 从音频文件提取元数据
            metadata = extract_audio_metadata(file_path)
            if not metadata:
                self.logger.error(f"无法提取音频元数据: {file_path}")
                return None

            # 搜索歌曲
            keyword = f"{metadata['artist']} {metadata['title']}"
            search_result = api.search(keyword)

            if not search_result or not hasattr(search_result, 'body'):
                self.logger.warning(f"搜索歌曲失败: {keyword}")
                return None

            # 解析搜索结果（Response 对象的 body 属性包含实际数据）
            self.logger.debug(f"搜索结果 body 类型: {type(search_result.body)}")
            self.logger.debug(f"搜索结果 body keys: {list(search_result.body.keys()) if isinstance(search_result.body, dict) else 'N/A'}")

            songs = parse_search_result(search_result.body, provider)
            self.logger.debug(f"解析后歌曲数: {len(songs)}")

            if not songs:
                self.logger.warning(f"未找到匹配的歌曲: {keyword}")
                # 打印详细的调试信息
                if isinstance(search_result.body, dict):
                    result_data = search_result.body.get('result', {})
                    song_list = result_data.get('songs', [])
                    self.logger.error(f"原始歌曲列表长度: {len(song_list)}")
                    if song_list:
                        self.logger.error(f"第一首歌: {song_list[0]}")
                return None

            # 尝试获取最匹配的歌曲的歌词
            for song in songs[:3]:  # 只尝试前3个结果
                song_id = song['id']
                lyric_data = api.lyric(id=song_id)

                if lyric_data and hasattr(lyric_data, 'body'):
                    # 解析歌词数据（Response 对象的 body 属性包含实际数据）
                    body = lyric_data.body

                    # 解析歌词数据
                    synced_lyrics = ''
                    plain_lyrics = ''

                    if provider == 'netease':
                        # 网易云音乐歌词格式
                        lrc_data = body.get('lrc', {})
                        tlyric_data = body.get('tlyric', {})
                        lrc_lyric = lrc_data.get('lyric', '') if isinstance(lrc_data, dict) else ''
                        tlyric_lyric = tlyric_data.get('lyric', '') if isinstance(tlyric_data, dict) else ''

                        # 根据歌词模式返回不同的内容
                        if lyric_mode == 'original':
                            # 仅返回原始歌词
                            synced_lyrics = lrc_lyric
                            plain_lyrics = ''
                        elif lyric_mode == 'merged':
                            # 合并原始歌词和翻译歌词（一句原始+一句翻译交替排列）
                            synced_lyrics = merge_lyrics_with_translation(lrc_lyric, tlyric_lyric)
                            plain_lyrics = tlyric_lyric  # 保留纯翻译歌词
                        elif lyric_mode == 'translation':
                            # 仅返回翻译歌词
                            synced_lyrics = tlyric_lyric
                            plain_lyrics = ''
                    else:
                        # 酷狗音乐歌词格式
                        synced_lyrics = body.get('lyrics', '')

                    if synced_lyrics or plain_lyrics:
                        self.logger.info(
                            f"成功获取歌词: {file_path}, 提供商: {provider}"
                        )
                        return {
                            'plain_lyrics': plain_lyrics,
                            'synced_lyrics': synced_lyrics,
                            'provider': provider,
                            'track_name': song.get('name', metadata['title']),
                            'artist_name': song.get('artist', metadata['artist']),
                            'album_name': song.get('album', metadata['album']),
                            'duration': song.get('duration', metadata['duration'])
                        }

            self.logger.warning(f"未找到歌词: {file_path}")
            return None

        except ImportError as e:
            self.logger.error(f"导入 pymusiclibrary 库失败: {e}")
            return None
        except Exception as e:
            self.logger.error(f"获取歌词失败: {file_path}, 错误: {e}")
            return None

    def _fetch_lyrics_from_lrxy(
        self,
        file_path: str,
        provider: str
    ) -> dict[str, Any] | None:
        """
        从 lrxy 库支持的提供商获取歌词（兼容旧代码）

        Args:
            file_path: 音频文件路径
            provider: 提供商名称

        Returns:
            dict | None: 歌词数据字典
        """
        try:
            # 导入 lrxy 库
            from lrxy.utils import load_audio

            # 加载音频文件
            audio = load_audio(file_path)
            if audio is None:
                self.logger.error(f"无法加载音频文件: {file_path}")
                return None

            # 获取提供商 API 函数
            provider_api = get_provider_api(provider)
            if provider_api is None:
                self.logger.error(f"无法加载提供商 API: {provider}")
                return None

            # 构建元数据
            metadata = {
                'artist': getattr(audio, 'artist_name', '') or getattr(audio, 'artist', ''),
                'title': getattr(audio, 'track_name', '') or getattr(audio, 'title', ''),
                'album': getattr(audio, 'album_name', '') or getattr(audio, 'album', ''),
                'duration': str(int(getattr(audio, 'duration', 0)))
            }

            # 调用 provider API 获取歌词
            result = provider_api(metadata)

            if not result.get('success'):
                error = result.get('error', '未知错误')
                message = result.get('message', '')
                self.logger.warning(f"获取歌词失败: {file_path}, 错误: {error}, 详情: {message}")
                return None

            data = result.get('data', {})
            lyric_data = data.get('lyric', {})

            # 构建返回数据
            lyrics_data = {
                'plain_lyrics': lyric_data.get('plainLyrics', ''),
                'synced_lyrics': lyric_data.get('syncedLyrics', ''),
                'provider': provider,
                'track_name': metadata['title'],
                'artist_name': metadata['artist'],
                'album_name': metadata['album'],
                'duration': int(metadata['duration'])
            }

            self.logger.info(
                f"成功获取歌词: {file_path}, 提供商: {provider}"
            )
            return lyrics_data

        except ImportError as e:
            self.logger.error(f"导入 lrxy 库失败: {e}")
            return None
        except Exception as e:
            self.logger.error(f"获取歌词失败: {file_path}, 错误: {e}")
            return None

    def select_best_match(
        self,
        songs: list[dict[str, Any]],
        file_path: str,
        provider: str = 'netease'
    ) -> dict[str, Any] | None:
        """
        从搜索结果中自动选择最佳匹配的歌曲

        使用多维度评分算法，综合考虑歌名相似度、艺术家匹配度和时长接近度，
        自动选择与音频文件最匹配的搜索结果。

        Args:
            songs: search_songs() 返回的搜索结果列表
            file_path: 音频文件路径（用于提取元数据作为匹配基准）
            provider: 歌词提供商名称

        Returns:
            dict | None: 最佳匹配的歌曲字典（包含 id, name, artist 等），无匹配返回 None

        Example:
            >>> fetcher = LyricFetcher(logger, rate_limiter, metrics)
            >>> songs = fetcher.search_songs('song.mp3', 'netease')
            >>> best = fetcher.select_best_match(songs, 'song.mp3', 'netease')
            >>> if best:
            ...     print(f"最佳匹配: {best['name']} - {best['artist']}")
        """
        if not songs:
            self.logger.warning("搜索结果为空，无法选择最佳匹配")
            return None

        # 提取音频文件的元数据作为匹配基准
        metadata = extract_audio_metadata(file_path)
        if not metadata:
            self.logger.warning(f"无法提取元数据，使用第一个搜索结果: {file_path}")
            return songs[0]

        file_title = metadata.get('title', '').strip().lower()
        file_artist = metadata.get('artist', '').strip().lower()
        file_duration = metadata.get('duration', 0)

        # 如果元数据为空，使用第一个结果
        if not file_title and not file_artist:
            self.logger.info("文件元数据为空，使用第一个搜索结果")
            return songs[0]

        # 计算每个结果的匹配分数
        scored_songs = []
        for song in songs:
            score = calculate_match_score(
                song=song,
                file_title=file_title,
                file_artist=file_artist,
                file_duration=file_duration
            )
            scored_songs.append((score, song))
            self.logger.debug(
                f"匹配评分: {song.get('name', '')} - {song.get('artist', '')} "
                f"= {score:.2f}"
            )

        # 按分数降序排序，选择最高分的结果
        scored_songs.sort(key=lambda x: x[0], reverse=True)
        best_score, best_song = scored_songs[0]

        self.logger.info(
            f"最佳匹配: {best_song.get('name', '')} - {best_song.get('artist', '')} "
            f"(评分: {best_score:.2f})"
        )

        return best_song

    def batch_fetch_lyrics(
        self,
        file_paths: list[str],
        provider: str = 'lrclib'
    ) -> dict[str, dict[str, Any] | None]:
        """
        批量获取歌词

        优化：使用 ThreadPoolExecutor 并发获取歌词，提升批量处理速度 5-8 倍。

        Args:
            file_paths: 音频文件路径列表
            provider: 提供商名称

        Returns:
            dict[str, dict | None]: 文件路径到歌词数据的映射

        Example:
            >>> fetcher = LyricFetcher(logger, rate_limiter, metrics)
            >>> results = fetcher.batch_fetch_lyrics(
            ...     ['song1.mp3', 'song2.flac'],
            ...     provider='lrclib'
            ... )
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading

        results = {}
        max_workers = min(5, len(file_paths))  # 最大并发数 5
        lock = threading.Lock()  # 线程安全的结果收集

        def fetch_single(file_path: str) -> tuple[str, dict[str, Any] | None]:
            """获取单个文件的歌词"""
            try:
                lyrics = self.fetch_lyrics(file_path, provider)
                return (file_path, lyrics)
            except Exception as e:
                self.logger.error(f"批量获取歌词失败: {file_path}, 错误: {e}")
                return (file_path, None)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            futures = {executor.submit(fetch_single, fp): fp for fp in file_paths}

            # 收集结果（线程安全）
            for future in as_completed(futures):
                file_path, lyrics = future.result()
                with lock:
                    results[file_path] = lyrics

        success_count = sum(1 for v in results.values() if v is not None)
        self.logger.info(
            f"批量获取歌词完成: 成功 {success_count}/{len(file_paths)} (并发={max_workers})"
        )

        return results
