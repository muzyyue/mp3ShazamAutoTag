# auto_tag/audio_recognize/_recognizer.py
"""
Audio fingerprint recognition module: Acoustid session management,
fingerprint generation, and recognition result validation.

Depends on: nothing internal (self-contained)
"""

from __future__ import annotations

import asyncio
import atexit
import json
import logging
import os
import subprocess
import tempfile
import threading

import aiohttp

logger = logging.getLogger(__name__)

# Acoustid API Key（免费额度：100 次/天）
ACOUSTID_API_KEY = "cSpUJKpD"
ACOUSTID_LOOKUP_URL = "https://api.acoustid.org/v2/lookup"

# 线程局部 aiohttp Session 管理器（避免跨线程事件循环冲突）
# 关键：aiohttp.ClientSession 绑定到特定事件循环，不能跨线程共享
# 使用线程局部存储确保每个线程拥有独立的 session 和事件循环
_acoustid_session_local = threading.local()


async def _get_acoustid_session() -> aiohttp.ClientSession:
    """
    获取或创建当前线程的 Acoustid API aiohttp Session

    使用线程局部存储（threading.local）确保每个线程拥有独立的 session，
    避免跨线程事件循环冲突导致的 RuntimeError: Event loop is closed。

    每个线程的 session 仍会复用连接池以减少 TCP 握手开销。

    Returns:
        aiohttp.ClientSession: 当前线程可用的 HTTP 会话实例
    """
    if not hasattr(_acoustid_session_local, 'session') or _acoustid_session_local.session is None or _acoustid_session_local.session.closed:
        _acoustid_session_local.session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=5, ttl_dns_cache=300),
            timeout=aiohttp.ClientTimeout(total=30)
        )
    return _acoustid_session_local.session


async def _close_acoustid_session() -> None:
    """
    关闭当前线程的 aiohttp Session（用于线程退出时清理资源）
    """
    if hasattr(_acoustid_session_local, 'session') and _acoustid_session_local.session is not None and not _acoustid_session_local.session.closed:
        await _acoustid_session_local.session.close()
        _acoustid_session_local.session = None


def _cleanup_aiohttp_resources():
    """
    程序退出时清理 aiohttp 资源（atexit 回调）

    确保所有线程的 ClientSession 都被正确关闭，
    避免 "Unclosed client session" 和 "Unclosed connector" 警告。
    """
    try:
        if hasattr(_acoustid_session_local, 'session') and _acoustid_session_local.session is not None:
            loop = _acoustid_session_local.session._loop if hasattr(_acoustid_session_local.session, '_loop') else None
            if loop and loop.is_running():
                asyncio.ensure_future(_close_acoustid_session(), loop=loop)
            elif loop and not loop.is_closed():
                loop.run_until_complete(_close_acoustid_session())
            logger.debug("[Cleanup] aiohttp session cleaned up successfully")
    except Exception as e:
        logger.debug(f"[Cleanup] Error cleaning up aiohttp session: {e}")


# 注册退出处理器，确保程序退出时清理 aiohttp 资源
atexit.register(_cleanup_aiohttp_resources)


