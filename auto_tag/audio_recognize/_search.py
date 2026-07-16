# auto_tag/audio_recognize/_search.py
"""
Multi-source search module: search results data structures, caching,
rate limiting, and search implementations for NetEase, QQ Music, KuGou.

Depends on: _infra (get_netease_api, get_kugou_api)
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import re
import threading
import time
from typing import Any
from urllib.parse import urlencode

from ._infra import get_kugou_api, get_netease_api

logger = logging.getLogger(__name__)


# 多数据源搜索结果数据结构
class SearchResult:
    """
    多平台音乐搜索结果封装类

    Attributes:
        source: 数据来源平台标识（"shazam"|"netease"|"kugou"）
        fingerprint_engine: 音频指纹识别引擎来源（"acoustid"|"shazam"|"metadata"|"none"）
        title: 歌曲标题
        artist: 艺术家
        album: 专辑名
        year: 发行年份（可选）
        genre: 音乐流派/类型（可选）
        cover_link: 封面图片URL
        song_id: 平台歌曲ID
        duration: 歌曲时长（秒）
        confidence: 置信度/相关度评分（0-1）
        raw_data: 原始API返回数据
    """

    def __init__(
        self,
        source: str,
        title: str,
        artist: str,
        album: str,
        cover_link: str = "",
        song_id: str = "",
        duration: int = 0,
        confidence: float = 1.0,
        raw_data: dict | None = None,
        fingerprint_engine: str = "none",
        year: str = "",
        genre: str = "",
    ) -> None:
        """
        初始化搜索结果

        Args:
            source: 数据来源平台
            title: 歌曲标题
            artist: 艺术家
            album: 专辑名
            cover_link: 封面URL
            song_id: 歌曲ID
            duration: 时长
            confidence: 置信度
            raw_data: 原始数据
            fingerprint_engine: 音频指纹识别引擎来源
            year: 发行年份（可选）
            genre: 音乐流派（可选）
        """
        self.source = source
        self.fingerprint_engine = fingerprint_engine
        self.title = title
        self.artist = artist
        self.album = album
        self.year = year
        self.genre = genre
        self.cover_link = cover_link
        self.song_id = song_id
        self.duration = duration
        self.confidence = confidence
        self.raw_data = raw_data

    def get_combined_source(self) -> str:
        """
        获取组合来源字符串

        Returns:
            str: 组合来源，如 "Acoustid + 网易云音乐" 或 "Shazam + QQ音乐"
        """
        if self.fingerprint_engine != "none":
            # 将引擎名称转换为显示名称
            engine_display = {
                "acoustid": "Acoustid",
                "shazam": "Shazam",
                "metadata": "音频标签",
                "filename": "文件名",
            }.get(self.fingerprint_engine, self.fingerprint_engine)

            # 将平台名称转换为显示名称
            source_display = {
                "netease": "网易云音乐",
                "qqmusic": "QQ音乐",
                "kugou": "酷狗音乐",
                "shazam": "Shazam",
            }.get(self.source, self.source)

            return f"{engine_display} + {source_display}"
        else:
            # 返回原始来源名称
            source_display = {
                "netease": "网易云音乐",
                "qqmusic": "QQ音乐",
                "kugou": "酷狗音乐",
                "shazam": "Shazam",
            }.get(self.source, self.source)

            return source_display

    def to_dict(self) -> dict[str, Any]:
        """
        转换为字典格式

        ✅ 修复#3：移除raw_data字段以减少内存占用
        原始API响应数据通常包含大量冗余信息（完整艺术家详情、专辑曲目列表等），
        34个文件 × 4个结果 = 136个SearchResult，每个raw_data可能10-50KB，总计1.3-6.8MB。
        UI层只需要展示用的关键字段，不需要原始响应数据。
        """
        return {
            "source": self.source,
            "fingerprint_engine": self.fingerprint_engine,
            "combined_source": self.get_combined_source(),
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "year": self.year,
            "genre": self.genre,
            "cover_link": self.cover_link,
            "song_id": self.song_id,
            "duration": self.duration,
            "confidence": self.confidence,
        }


def _flatten_shazam_metadata(track: dict) -> dict:
    """
    将 Shazam API 的嵌套 metadata 结构扁平化为标准字典

    转换前 (Shazam 原始格式):
        {
            "sections": [{
                "metadata": [
                    {"title": "Album", "text": "Weathering With You"},
                    {"title": "Genre", "text": "Anime"}
                ]
            }]
        }

    转换后 (标准格式):
        {
            "album": "Weathering With You",
            "genre": "Anime"
        }

    Args:
        track: Shazam API 返回的 track 字典

    Returns:
        dict: 扁平化的元数据字典（键名小写）
    """
    result = {}

    for section in track.get("sections", []):
        for meta in section.get("metadata", []):
            key = str(meta.get("title", "")).strip().lower()
            value = str(meta.get("text", "")).strip()

            if key and value:
                if key not in result:
                    result[key] = value
                    logger.debug(f"提取元数据: {key} = {value}")

    return result


def _parse_shazam_result(track: dict) -> SearchResult:
    """
    解析 Shazam API 返回的歌曲数据

    Args:
        track: Shazam 返回的 track 字典

    Returns:
        SearchResult: 解析后的搜索结果
    """
    title = track.get("title", "Unknown Title")
    artist = track.get("subtitle", "Unknown Artist")

    # 使用标准化函数提取嵌套元数据（替代旧版 find_deepest_metadata_key）
    flat_meta = _flatten_shazam_metadata(track)
    album = flat_meta.get("album", "Unknown Album")
    genre = flat_meta.get("genre", "")
    cover = track.get("images", {}).get("coverart", "")
    duration = 0

    # 尝试从 sections 中提取时长信息
    # 注意：Shazam API 返回的 metadata 可能是 list 或 dict
    for section in track.get("sections", []):
        if section.get("type") == "SONG":
            metadata = section.get("metadata")
            if isinstance(metadata, dict):
                # 旧版格式：metadata 是字典
                duration = metadata.get("duration", 0) or 0
            elif isinstance(metadata, list):
                # 新版格式：metadata 是列表，需要查找 duration 条目
                for item in metadata:
                    if isinstance(item, dict):
                        # 尝试通过 title 匹配
                        if item.get("title") == "Duration":
                            try:
                                duration = int(item.get("text", 0)) or 0
                            except (ValueError, TypeError):
                                duration = 0
                            break
                        # 或者直接尝试获取 duration 键
                        if "duration" in item:
                            try:
                                duration = int(item["duration"]) or 0
                            except (ValueError, TypeError):
                                duration = 0
                            break
            break

    return SearchResult(
        source="shazam",
        title=title,
        artist=artist,
        album=album,
        genre=genre,
        cover_link=cover,
        duration=duration,
        confidence=1.0,
        raw_data=track,
    )


def _parse_netease_result(song: dict) -> SearchResult:
    """
    解析网易云音乐 API 返回的歌曲数据

    Args:
        song: 网易云音乐返回的歌曲字典

    Returns:
        SearchResult: 解析后的搜索结果
    """
    title = song.get("name", "Unknown Title")
    artists = song.get("artists", [])
    artist = " / ".join([a.get("name", "Unknown") for a in artists]) if artists else "Unknown Artist"
    album_info = song.get("album", {})
    album = album_info.get("name", "Unknown Album") if album_info else "Unknown Album"
    song_id = str(song.get("id", ""))
    duration_ms = song.get("duration", 0)
    duration = duration_ms // 1000 if duration_ms else 0

    # 获取年份和流派
    year = ""
    genre = ""
    if album_info and isinstance(album_info, dict):
        publish_time = album_info.get("publishTime")
        if publish_time:
            try:
                from datetime import datetime
                year = str(datetime.fromtimestamp(publish_time / 1000).year)
            except (ValueError, TypeError, OSError):
                pass

    # 获取封面（多策略尝试）
    cover = _extract_netease_cover(song, album_info)

    logger.debug(f"[NetEase] Cover URL for '{title}': '{cover[:80]}...' if cover else '(empty)'")

    return SearchResult(
        source="netease",
        title=title,
        artist=artist,
        album=album,
        year=year,
        genre=genre,
        cover_link=cover,
        song_id=song_id,
        duration=duration,
        confidence=0.9,
        raw_data=song,
    )


def _parse_qqmusic_result(song: dict) -> SearchResult:
    """
    解析 QQ 音乐官方 API 返回的歌曲数据

    QQ 音乐官方 API (c.y.qq.com) 返回的数据结构：
    - id: 歌曲数字 ID（原 songid）
    - mid: 歌曲字符串 ID（原 songmid）
    - name: 歌曲名称（原 songname）
    - singer: 歌手列表（每个元素包含 id、mid 和 name）
    - album: 专辑对象（包含 id、mid、name）- 注意是嵌套对象！
    - interval: 歌曲时长（秒）

    注意：与旧版公共代理 API (api.qq.jsososo.com) 的字段名不同！
    旧版使用扁平字段（songname, albumname），新版使用嵌套结构。

    Args:
        song: QQ 音乐返回的歌曲字典

    Returns:
        SearchResult: 解析后的搜索结果，source 标记为 'qqmusic'
    """
    title = song.get("name", "Unknown Title")

    # 提取歌手信息（支持多位歌手，用 " / " 连接）
    singers = song.get("singer", [])
    if singers and isinstance(singers, list):
        artist = " / ".join([s.get("name", "Unknown") for s in singers if s.get("name")])
    else:
        artist = "Unknown Artist"

    # 提取专辑信息（新接口使用嵌套的 album 对象）
    album_info = song.get("album", {})
    if isinstance(album_info, dict):
        album = album_info.get("name", "Unknown Album")
    else:
        album = "Unknown Album"

    song_id = str(song.get("id", ""))

    # 时长（秒），需要转换为整数
    try:
        duration = int(song.get("interval", 0))
    except (ValueError, TypeError):
        duration = 0

    # 使用 album.mid 构建封面 URL
    if isinstance(album_info, dict):
        albummid = album_info.get("mid", "")
    else:
        albummid = ""
    if albummid:
        cover_link = f"https://y.gtimg.cn/music/photo_new/T002R500x500M000{albummid}.jpg"
    else:
        cover_link = ""

    logger.debug(f"[QQMusic] Parsed result: {title} - {artist} (ID: {song_id}, Duration: {duration}s)")

    return SearchResult(
        source="qqmusic",
        title=title,
        artist=artist,
        album=album,
        cover_link=cover_link,
        song_id=song_id,
        duration=duration,
        confidence=0.9,
        raw_data=song,
    )


def _parse_netease_radio_result(radio: dict) -> SearchResult:
    """
    解析网易云音乐 API 返回的电台/声音数据（type=1009）

    电台数据结构与歌曲不同，主要字段：
    - id: 电台 ID
    - name: 电台名称
    - dj: DJ 信息字典
    - picUrl: 封面图片 URL
    - desc: 描述
    - programCount: 节目数量
    - category: 分类
    - secondCategory: 子分类

    Args:
        radio: 网易云音乐返回的电台字典

    Returns:
        SearchResult: 解析后的搜索结果，source 标记为 'netease-radio'
    """
    radio_name = radio.get("name", "Unknown Radio")
    radio_id = str(radio.get("id", ""))

    # 提取 DJ/主播信息
    dj_info = radio.get("dj", {})
    dj_name = dj_info.get("name", "") if dj_info else ""
    artist = dj_name if dj_name else "NetEase Radio"

    # 封面图片
    cover = radio.get("picUrl", "")

    # 描述作为补充信息
    desc = radio.get("desc", "")

    # 构建标题（包含描述信息）
    title = f"[电台] {radio_name}"
    if desc and len(desc) > 0:
        title = f"{title} - {desc[:50]}"  # 截取前50字符避免过长

    # 专辑字段使用分类信息
    category = radio.get("category", "")
    second_category = radio.get("secondCategory", "")
    album = f"{second_category}" if second_category else (category if category else "Radio")

    logger.debug(f"[NetEase-Radio] Parsed radio: {radio_name}, DJ: {dj_name}, Category: {album}")

    return SearchResult(
        source="netease-radio",
        title=title,
        artist=artist,
        album=album,
        cover_link=cover,
        song_id=radio_id,
        duration=0,
        confidence=0.75,
        raw_data=radio,
    )


def _parse_kugou_result(song: dict) -> SearchResult:
    """
    解析酷狗音乐 API 返回的歌曲数据

    Args:
        song: 酷狗音乐返回的歌曲字典

    Returns:
        SearchResult: 解析后的搜索结果
    """
    title = song.get("songname", song.get("songname_original", "Unknown Title"))
    artist = song.get("singername", "Unknown Artist")
    album = song.get("album_name", "Unknown Album")
    song_id = str(song.get("hash", song.get("fileid", "")))
    duration = song.get("duration", 0)

    # 获取封面
    cover = song.get("album_pic", "") or song.get("imgurl", "")

    return SearchResult(
        source="kugou",
        title=title,
        artist=artist,
        album=album,
        cover_link=cover,
        song_id=song_id,
        duration=duration,
        confidence=0.85,
        raw_data=song,
    )


def _extract_netease_cover(song: dict, album_info: dict) -> str:
    """
    从网易云音乐响应中提取封面图片URL

    尝试多种策略获取真实的图片URL，
    并处理网易云返回的相对路径问题。

    Args:
        song: 歌曲数据字典
        album_info: 专辑信息字典

    Returns:
        str: 封面图片URL（可能是相对路径或绝对路径）
    """
    cover = ""

    # 策略1: 从 album_info 获取
    if album_info:
        cover = album_info.get("picUrl", "")
        if not cover:
            cover = album_info.get("blurPicUrl", "")

    # 策略2: 从 song 顶层获取
    if not cover:
        cover = song.get("picUrl", "") or song.get("albumPic", "") or song.get("coverImgUrl", "")

    # 策略3: 从 artists 获取
    if not cover:
        artists = song.get("artists", [])
        for a in artists:
            artist_cover = a.get("picUrl", "") or a.get("img1v1Url", "")
            if artist_cover:
                cover = artist_cover
                break

    # 策略4: 使用网易云音乐的CDN域名拼接
    if cover:
        # 如果URL不是以http开头，需要加上域名
        if not cover.startswith("http"):
            # 网易云音乐的图片CDN
            if cover.startswith("//"):
                cover = "https:" + cover
            elif cover.startswith("/"):
                cover = "https://music.163.com" + cover
            else:
                cover = "https://p1.music.126.net/" + cover

    return cover


class SearchCache:
    """
    搜索结果缓存（线程安全LRU + TTL）

    特性：
    - LRU淘汰：超出容量时自动移除最久未使用的条目
    - TTL过期：超过时间限制的条目自动失效
    - 线程安全：使用锁保护并发访问
    - 命中统计：记录命中率用于性能分析
    """

    def __init__(self, max_size: int = 100, ttl_seconds: int = 300):
        """
        初始化缓存

        Args:
            max_size: 最大缓存条目数（默认100）
            ttl_seconds: 条目存活时间，秒（默认5分钟）
        """
        self._cache: dict[str, tuple[float, list[SearchResult]]] = {}
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, keyword: str) -> list[SearchResult] | None:
        """
        获取缓存结果

        Args:
            keyword: 搜索关键词

        Returns:
            缓存的搜索结果列表，未命中或已过期返回None
        """
        with self._lock:
            if keyword not in self._cache:
                self._misses += 1
                return None

            timestamp, results = self._cache[keyword]
            elapsed = time.time() - timestamp

            if elapsed > self._ttl:
                del self._cache[keyword]
                self._misses += 1
                logger.debug(f"[Cache] EXPIRED '{keyword}' (age={elapsed:.0f}s)")
                return None

            self._hits += 1
            logger.info(f"[Cache] HIT '{keyword}' ({len(results)} results, age={elapsed:.0f}s)")
            return results

    def set(self, keyword: str, results: list[SearchResult]) -> None:
        """
        写入缓存

        Args:
            keyword: 搜索关键词
            results: 搜索结果列表
        """
        with self._lock:
            if len(self._cache) >= self._max_size and keyword not in self._cache:
                oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][0])
                del self._cache[oldest_key]
                logger.debug(f"[Cache] EVICTED '{oldest_key}' (cache full)")

            self._cache[keyword] = (time.time(), results)
            logger.info(f"[Cache] STORED '{keyword}' ({len(results)} results)")

    def clear(self) -> None:
        """清空所有缓存"""
        with self._lock:
            size = len(self._cache)
            self._cache.clear()
            logger.info(f"[Cache] CLEARED ({size} entries removed)")

    def stats(self) -> dict:
        """获取缓存统计信息"""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": f"{hit_rate:.1f}%",
                "ttl_seconds": self._ttl,
            }


class RateLimiter:
    """
    API请求限流器（自适应间隔控制）

    特性：
    - 最小间隔保护：避免请求过于密集触发反爬
    - 自适应调整：遇到限流自动增加间隔，成功后逐渐恢复
    - 最大间隔上限：防止等待时间过长影响体验
    - 线程安全：多线程环境下正确工作
    """

    def __init__(
        self,
        min_interval: float = 1.0,
        max_interval: float = 10.0,
        backoff_factor: float = 2.0,
        recovery_factor: float = 0.8,
    ):
        """
        初始化限流器

        Args:
            min_interval: 最小请求间隔（秒），默认1秒
            max_interval: 最大请求间隔（秒），默认10秒
            backoff_factor: 遇到限流时的退避倍数，默认2倍
            recovery_factor: 成功后的恢复系数，默认0.8（间隔缩短20%）
        """
        self._min_interval = min_interval
        self._max_interval = max_interval
        self._backoff_factor = backoff_factor
        self._recovery_factor = recovery_factor
        self._current_interval = min_interval
        self._last_request_time = 0.0
        self._lock = threading.Lock()
        self._rate_limited_count = 0

    async def wait_if_needed(self) -> float:
        """
        如果距离上次请求太近，则等待适当时间

        Returns:
            实际等待时间（秒），0表示无需等待
        """
        with self._lock:
            elapsed = time.time() - self._last_request_time
            wait_time = max(0, self._current_interval - elapsed)

            if wait_time > 0:
                logger.info(
                    f"[RateLimiter] Waiting {wait_time:.2f}s "
                    f"(interval={self._current_interval:.1f}s, elapsed={elapsed:.2f}s)"
                )

        if wait_time > 0:
            await asyncio.sleep(wait_time)
            return wait_time

        return 0.0

    def record_request(self) -> None:
        """记录一次请求时间戳"""
        with self._lock:
            self._last_request_time = time.time()

    def on_success(self) -> None:
        """
        请求成功时调用

        逐渐恢复默认间隔（但不会低于最小值）
        """
        with self._lock:
            old_interval = self._current_interval
            self._current_interval = max(
                self._min_interval,
                self._current_interval * self._recovery_factor
            )
            logger.debug(
                f"[RateLimiter] Success: {old_interval:.2f}s → {self._current_interval:.2f}s"
            )

    def on_rate_limited(self) -> None:
        """
        遇到频率限制时调用

        增加请求间隔（但不会超过最大值）
        """
        with self._lock:
            old_interval = self._current_interval
            self._current_interval = min(
                self._max_interval,
                self._current_interval * self._backoff_factor
            )
            self._rate_limited_count += 1
            logger.warning(
                f"[RateLimiter] Rate limited! Interval increased: "
                f"{old_interval:.2f}s → {self._current_interval:.2f}s "
                f"(limit count: {self._rate_limited_count})"
            )

    def stats(self) -> dict:
        """获取限流器统计信息"""
        with self._lock:
            return {
                "current_interval": round(self._current_interval, 2),
                "min_interval": self._min_interval,
                "max_interval": self._max_interval,
                "rate_limited_count": self._rate_limited_count,
            }


# 全局单例：搜索缓存和限流器（模块级共享）
_search_cache = SearchCache(max_size=150, ttl_seconds=300)
_rate_limiter = RateLimiter(min_interval=1.0, max_interval=8.0)

# 全局 Cookie（用于网易云 API 请求认证）
_netease_cookie: str | None = None
_login_lock = threading.Lock()


def _login_netease_guest() -> str | None:
    """
    网易云音乐游客登录

    通过访问网易云首页获取游客 cookie，
    用于后续 API 请求（获取封面图片等）。

    Returns:
        str | None: 成功返回 Cookie 字符串，失败返回 None
    """
    global _netease_cookie

    with _login_lock:
        # 如果已经尝试过登录（无论成功失败），不再重复尝试
        if _netease_cookie is not None:
            return _netease_cookie if _netease_cookie else None

        try:
            import ssl
            import http.client

            ctx = ssl.create_default_context()
            ctx.check_hostname = True
            ctx.verify_mode = ssl.CERT_REQUIRED

            conn = http.client.HTTPSConnection(
                'music.163.com',
                timeout=10,
                context=ctx,
            )

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://music.163.com/',
            }

            # 访问首页获取 Cookie
            conn.request('GET', '/', headers=headers)
            response = conn.getresponse()

            # 提取 Set-Cookie 头
            set_cookie_headers = response.getheaders()
            cookies = []
            for name, value in set_cookie_headers:
                if name.lower() == 'set-cookie':
                    # 提取第一个 key=value 对
                    if ';' in value:
                        cookie_part = value.split(';')[0]
                    else:
                        cookie_part = value
                    cookies.append(cookie_part)

            response.read()
            conn.close()

            if cookies:
                # 合并所有 Cookie
                cookie = '; '.join(cookies)
                _netease_cookie = cookie
                logger.info(f"[NetEase-Login] Guest login successful, cookie: {cookie[:50]}...")
                return cookie
            else:
                logger.warning(f"[NetEase-Login] No cookie received from homepage visit")
                _netease_cookie = ''
                return None
        except Exception as e:
            logger.error(f"[NetEase-Login] Login error: {e}")
            _netease_cookie = ''
            return None


def _get_netease_cover_by_id(song_id: str, cookie: str | None = None) -> str:
    """
    通过歌曲ID获取网易云音乐封面URL

    网易云搜索API不返回封面URL，需要通过歌曲详情接口获取。

    Args:
        song_id: 歌曲ID
        cookie: Cookie（可选）

    Returns:
        str: 封面图片URL，失败返回空字符串
    """
    if not song_id:
        return ''

    try:
        import ssl
        import http.client
        import json

        ctx = ssl.create_default_context()
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED

        conn = http.client.HTTPSConnection(
            'music.163.com',
            timeout=10,
            context=ctx,
        )

        path = f'/api/song/detail?id={song_id}&ids=[{song_id}]'

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://music.163.com/',
        }

        if cookie:
            headers['Cookie'] = cookie

        conn.request('GET', path, headers=headers)
        response = conn.getresponse()
        raw_data = response.read().decode('utf-8')
        conn.close()

        if response.status != 200:
            logger.warning(f"[NetEase-Cover] Failed to get song detail: status={response.status}")
            return ''

        data = json.loads(raw_data)
        songs = data.get('songs', [])
        if not songs:
            return ''

        song = songs[0]
        album = song.get('album', {})

        # 尝试多种字段
        cover = (
            album.get('picUrl', '') or
            album.get('blurPicUrl', '') or
            song.get('albumPic', '') or
            song.get('picUrl', '')
        )

        # 处理相对路径
        if cover and not cover.startswith("http"):
            if cover.startswith("//"):
                cover = "https:" + cover
            elif cover.startswith("/"):
                cover = "https://music.163.com" + cover
            else:
                cover = f"https://p1.music.126.net/{cover}"

        if cover:
            logger.debug(f"[NetEase-Cover] Got cover for song {song_id}: {cover[:80]}...")
            return cover
        else:
            logger.warning(f"[NetEase-Cover] No cover URL for song {song_id}")
            return ''

    except Exception as e:
        logger.error(f"[NetEase-Cover] Error: {e}")
        return ''


async def _search_netease_rest(
    keyword: str,
    limit: int = 5,
    max_retries: int = 3,
    include_radio: bool = True,
    fingerprint_engine: str = "none",
) -> list[SearchResult]:
    """
    纯 REST API 搜索网易云音乐（完全独立，不依赖 pymusiclibrary）

    使用 http.client 直接发起 HTTPS 请求，手动管理 SSL context 和连接，
    完全绕开 pymusiclibrary C 库和 urllib 全局状态。
    跨线程安全，无 access violation 风险。

    优化特性：
    - 内置搜索结果缓存（LRU + TTL），相同关键词直接返回
    - 自适应请求间隔控制，主动避免触发频率限制
    - 指数退避重试机制，自动处理网易云 API 频率限制（HTTP 405）
    - 支持同时搜索歌曲和电台/声音内容

    API 接口: GET https://music.163.com/api/search/get/web?s=关键词&type=1&limit=N

    Args:
        keyword: 搜索关键词
        limit: 返回结果数量上限（每种类型）
        max_retries: 最大重试次数（遇到频率限制时）
        include_radio: 是否同时搜索电台/声音内容（type=1009）
        fingerprint_engine: 音频指纹识别引擎来源

    Returns:
        list[SearchResult]: 搜索结果列表（歌曲+电台合并）
    """
    global _search_cache, _rate_limiter

    # Step 0: 强制清理关键词（最底层的保障）
    import re as _netease_re
    _original_keyword = keyword

    # 清理 1: 移除 "Unknown_Album/Artist" 等无效后缀
    if 'unknown' in keyword.lower() or 'n/a' in keyword.lower():
        logger.warning(f"[NetEase-CLEAN] Dirty keyword detected: '{keyword}'")
        keyword = _netease_re.sub(
            r'\s*[-–—:\s]+\s*(Unknown[_\s]*(Album|Artist|Title)|N/A|None)\s*$',
            '',
            keyword,
            flags=_netease_re.IGNORECASE
        ).strip()
        if keyword != _original_keyword:
            logger.warning(f"[NetEase-CLEAN] Cleaned suffix: '{_original_keyword}' -> '{keyword}'")

    # 清理 2: 如果关键词包含 "歌名 艺术家" 格式，尝试拆分只保留歌名
    if ' ' in keyword and not keyword.startswith(('http', 'www')):
        parts = keyword.split(' ', 1)
        if len(parts) >= 2 and len(parts[0]) >= 2:
            candidate_title = parts[0]
            if len(candidate_title) < len(keyword) * 0.6:
                logger.warning(
                    f"[NetEase-CLEAN] Splitting keyword: '{keyword}' -> '{candidate_title}'"
                )
                keyword = candidate_title

    # 最终检查：如果关键词变化了，需要更新缓存 key 并清除旧缓存
    if keyword != _original_keyword:
        logger.warning(f"[NetEase-CLEAN] Final keyword: '{keyword}' (original: '{_original_keyword}')")

        _dirty_cache_key = f"{_original_keyword}_radio" if include_radio else _original_keyword
        if _search_cache.get(_dirty_cache_key) is not None:
            logger.warning(f"[NetEase-CLEAN] Removing dirty cache for: '{_dirty_cache_key}'")
            try:
                with _search_cache._lock:
                    if _dirty_cache_key in _search_cache._cache:
                        del _search_cache._cache[_dirty_cache_key]
                        logger.info(f"[NetEase-CLEAN] Cache entry removed successfully")
            except Exception as cache_err:
                logger.debug(f"[NetEase-CLEAN] Failed to remove cache: {cache_err}")

        cache_key = f"{keyword}_radio" if include_radio else keyword

    # Step 1: 检查缓存（命中则直接返回，无需网络请求）
    cache_key = f"{keyword}_radio" if include_radio else keyword
    cached_results = _search_cache.get(cache_key)
    if cached_results is not None:
        for r in cached_results:
            r.fingerprint_engine = fingerprint_engine
        return cached_results

    # Step 2: 请求前等待（避免过于频繁）
    await _rate_limiter.wait_if_needed()

    import random

    all_results = []

    for attempt in range(max_retries + 1):
        try:
            # Step 3: 记录请求时间戳
            _rate_limiter.record_request()

            loop = asyncio.get_running_loop()

            song_results = await loop.run_in_executor(None, _do_single_search, keyword, limit, 1)
            all_results.extend(song_results)

            logger.info(f"[NetEase-REST] Found {len(song_results)} songs for '{keyword}'")

            if include_radio:
                radio_results = await loop.run_in_executor(None, _do_radio_search, keyword, limit)
                all_results.extend(radio_results)
                logger.info(f"[NetEase-REST] Found {len(radio_results)} radios for '{keyword}'")

            if all_results:
                for r in all_results:
                    r.fingerprint_engine = fingerprint_engine

                _search_cache.set(cache_key, all_results)
                _rate_limiter.on_success()

                logger.info(f"[NetEase-REST] Total results: {len(all_results)} (songs={len(song_results)}, radios={len(radio_results) if include_radio else 0})")
                return all_results

            if attempt < max_retries:
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                logger.warning(
                    f"[NetEase-REST] Retry {attempt + 1}/{max_retries} "
                    f"after {wait_time:.1f}s for '{keyword}'"
                )
                await asyncio.sleep(wait_time)

        except RuntimeError:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                _rate_limiter.record_request()

                song_future = executor.submit(_do_single_search, keyword, limit, 1)
                song_results = song_future.result(timeout=30)
                all_results.extend(song_results)

                if include_radio:
                    radio_future = executor.submit(_do_radio_search, keyword, limit)
                    radio_results = radio_future.result(timeout=30)
                    all_results.extend(radio_results)

                if all_results:
                    for r in all_results:
                        r.fingerprint_engine = fingerprint_engine

                    _search_cache.set(cache_key, all_results)
                    _rate_limiter.on_success()

                    logger.info(f"[NetEase-REST] Total results: {len(all_results)} (songs={len(song_results)}, radios={len(radio_results) if include_radio else 0})")
                    return all_results

                if attempt < max_retries:
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(
                        f"[NetEase-REST] Retry {attempt + 1}/{max_retries} "
                        f"after {wait_time:.1f}s for '{keyword}'"
                    )
                    await asyncio.sleep(wait_time)

        except Exception as e:
            logger.error(f"[NetEase-REST] Error on attempt {attempt + 1}: {e}", exc_info=True)
            if attempt < max_retries:
                await asyncio.sleep(1)

    logger.error(f"[NetEase-REST] All {max_retries} retries failed for '{keyword}'")
    return []


def _do_single_search(keyword: str, limit: int, search_type: int = 1) -> list[SearchResult]:
    """
    执行单次 REST API 搜索请求

    Args:
        keyword: 搜索关键词
        limit: 结果数量限制
        search_type: 搜索类型（1=歌曲, 1009=电台/DJ节目）

    Returns:
        list[SearchResult]: 搜索结果列表，失败返回空列表
    """
    import ssl
    import http.client

    try:
        logger.info(f"[NetEase-REST] Searching: {keyword} (type={search_type})")

        params = urlencode({
            's': keyword,
            'type': search_type,
            'offset': 0,
            'total': 'true',
            'limit': limit
        })
        path = f'/api/search/get/web?{params}'

        ctx = ssl.create_default_context()
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2

        conn = http.client.HTTPSConnection(
            'music.163.com',
            timeout=15,
            context=ctx,
        )

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://music.163.com/',
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
        }

        cookie = _login_netease_guest()
        if cookie:
            headers['Cookie'] = cookie

        conn.request('GET', path, headers=headers)
        response = conn.getresponse()
        status = response.status
        raw_data = response.read().decode('utf-8')
        conn.close()

        if status != 200:
            error_msg = ""
            try:
                error_data = json.loads(raw_data)
                error_msg = error_data.get('msg', '')
            except:
                pass

            if status == 405 and "频繁" in error_msg:
                logger.warning(
                    f"[NetEase-REST] Rate limited (405) for '{keyword}', will retry..."
                )
                _rate_limiter.on_rate_limited()
                return []
            else:
                logger.warning(f"[NetEase-REST] HTTP {status} for '{keyword}': {error_msg}")
                return []

        data = json.loads(raw_data)

        if not data or 'result' not in data:
            logger.warning(
                f"[NetEase-REST] No 'result' key for '{keyword}', "
                f"code={data.get('code')}, msg={data.get('msg', '')[:50]}"
            )
            return []

        result_data = data['result']

        if search_type == 1009:
            radios = result_data.get('djRadios', [])
            if not radios:
                logger.warning(f"[NetEase-REST] Empty radios for '{keyword}'")
                return []

            logger.info(f"[NetEase-REST] Found {len(radios)} radios for '{keyword}'")
            parsed = [_parse_netease_radio_result(radio) for radio in radios[:limit]]
            return parsed

        else:
            songs = result_data.get('songs', [])
            if not songs:
                logger.warning(f"[NetEase-REST] Empty songs for '{keyword}'")
                return []

            logger.info(f"[NetEase-REST] Found {len(songs)} songs for '{keyword}'")
            parsed = [_parse_netease_result(song) for song in songs[:limit]]

            if parsed:
                if _netease_cookie:
                    logger.info("[NetEase-REST] Using cookie for cover fetch")

                for i, result in enumerate(parsed):
                    cover_url = _get_netease_cover_by_id(result.song_id, _netease_cookie)
                    if cover_url:
                        logger.debug(f"[NetEase-REST] Got cover for result {i}: {cover_url[:80]}...")
                        parsed[i] = SearchResult(
                            source=result.source,
                            title=result.title,
                            artist=result.artist,
                            album=result.album,
                            cover_link=cover_url,
                            song_id=result.song_id,
                            duration=result.duration,
                            confidence=result.confidence,
                            raw_data=result.raw_data,
                        )
                    else:
                        logger.warning(f"[NetEase-REST] Failed to get cover for result {i}")

            return parsed

    except Exception as e:
        logger.error(f"[NetEase-REST] Error: {e}", exc_info=True)
        return []


def _do_radio_search(keyword: str, limit: int) -> list[SearchResult]:
    """
    搜索网易云音乐电台/声音内容（type=1009）

    专门用于搜索 DJ 电台、播客、声音等非音乐类内容。

    Args:
        keyword: 搜索关键词
        limit: 结果数量限制

    Returns:
        list[SearchResult]: 电台搜索结果列表
    """
    return _do_single_search(keyword, limit, search_type=1009)


def _do_qqmusic_search(keyword: str, limit: int = 5, cookie: str = "") -> list[SearchResult]:
    """
    执行 QQ 音乐搜索的同步 HTTP 请求

    使用 QQ 音乐统一网关接口 (u.y.qq.com/cgi-bin/musicu.fcg)，
    通过 POST 请求发送 JSON 格式的搜索参数。

    API 接口: POST https://u.y.qq.com/cgi-bin/musicu.fcg

    Args:
        keyword: 搜索关键词
        limit: 返回结果数量限制（默认5）
        cookie: QQ音乐用户Cookie字符串（可选）

    Returns:
        list[SearchResult]: QQ 音乐搜索结果列表，失败返回空列表
    """
    import http.client
    from auto_tag.utils.validation import mask_cookie_for_logging

    try:
        log_cookie_info = f", Cookie: {mask_cookie_for_logging(cookie)}" if cookie else ""
        logger.info(f"[QQMusic] Searching: {keyword} (limit={limit}{log_cookie_info})")

        request_body = json.dumps({
            "comm": {"ct": 24, "cv": 1000000},
            "search": {
                "method": "DoSearchForQQMusicLite",
                "module": "music.search.SearchCgiService",
                "param": {
                    "query": keyword,
                    "page_num": 1,
                    "num_per_page": limit,
                    "search_type": 0,
                }
            }
        }, ensure_ascii=False).encode('utf-8')

        conn = http.client.HTTPSConnection('u.y.qq.com', timeout=10)

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://y.qq.com/',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }

        if cookie and cookie.strip():
            headers['Cookie'] = cookie.strip()

        conn.request('POST', '/cgi-bin/musicu.fcg', body=request_body, headers=headers)
        response = conn.getresponse()
        status = response.status
        raw_data = response.read().decode('utf-8')
        conn.close()

        if status != 200:
            logger.warning(f"[QQMusic] HTTP {status} for '{keyword}'")
            return []

        data = json.loads(raw_data)

        if not data or data.get('code') != 0:
            error_msg = data.get('msg', 'Unknown error') if data else 'Empty response'
            logger.warning(f"[QQMusic] API error for '{keyword}': {error_msg} (code={data.get('code') if data else 'N/A'})")
            return []

        search_obj = data.get('search', {})
        data_obj = search_obj.get('data', {})
        body = data_obj.get('body', {})
        songs = body.get('item_song', [])

        meta = data_obj.get('meta', {})
        estimate_sum = meta.get('estimate_sum', 0)

        if not songs:
            if estimate_sum > 0:
                logger.warning(
                    f"[QQMusic] API returned {estimate_sum} estimated results "
                    f"but song list is empty for '{keyword}'. "
                    f"This may indicate API authentication or parameter issues."
                )
            else:
                logger.warning(f"[QQMusic] No results found for '{keyword}'")
            return []

        logger.info(f"[QQMusic] Found {len(songs)} songs (estimated: {estimate_sum}) for '{keyword}'")

        parsed = [_parse_qqmusic_result(song) for song in songs[:limit]]
        logger.info(f"[QQMusic] Parsed {len(parsed)} results")
        return parsed

    except json.JSONDecodeError as e:
        logger.error(f"[QQMusic] JSON decode error: {e}")
        return []
    except Exception as e:
        logger.error(f"[QQMusic] Search error: {e}", exc_info=True)
        return []


def _extract_response_data(response) -> dict | None:
    """
    从API响应中提取数据

    pymusiclibrary 的 API 返回 Response 对象，
    需要从 .data 或 .body 属性提取实际数据。

    Args:
        response: API 响应对象

    Returns:
        dict | None: 提取的数据字典，失败返回None
    """
    if response is None:
        return None

    if hasattr(response, 'data') and response.data is not None:
        return response.data if isinstance(response.data, dict) else None

    if hasattr(response, 'body') and response.body is not None:
        return response.body if isinstance(response.body, dict) else None

    if isinstance(response, dict):
        return response

    return None


async def _search_netease(keyword: str, limit: int = 5) -> list[SearchResult]:
    """
    异步搜索网易云音乐（全局单例模式）

    使用预初始化的全局单例 API 实例，
    与旧版本表格布局保持一致。

    Args:
        keyword: 搜索关键词
        limit: 返回结果数量

    Returns:
        list[SearchResult]: 搜索结果列表
    """
    try:
        def _do_search() -> list[SearchResult]:
            try:
                current_thread_name = threading.current_thread().name
                logger.info(f"[NetEase] Getting API for thread: {current_thread_name}")

                api = get_netease_api()
                if api is None:
                    logger.warning(f"[NetEase] API not available in thread '{current_thread_name}' - search skipped")
                    return []

                logger.info(f"[NetEase] Searching: {keyword}")
                response = api.search(keyword, limit=limit)

                logger.info(f"[NetEase] Response type: {type(response).__name__}, dir: {[a for a in dir(response) if not a.startswith('_')]}")
                if hasattr(response, 'data'):
                    logger.info(f"[NetEase] response.data type: {type(response.data)}, keys: {list(response.data.keys()) if isinstance(response.data, dict) else 'N/A'}")
                elif hasattr(response, 'body'):
                    logger.info(f"[NetEase] response.body type: {type(response.body)}, keys: {list(response.body.keys()) if isinstance(response.body, dict) else 'N/A'}")
                elif hasattr(response, 'status_code'):
                    logger.info(f"[NetEase] response.status_code: {response.status_code}")

                result = _extract_response_data(response)
                logger.info(f"[NetEase] Extracted data: {'keys=' + str(list(result.keys())) if result else 'None'}")

                if not result:
                    logger.warning(f"[NetEase] No response data for: {keyword}")
                    return []

                if "result" not in result:
                    logger.warning(f"[NetEase] No 'result' key in response for: {keyword}, keys={list(result.keys())}")
                    return []

                songs = result["result"].get("songs", [])
                logger.info(f"[NetEase] Found {len(songs)} songs for: {keyword}")

                if not songs:
                    logger.warning(f"[NetEase] Empty songs list for: {keyword}")
                    return []

                parsed = [_parse_netease_result(song) for song in songs[:limit]]
                logger.info(f"[NetEase] Parsed {len(parsed)} results")
                return parsed

            except OSError as e:
                logger.error(f"[NetEase] Native library init failed: {e}")
                return []
            except Exception as e:
                logger.error(f"[NetEase] Search error: {e}", exc_info=True)
                return []

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _do_search)
    except RuntimeError:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_do_search)
            return future.result(timeout=30)
    except Exception as e:
        logger.error(f"[NetEase] Async error: {e}", exc_info=True)
        return []


async def _search_kugou(keyword: str, limit: int = 5) -> list[SearchResult]:
    """
    异步搜索酷狗音乐（全局单例模式）

    使用预初始化的全局单例 API 实例，
    与旧版本表格布局保持一致。

    Args:
        keyword: 搜索关键词
        limit: 返回结果数量

    Returns:
        list[SearchResult]: 搜索结果列表
    """
    try:
        def _do_search_kugou() -> list[SearchResult]:
            try:
                api = get_kugou_api()
                if api is None:
                    logger.warning("[KuGou] API not available")
                    return []

                logger.info(f"[KuGou] Searching: {keyword}")
                response = api.search(keyword)
                result = _extract_response_data(response)

                if not result:
                    logger.warning(f"[KuGou] No response data for: {keyword}")
                    return []

                if "data" not in result:
                    logger.warning(f"[KuGou] No 'data' key in response for: {keyword}, keys={list(result.keys())}")
                    return []

                songs = result["data"].get("lists", []) if isinstance(result["data"], dict) else []
                logger.info(f"[KuGou] Found {len(songs)} songs for: {keyword}")

                if not songs:
                    logger.warning(f"[KuGou] Empty songs list for: {keyword}")
                    return []

                parsed = [_parse_kugou_result(song) for song in songs[:limit]]
                logger.info(f"[KuGou] Parsed {len(parsed)} results")
                return parsed

            except OSError as e:
                logger.error(f"[KuGou] Native library init failed: {e}")
                return []
            except Exception as e:
                logger.error(f"[KuGou] Search error: {e}", exc_info=True)
                return []

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _do_search_kugou)
    except RuntimeError:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_do_search_kugou)
            return future.result(timeout=30)
    except Exception as e:
        logger.error(f"[KuGou] Async error: {e}", exc_info=True)
        return []


async def _search_qqmusic(
    keyword: str,
    limit: int = 5,
    max_retries: int = 3,
    fingerprint_engine: str = "none",
) -> list[SearchResult]:
    """
    异步搜索 QQ 音乐（REST API 模式）

    使用 http.client 直接发起 HTTP 请求到 QQ 音乐搜索 API，
    通过 asyncio.run_in_executor 包装同步函数实现异步调用。

    API 接口: POST https://u.y.qq.com/cgi-bin/musicu.fcg

    Args:
        keyword: 搜索关键词
        limit: 返回结果数量上限（默认5）
        max_retries: 最大重试次数（默认3）
        fingerprint_engine: 音频指纹识别引擎来源

    Returns:
        list[SearchResult]: QQ 音乐搜索结果列表，失败返回空列表
    """
    from auto_tag.gui.config import config as app_config
    cookie = app_config.qq_music_cookie

    try:
        def _do_search() -> list[SearchResult]:
            results = _do_qqmusic_search(keyword, limit, cookie=cookie)
            for r in results:
                r.fingerprint_engine = fingerprint_engine
            return results

        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(None, _do_search)

        if results:
            logger.info(f"[QQMusic] Found {len(results)} results for '{keyword}'")
        else:
            logger.warning(f"[QQMusic] No results for '{keyword}'")

        return results

    except RuntimeError:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_do_qqmusic_search, keyword, limit, cookie)
            try:
                results = future.result(timeout=30)
                if results:
                    logger.info(f"[QQMusic] Found {len(results)} results for '{keyword}' (ThreadPoolExecutor)")
                else:
                    logger.warning(f"[QQMusic] No results for '{keyword}' (ThreadPoolExecutor)")
                return results
            except Exception as e:
                logger.error(f"[QQMusic] ThreadPoolExecutor error: {e}", exc_info=True)
                return []

    except Exception as e:
        logger.error(f"[QQMusic] Async search error: {e}", exc_info=True)
        return []


async def multi_source_search(
    keyword: str,
    shazam_result: dict | None = None,
    limit: int = 5,
    sources: list[str] | None = None,
    include_radio: bool = True,
    fingerprint_engine: str = "none",
) -> list[SearchResult]:
    """
    多数据源并发搜索音乐信息

    根据 sources 参数选择要搜索的平台，
    将结果汇总并按置信度排序。

    Args:
        keyword: 搜索关键词
        shazam_result: 已有的 Shazam 识别结果（如果有）
        limit: 每个平台返回的最大结果数
        sources: 要搜索的源列表，默认 ["shazam", "netease"]
        include_radio: 是否包含电台/声音内容（仅 netease 生效），默认 True
        fingerprint_engine: 音频指纹识别引擎来源

    Returns:
        list[SearchResult]: 所有平台的搜索结果，按置信度降序排列
    """
    all_results: list[SearchResult] = []
    logger.info(f"[MultiSource] Starting search with keyword: {keyword}, sources: {sources}, fingerprint_engine: {fingerprint_engine}")

    if sources is None:
        sources = ["shazam", "netease"]

    if shazam_result and "track" in shazam_result:
        try:
            source = shazam_result.get("source", "shazam")
            shazam_result_obj = _parse_shazam_result(shazam_result["track"])
            shazam_result_obj.source = source
            all_results.append(shazam_result_obj)
            logger.info(
                f"[MultiSource] Fingerprint result ({source}) added: "
                f"{shazam_result_obj.title} - {shazam_result_obj.artist}"
            )
        except Exception as e:
            logger.error(f"[MultiSource] Failed to parse fingerprint result: {e}", exc_info=True)

    search_tasks = []

    if "netease" in sources:
        logger.info("[MultiSource] Using pure REST API for NetEase")
        search_tasks.append(asyncio.create_task(_search_netease_rest(
            keyword, limit, include_radio=include_radio, fingerprint_engine=fingerprint_engine
        )))
    else:
        logger.info("[MultiSource] NetEase not in sources, skipping")

    if "qqmusic" in sources:
        logger.info("[MultiSource] Using REST API for QQ Music")
        search_tasks.append(asyncio.create_task(_search_qqmusic(keyword, limit, fingerprint_engine=fingerprint_engine)))

    if "kugou" in sources:
        logger.info("[MultiSource] KuGou Music temporarily disabled (no stable REST API available)")

    if not search_tasks:
        logger.info("[MultiSource] No async search tasks to run")
        all_results.sort(key=lambda x: x.confidence, reverse=True)
        return all_results

    task_results = await asyncio.gather(*search_tasks, return_exceptions=True)

    for task_result in task_results:
        if isinstance(task_result, Exception):
            logger.error(f"[MultiSource] Search exception: {task_result}", exc_info=True)
        elif isinstance(task_result, list):
            logger.info(f"[MultiSource] Source returned {len(task_result)} results")
            all_results.extend(task_result)
        else:
            logger.warning(f"[MultiSource] Unexpected result type: {type(task_result)}")

    all_results.sort(key=lambda x: x.confidence, reverse=True)

    logger.info(f"[MultiSource] Total results: {len(all_results)}")
    for r in all_results:
        logger.info(f"  - [{r.source}] {r.title} - {r.artist}")

    return all_results
