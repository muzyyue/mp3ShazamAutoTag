# auto_tag/audio_recognize/__init__.py
"""
Package re-export facade — replaces the original audio_recognize.py

All functions, classes, and module-level variables that were previously
importable from ``auto_tag.audio_recognize`` are re-exported here so that
existing ``from auto_tag.audio_recognize import ...`` statements continue
to work without modification.
"""

from auto_tag.audio_recognize._infra import (
    _apply_monkey_patch,
    _initialized,
    _kugou_api,
    _monkey_patch_applied,
    _netease_api,
    _thread_local,
    get_kugou_api,
    get_netease_api,
    initialize_music_library,
    is_music_library_available,
)

from auto_tag.audio_recognize._metadata import (
    _build_keyword_from_metadata,
    _build_search_keyword_from_filename,
    _build_smart_keyword,
    _enhanced_extract_song_name,
    _is_filename_like_song_name,
    _is_metadata_valid,
    _read_audio_metadata_from_file,
    _safe_filename,
    read_audio_metadata_mutagen,
)

from auto_tag.audio_recognize._tags import (
    _write_flac_tags,
    _write_generic_tags,
    _write_mp3_tags,
    _write_mp4_tags,
    _write_vorbis_tags,
    update_audio_tags,
    update_mp3_cover_art,
    update_mp3_tags,
    update_ogg_tags,
)

from auto_tag.audio_recognize._recognizer import (
    _acoustid_session_local,
    _cleanup_aiohttp_resources,
    _close_acoustid_session,
    _get_acoustid_session,
    _is_valid_fingerprint_result,
    ACOUSTID_API_KEY,
    ACOUSTID_LOOKUP_URL,
    recognize_with_acoustid,
)

from auto_tag.audio_recognize._search import (
    _do_qqmusic_search,
    _do_radio_search,
    _do_single_search,
    _extract_netease_cover,
    _extract_response_data,
    _flatten_shazam_metadata,
    _get_netease_cover_by_id,
    _login_lock,
    _login_netease_guest,
    _netease_cookie,
    _parse_kugou_result,
    _parse_netease_radio_result,
    _parse_netease_result,
    _parse_qqmusic_result,
    _parse_shazam_result,
    _rate_limiter,
    _search_cache,
    _search_kugou,
    _search_netease,
    _search_netease_rest,
    _search_qqmusic,
    multi_source_search,
    RateLimiter,
    SearchCache,
    SearchResult,
)

from auto_tag.audio_recognize._orchestrator import (
    find_and_recognize_audio_files,
    recognize_and_rename_file,
)

# Backward-compatibility: tests mock auto_tag.audio_recognize.urlopen
# This was previously a top-level import in the monolithic audio_recognize.py
from urllib.request import urlopen