async def recognize_with_acoustid(file_path: str, trace: bool = False) -> dict | None:
    """
    使用 Acoustid 进行音频识别（备选方案）

    Acoustid 是基于 Chromaprint 音频指纹的开源音乐识别服务。
    当 Shazam 识别失败时，可以尝试使用此方案。

    优化：使用 asyncio.create_subprocess_exec() 替代 subprocess.run()，
    避免在异步函数中阻塞事件循环。

    Args:
        file_path: 音频文件路径
        trace: 是否输出调试信息

    Returns:
        dict | None: 识别结果字典（与 Shazam 格式兼容），失败时返回 None
    """
    from auto_tag.utils.ffmpeg_utils import get_silent_process_kwargs

    try:
        # 检查 ffmpeg 是否可用（使用非阻塞异步方式）
        try:
            kwargs = get_silent_process_kwargs()
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-version",
                **kwargs
            )
            await proc.communicate()
            if proc.returncode != 0:
                raise subprocess.CalledProcessError(proc.returncode, "ffmpeg")
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired, OSError):
            if trace:
                print("[Acoustid] ffmpeg not available, skipping Acoustid recognition")
            logger.info("[Acoustid] ffmpeg not available, skipping")
            return None

        # 使用 ffmpeg 生成 Chromaprint 音频指纹（默认压缩格式，Acoustid API 可直接接受）
        # 注意：必须使用默认格式（无 -fp_format 参数），不能使用 -fp_format 0（原始二进制）
        fd, tmp_fp = tempfile.mkstemp(suffix=".txt")
        os.close(fd)

        try:
            cmd = [
                "ffmpeg", "-y",
                "-i", file_path,
                "-f", "chromaprint",
                tmp_fp,
            ]

            if trace:
                print(f"[Acoustid] Generating fingerprint for: {os.path.basename(file_path)}")

            # 使用非阻塞异步方式执行 ffmpeg（隐藏CMD窗口）
            kwargs = get_silent_process_kwargs()
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                **kwargs
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

            if proc.returncode != 0:
                raise subprocess.CalledProcessError(proc.returncode, cmd)

            with open(tmp_fp, "r", encoding="ascii") as f:
                fingerprint = f.read().strip()
        finally:
            if os.path.exists(tmp_fp):
                os.remove(tmp_fp)

        # 提取时长（从音频文件信息中获取）
        probe_cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            file_path
        ]

        # 使用非阻塞异步方式执行 ffprobe（隐藏CMD窗口）
        kwargs = get_silent_process_kwargs()
        proc = await asyncio.create_subprocess_exec(
            *probe_cmd,
            **kwargs
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)

        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, probe_cmd)

        probe_data = json.loads(stdout.decode('utf-8'))
        duration = int(float(probe_data.get('format', {}).get('duration', 0)))

        if duration == 0:
            duration = 10  # 默认值

        if trace:
            print(f"[Acoustid] Fingerprint generated: duration={duration}s, fp_len={len(fingerprint)}")

        from urllib.parse import urlencode

        body = urlencode({
            'client': ACOUSTID_API_KEY,
            'fingerprint': fingerprint,
            'duration': str(duration),
            'meta': 'recordings releasegroups',
        })

        # 复用全局 aiohttp session（避免每次创建新连接的开销）
        session = await _get_acoustid_session()
        async with session.post(
            ACOUSTID_LOOKUP_URL,
            data=body,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=aiohttp.ClientTimeout(total=30)
        ) as response:
            if response.status != 200:
                if trace:
                    print(f"[Acoustid] API request failed: status={response.status}")
                logger.warning(f"[Acoustid] API request failed: status={response.status}")
                return None

            data = await response.json()

            if trace:
                print(f"[Acoustid] API response: {json.dumps(data, ensure_ascii=False)[:500]}")

            if data.get("status") != "ok" or not data.get("results"):
                if trace:
                    print("[Acoustid] No matching results")
                logger.info("[Acoustid] No matching results")
                return None

            # 解析第一个匹配结果
            result_data = data["results"][0]
            recordings = result_data.get("recordings", [])

            if not recordings:
                if trace:
                    print("[Acoustid] No recordings in result")
                return None

            recording = recordings[0]
            releasegroups = result_data.get("releasegroups", [])
            album_name = releasegroups[0].get("title", "") if releasegroups else ""

            # 返回与 Shazam 格式兼容的结果
            acoustid_result = {
                "track": {
                    "title": recording.get("title", "Unknown Title"),
                    "subtitle": recording.get("artists", [{}])[0].get("name", "Unknown Artist"),
                    "images": {
                        "coverart": ""  # Acoustid 不提供封面
                    },
                    "sections": [],
                },
                "source": "acoustid",
                "acoustid_id": result_data.get("id", ""),
            }

            if trace:
                print(f"[Acoustid] Success: {acoustid_result['track']['title']} - {acoustid_result['track']['subtitle']}")

            return acoustid_result

    except subprocess.TimeoutExpired:
        logger.error("[Acoustid] ffmpeg timeout")
        if trace:
            print("[Acoustid] ffmpeg timeout")
        return None
    except asyncio.TimeoutError:
        logger.error("[Acoustid] ffmpeg/ffprobe timeout")
        if trace:
            print("[Acoustid] ffmpeg/ffprobe timeout")
        return None
    except Exception as e:
        logger.error(f"[Acoustid] Recognition failed: {e}", exc_info=True)
        if trace:
            print(f"[Acoustid] Error: {e}")
        return None


def _is_valid_fingerprint_result(fingerprint_result: dict | None) -> bool:
    """
    检查指纹识别结果是否有效（包含有意义的元数据）

    用于过滤 Acoustid/Shazam 返回的 "Unknown Title" 等无效结果。

    Args:
        fingerprint_result: 指纹识别 API 返回的结果字典

    Returns:
        bool: 如果结果包含有效的 title/artist 信息返回 True，否则返回 False
    """
    if not fingerprint_result or "track" not in fingerprint_result:
        return False

    track = fingerprint_result["track"]

    # 检查 title 是否有效（不是 Unknown/空）
    title = track.get("title", "")
    INVALID_TITLES = {"unknown title", "unknown", "", "n/a", "none"}

    if isinstance(title, str) and title.lower().strip() in INVALID_TITLES:
        logger.debug("[Fingerprint] Invalid result: title is empty/unknown")
        return False

    # 检查是否有至少一个有效字段（title 或 artist）
    artist = track.get("subtitle", "")
    has_valid_title = bool(title and title.lower().strip() not in INVALID_TITLES)
    has_valid_artist = bool(artist and artist.lower().strip() not in INVALID_TITLES)

    is_valid = has_valid_title or has_valid_artist

    if not is_valid:
        logger.debug(
            f"[Fingerprint] Result considered invalid - "
            f"title='{title}', artist='{artist}'"
        )

    return is_valid
