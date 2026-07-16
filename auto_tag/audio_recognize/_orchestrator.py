# auto_tag/audio_recognize/_orchestrator.py
"""
Orchestrator module: top-level recognition pipeline that ties together
fingerprint recognition, metadata extraction, search, and tag writing.

Depends on: all internal modules (_infra, _metadata, _tags, _recognizer, _search)
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
import time

import soundfile as sf
from shazamio import Shazam
from tqdm.asyncio import tqdm

from auto_tag.utils import is_file_in_use_error

from ._metadata import (
    _build_keyword_from_metadata,
    _build_search_keyword_from_filename,
    _build_smart_keyword,
    _is_metadata_valid,
    _is_filename_like_song_name,
    _read_audio_metadata_from_file,
    _safe_filename,
)
from ._recognizer import _is_valid_fingerprint_result, recognize_with_acoustid
from ._search import _flatten_shazam_metadata, multi_source_search
from ._tags import update_mp3_cover_art, update_mp3_tags, update_ogg_tags

logger = logging.getLogger(__name__)


async def find_and_recognize_audio_files(
    folder_path: str,
    *,
    modify: bool = True,
    delay: int = 10,
    nbr_retry: int = 3,
    trace: bool = False,
    extensions: list[str] | tuple[str, ...] = ("mp3", "ogg", "flac", "wav", "m4a", "aac", "wma", "opus"),
    output_dir: str | None = None,
    plex_structure: bool = False,
    copy_to: str | None = None,
    tag_only: bool = False,
) -> None:
    """
    Walk folder_path, recognise each file, then move or copy/tag it.
    - copy_to: if given, base dir to copy files into (instead of moving)
    - tag_only: if True, update tags/cover only on the original file (no rename/move).
    """
    # Safe 模式：API 实例在首次使用时惰性创建，无需预初始化

    exts = {e.lower().lstrip(".") for e in extensions}
    audio_files: list[str] = []
    for root, _, files in os.walk(folder_path):
        if "test" in os.path.basename(root).lower():
            continue
        for fn in files:
            if os.path.splitext(fn)[1].lower().lstrip(".") in exts:
                audio_files.append(os.path.join(root, fn))

    if not audio_files:
        print(f"No files with extensions {exts} found in {folder_path}.")
        return

    shazam = Shazam()
    ok = 0

    for path in tqdm(audio_files, desc="Recognising and renaming"):
        res = await recognize_and_rename_file(
            file_path=path,
            shazam=shazam,
            modify=modify,
            delay=delay,
            nbr_retry=nbr_retry,
            trace=trace,
            output_dir=output_dir,
            plex_structure=plex_structure,
            copy_to=copy_to,
            tag_only=tag_only,
        )
        if "error" in res and trace:
            print(f"[{os.path.basename(path)}] {res['error']}")
        if "error" not in res:
            ok += 1

    print(f"Succeeded {ok}/{len(audio_files)}.")


async def recognize_and_rename_file(
    *,
    file_path: str,
    shazam: Shazam,
    modify: bool,
    delay: int,
    nbr_retry: int,
    trace: bool,
    output_dir: str | None,
    plex_structure: bool,
    copy_to: str | None = None,
    tag_only: bool = False,
) -> dict:
    """
    Recognise file_path with Shazam, then move or copy & tag it.
    Also performs multi-source search (NetEase, KuGou) for additional results.
    - If tag_only is True, only update metadata on the original file_path.
    - Else if copy_to is set, copy; otherwise rename/move.
    """
    ext = os.path.splitext(file_path)[1].lower()
    tmp_wav: str | None = None

    # 1) For OGG, attempt WAV conversion for recognition
    input_path = file_path
    if ext == ".ogg":
        fd, tmp_wav = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            data, sr = sf.read(file_path, dtype="int16")
            sf.write(tmp_wav, data, sr, subtype="PCM_16")
            input_path = tmp_wav
        except Exception as exc:
            if trace:
                print(f"[{os.path.basename(file_path)}] OGG→WAV failed: {exc}")
            input_path = file_path

    # 2) 判断文件名是否像歌曲名，决定搜索策略
    filename_is_song_like = _is_filename_like_song_name(file_path)

    # 3) 读取用户配置的识别引擎（从设置页面的搜索源获取）
    try:
        from auto_tag.gui.config import config
        enabled_sources = config.search_sources
        ascii_only = config.ascii_only_filenames if config else False
    except Exception:
        enabled_sources = ["acoustid", "shazam"]
        ascii_only = False

    # 分离音频指纹引擎和关键词搜索平台
    fingerprint_engines = [s for s in enabled_sources if s in ("acoustid", "shazam")]
    keyword_platforms = [s for s in enabled_sources if s in ("netease", "kugou", "qqmusic")]

    logger.info(
        f"[Strategy] Engines: {fingerprint_engines}, Keywords: {keyword_platforms}: {file_path}"
    )

    out = None
    recognition_source = None

    # === 按配置顺序执行音频指纹识别引擎 ===
    for engine in fingerprint_engines:
        if out is not None and "track" in (out or {}):
            break

        if engine == "acoustid":
            logger.info(f"[Engine/Acoustid] Trying audio fingerprint recognition...")
            try:
                acoustid_result = await recognize_with_acoustid(file_path, trace=trace)
                if acoustid_result and "track" in acoustid_result:
                    out = acoustid_result
                    recognition_source = "acoustid"
                    if trace:
                        track = acoustid_result["track"]
                        print(f"[Acoustid] Success! Found: {track.get('title')} - {track.get('subtitle')}")
            except Exception as acoustid_error:
                logger.warning(f"[Engine/Acoustid] Failed: {acoustid_error}")
                if trace:
                    print(f"[Acoustid] Error: {acoustid_error}")

        elif engine == "shazam":
            logger.info(f"[Engine/Shazam] Trying Shazam recognition...")
            for attempt in range(1, nbr_retry + 1):
                try:
                    candidate = await shazam.recognize(input_path)
                    if candidate:
                        out = candidate
                        recognition_source = "shazam"
                        break
                except Exception as exc:
                    if trace:
                        print(f"[{os.path.basename(file_path)}] Shazam attempt {attempt}: {exc}")
                if attempt < nbr_retry:
                    await asyncio.sleep(delay)

            # Fallback to original OGG if WAV recognition failed
            if (out is None or "track" not in (out or {})) and ext == ".ogg" and input_path != file_path:
                for attempt in range(1, nbr_retry + 1):
                    try:
                        candidate = await shazam.recognize(file_path)
                        if candidate:
                            out = candidate
                            recognition_source = "shazam"
                            break
                    except Exception as exc:
                        if trace:
                            print(f"[{os.path.basename(file_path)}] Shazam OGG fallback {attempt}: {exc}")
                    if attempt < nbr_retry:
                        await asyncio.sleep(delay)

    # cleanup temp WAV
    if tmp_wav and os.path.exists(tmp_wav):
        os.remove(tmp_wav)

    # === 新逻辑：检查指纹识别结果是否有效 ===
    fingerprint_is_valid = _is_valid_fingerprint_result(out)

    if not fingerprint_is_valid:
        if out and "track" in out:
            track = out["track"]
            title = track.get("title", "Unknown")
            artist = track.get("subtitle", "Unknown")
            logger.warning(
                f"[Fingerprint] ⚠ Fingerprint recognized but INVALID metadata: "
                f"title='{title}', artist='{artist}' → Will use keyword search instead"
            )
            if trace:
                print(f"[Fingerprint] Found but invalid: {title} - {artist}")
                print(f"[Fingerprint] Falling back to keyword search...")
        elif trace:
            print(f"All engines failed: {file_path}, attempting keyword fallback...")

        # 备选方案：智能关键词搜索（集成中英文分离）
        if filename_is_song_like:
            from auto_tag.utils import split_multilingual_text, is_multilingual_text

            raw_keyword = _build_search_keyword_from_filename(file_path)

            if raw_keyword:
                if is_multilingual_text(raw_keyword):
                    split_result = split_multilingual_text(raw_keyword)
                    if split_result['has_both'] and split_result['native']:
                        fallback_keyword = split_result['native']
                        logger.warning(
                            f"[Fallback] ★ Multi-language text detected! Using Native keyword: '{fallback_keyword}' "
                            f"(original: '{raw_keyword}')"
                        )
                    else:
                        fallback_keyword = raw_keyword
                else:
                    fallback_keyword = raw_keyword

                logger.info(f"[Fallback] Trying keyword search: {fallback_keyword}")
                try:
                    from auto_tag.gui.config import config
                    fallback_results = await multi_source_search(
                        keyword=fallback_keyword,
                        shazam_result=None,
                        limit=5,
                        sources=config.search_sources,
                        include_radio=config.include_radio,
                        fingerprint_engine="filename",
                    )

                    if fallback_results:
                        best_match = fallback_results[0]
                        s_title = _safe_filename(best_match.title, ascii_only)
                        s_artist = _safe_filename(best_match.artist, ascii_only)
                        s_album = _safe_filename(best_match.album, ascii_only)

                        logger.info(
                            f"[Fallback] Success! Found: {best_match.title} - {best_match.artist}"
                        )

                        return {
                            "file_path": file_path,
                            "new_file_path": file_path,
                            "title": s_title,
                            "author": s_artist,
                            "album": s_album,
                            "cover_link": best_match.cover_link,
                            "search_results": [sr.to_dict() for sr in fallback_results],
                        }
                    else:
                        logger.warning(f"[Fallback] No results for keyword: {fallback_keyword}")
                except Exception as fallback_error:
                    logger.error(f"[Fallback] Search failed: {fallback_error}", exc_info=True)
        else:
            logger.info(f"[MetadataFallback] Trying to read metadata tags from file: {file_path}")
            file_metadata = _read_audio_metadata_from_file(file_path)

            if _is_metadata_valid(file_metadata):
                fallback_keyword = _build_keyword_from_metadata(file_metadata)
                logger.info(f"[MetadataFallback] Found valid metadata, searching with: '{fallback_keyword}'")

                try:
                    from auto_tag.gui.config import config
                    fallback_results = await multi_source_search(
                        keyword=fallback_keyword,
                        shazam_result=None,
                        limit=5,
                        sources=config.search_sources,
                        include_radio=config.include_radio,
                        fingerprint_engine="metadata",
                    )

                    if fallback_results:
                        best_match = fallback_results[0]
                        s_title = _safe_filename(best_match.title, ascii_only)
                        s_artist = _safe_filename(best_match.artist, ascii_only)
                        s_album = _safe_filename(best_match.album, ascii_only)

                        logger.info(
                            f"[MetadataFallback] Success! Found: {best_match.title} - {best_match.artist}"
                        )

                        return {
                            "file_path": file_path,
                            "new_file_path": file_path,
                            "title": s_title,
                            "author": s_artist,
                            "album": s_album,
                            "cover_link": best_match.cover_link,
                            "search_results": [sr.to_dict() for sr in fallback_results],
                        }
                    else:
                        logger.warning(
                            f"[MetadataFallback] No search results for metadata keyword: '{fallback_keyword}'"
                        )
                except Exception as fallback_error:
                    logger.error(
                        f"[MetadataFallback] Search failed: {fallback_error}", exc_info=True
                    )
            else:
                logger.warning(
                    f"[MetadataFallback] No valid metadata tags found in file: {file_path}"
                )

        return {
            "file_path": file_path,
            "error": "Recognition failed",
            "search_results": [],
        }

    # 3) Extract & sanitize metadata
    track = out["track"]
    title = track.get("title", "Unknown Title")
    artist = track.get("subtitle", "Unknown Artist")

    # 使用标准化函数提取嵌套元数据（替代旧版 find_deepest_metadata_key）
    flat_meta = _flatten_shazam_metadata(track)
    album = flat_meta.get("album", "Unknown Album")
    cover = track.get("images", {}).get("coverart", "")

    ascii_only = config.ascii_only_filenames if config else False
    s_title = _safe_filename(title, ascii_only)
    s_artist = _safe_filename(artist, ascii_only)
    s_album = _safe_filename(album, ascii_only)

    # 3.5) Multi-source search: 根据配置构建关键词（支持智能回退）
    from auto_tag.gui.config import config

    primary_keyword, alternative_keywords = _build_smart_keyword(
        file_path=file_path,
        title=title,
        artist=artist,
        mode=config.search_keyword_mode,
    )

    search_results = await multi_source_search(
        keyword=primary_keyword,
        shazam_result=out,
        limit=3,
        sources=config.search_sources,
        include_radio=config.include_radio,
        fingerprint_engine=recognition_source or "none",
    )

    if not search_results and alternative_keywords:
        for alt_kw in alternative_keywords[:3]:
            logger.info(
                f"[SmartKeyword] Primary keyword '{primary_keyword}' failed, "
                f"trying alternative: '{alt_kw}'"
            )
            alt_results = await multi_source_search(
                keyword=alt_kw,
                shazam_result=out,
                limit=3,
                sources=config.search_sources,
                include_radio=config.include_radio,
                fingerprint_engine=recognition_source or "none",
            )
            if alt_results:
                logger.info(
                    f"[SmartKeyword] Alternative keyword '{alt_kw}' succeeded "
                    f"with {len(alt_results)} results"
                )
                search_results = alt_results
                break

    # 4) Build final name (if renaming)
    if plex_structure:
        new_name = f"{s_title}{ext}"
    else:
        new_name = f"{s_title} - {s_artist} - {s_album}{ext}"

    # 5) Determine target directory
    root_dir = copy_to or output_dir or os.path.dirname(file_path)
    if plex_structure:
        root_dir = os.path.join(root_dir, s_artist, s_album)
    os.makedirs(root_dir, exist_ok=True)

    # 6) Unique filename
    new_path = os.path.join(root_dir, new_name)
    count = 1
    while os.path.exists(new_path) and new_path != file_path:
        stem, e2 = os.path.splitext(new_path)
        new_path = f"{stem} ({count}){e2}"
        count += 1

    # 7) Tag-only branch: update tags on original file
    if tag_only and modify:
        try:
            if ext == ".mp3":
                update_mp3_tags(file_path, s_title, s_artist, s_album)
                if cover:
                    update_mp3_cover_art(file_path, cover, trace)
            else:
                update_ogg_tags(
                    file_path, s_title, s_artist, s_album, cover, trace
                )
        except Exception as exc:
            return {
                "file_path": file_path,
                "error": f"Tag error: {exc}",
                "search_results": [sr.to_dict() for sr in search_results],
            }
        return {
            "file_path": file_path,
            "new_file_path": file_path,
            "title": s_title,
            "author": s_artist,
            "album": s_album,
            "cover_link": cover,
            "search_results": [sr.to_dict() for sr in search_results],
        }

    # 8) Move or copy & tag
    if modify and not tag_only:
        max_retries = 3
        retry_delay = 0.5
        for attempt in range(max_retries + 1):
            try:
                if copy_to:
                    shutil.copy2(file_path, new_path)
                else:
                    os.rename(file_path, new_path)

                if ext == ".mp3":
                    update_mp3_tags(new_path, s_title, s_artist, s_album)
                    if cover:
                        update_mp3_cover_art(new_path, cover, trace)
                else:
                    update_ogg_tags(
                        new_path, s_title, s_artist, s_album, cover, trace
                    )
                break
            except Exception as exc:
                if is_file_in_use_error(exc) and attempt < max_retries:
                    wait_time = retry_delay * (attempt + 1)
                    logger.warning(
                        f"文件被占用，将在 {wait_time:.1f} 秒后重试 "
                        f"({attempt + 1}/{max_retries}): {exc}"
                    )
                    time.sleep(wait_time)
                    continue
                return {
                    "file_path": file_path,
                    "error": f"Tag error: {exc}",
                    "search_results": [sr.to_dict() for sr in search_results],
                }

    return {
        "file_path": file_path,
        "new_file_path": new_path,
        "title": s_title,
        "author": s_artist,
        "album": s_album,
        "cover_link": cover,
        "search_results": [sr.to_dict() for sr in search_results],
        "source": recognition_source or "shazam",
    }
