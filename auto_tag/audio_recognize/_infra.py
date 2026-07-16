# auto_tag/audio_recognize/_infra.py
"""
Infrastructure module: MusicLibrary initialization, API singleton management,
monkey patching for pymusiclibrary bug fixes.

This module is the foundation layer with no internal package dependencies.
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

# 全局 API 实例缓存（单例模式 - 主线程使用）
# 重要：pymusiclibrary 原生 C 库只能初始化一次，重复创建会导致 access violation！
_netease_api = None
_kugou_api = None
_initialized = False

# 线程本地存储（子线程使用 - 每个线程独立实例）
_thread_local = threading.local()

# Monkey Patch 标志（确保只执行一次）
_monkey_patch_applied = False


def _apply_monkey_patch():
    """
    应用 Monkey Patch 修复 pymusiclibrary 库的 Bug

    修复问题：
    1. NeteaseCloudMusicApi.__init__ 失败时没有设置 _destroyed 属性
    2. KuGouMusicApi.__init__ 失败时没有设置 _destroyed 属性
    3. __del__ 方法尝试访问 _destroyed 导致 AttributeError
    """
    global _monkey_patch_applied

    if _monkey_patch_applied:
        return

    try:
        from MusicLibrary import neteaseCloudMusicApi, kuGouMusicApi

        _original_netease_init = neteaseCloudMusicApi.NeteaseCloudMusicApi.__init__
        _original_kugou_init = kuGouMusicApi.KuGouMusicApi.__init__

        def _patched_netease_init(self, *args, **kwargs):
            self._destroyed = True
            try:
                _original_netease_init(self, *args, **kwargs)
                self._destroyed = False
            except Exception as e:
                logger.debug(f"[Patch] NetEase API init failed: {e}")
                raise

        def _patched_kugou_init(self, *args, **kwargs):
            self._destroyed = True
            try:
                _original_kugou_init(self, *args, **kwargs)
                self._destroyed = False
            except Exception as e:
                logger.debug(f"[Patch] KuGou API init failed: {e}")
                raise

        neteaseCloudMusicApi.NeteaseCloudMusicApi.__init__ = _patched_netease_init
        kuGouMusicApi.KuGouMusicApi.__init__ = _patched_kugou_init
        _monkey_patch_applied = True
        logger.info("[MusicLibrary] Monkey patch applied successfully")

    except ImportError:
        logger.debug("[MusicLibrary] pymusiclibrary not available for patching")
    except Exception as e:
        logger.warning(f"[MusicLibrary] Failed to apply monkey patch: {e}")


def initialize_music_library():
    """
    在主线程预初始化 MusicLibrary API 实例（全局单例）

    此函数应该在应用启动时调用（在 GUI 主线程中）。
    只创建一次实例，后续所有搜索复用该实例。

    重要：pymusiclibrary 原生 C 库只能初始化一次，
    重复创建实例会导致 access violation 崩溃！
    """
    global _netease_api, _kugou_api, _initialized

    if _initialized:
        return

    _apply_monkey_patch()

    try:
        from MusicLibrary.neteaseCloudMusicApi import NeteaseCloudMusicApi
        try:
            _netease_api = NeteaseCloudMusicApi()
            logger.info("[MusicLibrary] NetEase API initialized (global singleton)")
        except Exception as e:
            logger.warning(f"[MusicLibrary] NetEase API init failed: {e}")
            _netease_api = None
    except ImportError as e:
        logger.debug(f"[MusicLibrary] pymusiclibrary not available: {e}")
        _netease_api = None

    try:
        from MusicLibrary.kuGouMusicApi import KuGouMusicApi
        try:
            _kugou_api = KuGouMusicApi()
            logger.info("[MusicLibrary] KuGou API initialized (global singleton)")
        except Exception as e:
            logger.warning(f"[MusicLibrary] KuGou API init failed: {e}")
            _kugou_api = None
    except ImportError as e:
        logger.debug(f"[MusicLibrary] pymusiclibrary not available: {e}")
        _kugou_api = None

    _initialized = True


def get_netease_api():
    """
    获取 NetEase API 实例（智能模式）

    智能判断当前线程：
    - 主线程：返回全局单例（启动时预初始化）
    - 子线程：返回该线程的独立实例（避免跨线程访问崩溃）

    Returns:
        NeteaseCloudMusicApi or None: API 实例或 None
    """
    current_thread = threading.current_thread()
    thread_name = current_thread.name

    # 主线程：使用全局单例
    if thread_name == 'MainThread':
        if not _initialized:
            logger.warning(f"[MusicLibrary][{thread_name}] API not initialized, call initialize_music_library() first")
            return None
        if _netease_api is None:
            logger.warning(f"[MusicLibrary][{thread_name}] Global NetEase API is None (init failed?)")
            return None
        return _netease_api

    # 子线程：使用线程本地实例（每线程只创建一次）
    if hasattr(_thread_local, 'netease_api'):
        api = _thread_local.netease_api
        if api is not None:
            return api
        else:
            logger.warning(f"[MusicLibrary][{thread_name}] Thread-local NetEase API was set to None (previous init failed)")

    logger.info(f"[MusicLibrary][{thread_name}] Creating new NetEase API instance for this thread...")
    try:
        _apply_monkey_patch()
        from MusicLibrary.neteaseCloudMusicApi import NeteaseCloudMusicApi
        api = NeteaseCloudMusicApi()
        _thread_local.netease_api = api
        logger.info(f"[MusicLibrary][{thread_name}] ✅ NetEase API created successfully!")
        return api
    except Exception as e:
        error_msg = str(e)
        logger.error(f"[MusicLibrary][{thread_name}] ❌ Failed to create NetEase API: {error_msg}")
        if "access violation" in error_msg.lower() or "0x" in error_msg.lower():
            logger.error(f"[MusicLibrary][{thread_name}] ⚠️ This is a native library crash (QuickJS engine)")
        _thread_local.netease_api = None
        return None


def get_kugou_api():
    """
    获取 KuGou API 实例（智能模式）

    智能判断当前线程：
    - 主线程：返回全局单例（启动时预初始化）
    - 子线程：返回该线程的独立实例（避免跨线程访问崩溃）

    Returns:
        KuGouMusicApi or None: API 实例或 None
    """
    current_thread = threading.current_thread()
    thread_name = current_thread.name

    # 主线程：使用全局单例
    if thread_name == 'MainThread':
        if not _initialized:
            logger.warning(f"[MusicLibrary][{thread_name}] API not initialized, call initialize_music_library() first")
            return None
        if _kugou_api is None:
            logger.warning(f"[MusicLibrary][{thread_name}] Global KuGou API is None (init failed?)")
            return None
        return _kugou_api

    # 子线程：使用线程本地实例（每线程只创建一次）
    if hasattr(_thread_local, 'kugou_api'):
        api = _thread_local.kugou_api
        if api is not None:
            return api
        else:
            logger.warning(f"[MusicLibrary][{thread_name}] Thread-local KuGou API was set to None (previous init failed)")

    logger.info(f"[MusicLibrary][{thread_name}] Creating new KuGou API instance for this thread...")
    try:
        _apply_monkey_patch()
        from MusicLibrary.kuGouMusicApi import KuGouMusicApi
        api = KuGouMusicApi()
        _thread_local.kugou_api = api
        logger.info(f"[MusicLibrary][{thread_name}] ✅ KuGou API created successfully!")
        return api
    except Exception as e:
        error_msg = str(e)
        logger.error(f"[MusicLibrary][{thread_name}] ❌ Failed to create KuGou API: {error_msg}")
        if "access violation" in error_msg.lower() or "0x" in error_msg.lower():
            logger.error(f"[MusicLibrary][{thread_name}] ⚠️ This is a native library crash (QuickJS engine)")
        _thread_local.kugou_api = None
        return None


def is_music_library_available() -> bool:
    """
    检查 MusicLibrary 是否可用

    Returns:
        bool: 是否已初始化且至少有一个 API 可用
    """
    # 主线程检查全局状态
    if threading.current_thread().name == 'MainThread':
        return _initialized and (_netease_api is not None or _kugou_api is not None)

    # 子线程检查线程本地状态
    has_netease = hasattr(_thread_local, 'netease_api') and _thread_local.netease_api is not None
    has_kugou = hasattr(_thread_local, 'kugou_api') and _thread_local.kugou_api is not None
    return has_netease or has_kugou
