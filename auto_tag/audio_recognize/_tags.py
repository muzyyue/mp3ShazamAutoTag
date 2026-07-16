# auto_tag/audio_recognize/_tags.py
"""
Audio tag writing module: supports MP3 (eyed3), OGG/Opus, FLAC, M4A/MP4,
and generic formats (WMA, AAC) via mutagen.

Depends on: nothing internal (self-contained)
"""

from __future__ import annotations

import base64
import logging
import os
from urllib.request import urlopen

import eyed3
from mutagen import File
from mutagen.flac import Picture
from mutagen.id3 import TALB, TCON, TDRC, TIT2, TPE1
from mutagen.mp4 import MP4
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis

logger = logging.getLogger(__name__)


def update_mp3_cover_art(file_path: str, cover_url: str, trace: bool) -> None:
    """
    更新 MP3 文件的封面图片

    Args:
        file_path (str): MP3 文件路径
        cover_url (str): 封面图片 URL
        trace (bool): 是否输出调试信息

    Raises:
        ValueError: 无法加载 MP3 文件
        RuntimeError: 封面图片下载或保存失败
    """
    logger.info(f"[update_mp3_cover_art] Processing: {file_path}")

    if not cover_url:
        logger.info(f"[update_mp3_cover_art] No cover URL provided, skipping")
        if trace:
            print(f"No cover art for {file_path}")
        return

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"MP3 文件不存在: {file_path}")

    try:
        audio = eyed3.load(file_path)
        if not audio:
            raise ValueError(f"无法加载 MP3 文件: {file_path}")

        if audio.tag is None:
            audio.initTag()

        logger.info(f"[update_mp3_cover_art] Downloading cover from URL...")
        import urllib.request
        req = urllib.request.Request(
            cover_url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        img = urlopen(req, timeout=10).read()
        audio.tag.images.set(3, img, "image/jpeg", "cover")
        audio.tag.save()
        logger.info(f"[update_mp3_cover_art] ✓ Cover art saved successfully for {os.path.basename(file_path)}")
    except Exception as e:
        logger.error(f"[update_mp3_cover_art] ✗ Failed to save cover art: {e}", exc_info=True)
        raise RuntimeError(f"保存封面失败: {e}") from e


def update_mp3_tags(
    file_path: str, title: str, artist: str, album: str,
    year: str | None = None, genre: str | None = None
) -> None:
    """
    更新 MP3 文件的 ID3 标签

    Args:
        file_path (str): MP3 文件路径
        title (str): 歌曲标题
        artist (str): 艺术家
        album (str): 专辑名
        year (str | None): 发行年份（可选）
        genre (str | None): 音乐流派（可选）

    Raises:
        ValueError: 无法加载或解析 MP3 文件
        RuntimeError: 标签保存失败
    """
    logger.info(f"[update_mp3_tags] Loading file: {file_path}")
    logger.info(f"[update_mp3_tags] Metadata to write - title='{title}', artist='{artist}', album='{album}', year='{year}', genre='{genre}'")

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"MP3 文件不存在: {file_path}")

    audio = eyed3.load(file_path)
    if not audio:
        raise ValueError(f"无法加载 MP3 文件（可能格式损坏或不支持）: {file_path}")

    logger.info(f"[update_mp3_tags] File loaded successfully, tag exists: {audio.tag is not None}")

    if audio.tag is None:
        logger.info(f"[update_mp3_tags] Initializing new ID3 tag...")
        audio.initTag()

    try:
        audio.tag.title = title
        audio.tag.artist = artist
        audio.tag.album = album
        if year:
            from datetime import datetime
            try:
                audio.tag.recording_date = datetime(int(year), 1, 1)
            except (ValueError, TypeError):
                audio.tag.release_date = year
        if genre:
            audio.tag.genre = genre
            audio.tag.genre_id = None
        logger.info(f"[update_mp3_tags] Tag values set, saving...")
        audio.tag.save()
        logger.info(f"[update_mp3_tags] ✓ Tags saved successfully for {os.path.basename(file_path)}")
    except Exception as e:
        logger.error(f"[update_mp3_tags] ✗ Failed to save tags: {e}", exc_info=True)
        raise RuntimeError(f"保存 MP3 标签失败: {e}") from e


def update_ogg_tags(
    file_path: str,
    title: str,
    artist: str,
    album: str,
    cover_url: str,
    trace: bool,
    year: str | None = None,
    genre: str | None = None,
) -> None:
    """
    更新 OGG 文件的 Vorbis/Opus 标签

    Args:
        file_path (str): OGG 文件路径
        title (str): 歌曲标题
        artist (str): 艺术家
        album (str): 专辑名
        cover_url (str): 封面图片 URL
        trace (bool): 是否输出调试信息
        year (str | None): 发行年份（可选）
        genre (str | None): 音乐流派（可选）

    Raises:
        FileNotFoundError: OGG 文件不存在
        RuntimeError: 不支持的 OGG 格式或标签保存失败
    """
    logger.info(f"[update_ogg_tags] Loading file: {file_path}")
    logger.info(f"[update_ogg_tags] Metadata to write - title='{title}', artist='{artist}', album='{album}', year='{year}', genre='{genre}'")

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"OGG 文件不存在: {file_path}")

    # Try Vorbis, then Opus, then generic
    audio = None
    try:
        audio = OggVorbis(file_path)
        logger.info(f"[update_ogg_tags] Loaded as OggVorbis")
    except Exception as e:
        logger.debug(f"[update_ogg_tags] Not Vorbis format: {e}")
        try:
            audio = OggOpus(file_path)
            logger.info(f"[update_ogg_tags] Loaded as OggOpus")
        except Exception as e2:
            logger.debug(f"[update_ogg_tags] Not Opus format: {e2}")
            audio = File(file_path)
            if audio is None:
                raise RuntimeError(f"不支持的 OGG 文件格式: {file_path}")
            logger.info(f"[update_ogg_tags] Loaded as generic File")

    try:
        audio["TITLE"] = [title]
        audio["ARTIST"] = [artist]
        audio["ALBUM"] = [album]
        if year:
            audio["DATE"] = [year]
        if genre:
            audio["GENRE"] = [genre]
        logger.info(f"[update_ogg_tags] Tag values set")

        if cover_url:
            try:
                logger.info(f"[update_ogg_tags] Downloading cover art from URL...")
                img = urlopen(cover_url).read()
                pic = Picture()
                pic.data = img
                pic.type = 3
                pic.mime = "image/jpeg"
                pic.width = pic.height = pic.depth = pic.colors = 0
                b64 = base64.b64encode(pic.write()).decode("ascii")
                audio["METADATA_BLOCK_PICTURE"] = [b64]
                logger.info(f"[update_ogg_tags] Cover art embedded successfully")
            except Exception as exc:
                logger.warning(f"[update_ogg_tags] Cover art error (non-fatal): {exc}")
                if trace:
                    print(f"Cover art error: {exc}")
        else:
            logger.info(f"[update_ogg_tags] No cover URL provided")

        audio.save()
        logger.info(f"[update_ogg_tags] ✓ Tags saved successfully for {os.path.basename(file_path)}")
    except Exception as e:
        logger.error(f"[update_ogg_tags] ✗ Failed to save tags: {e}", exc_info=True)
        raise RuntimeError(f"保存 OGG 标签失败: {e}") from e


def update_audio_tags(
    file_path: str,
    title: str,
    artist: str,
    album: str,
    cover_url: str | None = None,
    trace: bool = False,
    year: str | None = None,
    genre: str | None = None,
) -> None:
    """
    通用音频标签写入函数，支持多种音频格式

    根据文件扩展名自动选择合适的标签写入方式：
    - MP3: 使用 eyed3 (ID3v2.4)
    - OGG/OPUS: 使用 mutagen (Vorbis Comment)
    - FLAC: 使用 mutagen (Vorbis Comment + FLAC Picture)
    - M4A/MP4: 使用 mutagen (MP4 原子)
    - WAV: 跳过（WAV 不支持标准元数据嵌入）
    - WMA/AAC: 尝试使用 mutagen 通用接口

    Args:
        file_path (str): 音频文件路径
        title (str): 歌曲标题
        artist (str): 艺术家名称
        album (str): 专辑名称
        cover_url (str | None): 封面图片 URL（可选）
        trace (bool): 是否输出调试信息
        year (str | None): 发行年份（可选，None 或空字符串时不写入）
        genre (str | None): 音乐流派（可选，None 或空字符串时不写入）

    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 不支持的文件格式
        RuntimeError: 标签保存失败

    Example:
        >>> update_audio_tags("song.flac", "Title", "Artist", "Album")
        >>> update_audio_tags("song.m4a", "Title", "Artist", "Album", "http://cover.jpg", year="2024", genre="Pop")
    """
    logger.info(f"[update_audio_tags] Processing file: {file_path}")
    logger.info(f"[update_audio_tags] Metadata - title='{title}', artist='{artist}', album='{album}', year='{year}', genre='{genre}'")

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"音频文件不存在: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()
    logger.info(f"[update_audio_tags] Detected format: {ext}")

    try:
        if ext == ".mp3":
            _write_mp3_tags(file_path, title, artist, album, cover_url, trace, year, genre)
        elif ext in (".ogg", ".opus"):
            _write_vorbis_tags(file_path, title, artist, album, cover_url, trace, year, genre)
        elif ext == ".flac":
            _write_flac_tags(file_path, title, artist, album, cover_url, trace, year, genre)
        elif ext in (".m4a", ".mp4"):
            _write_mp4_tags(file_path, title, artist, album, cover_url, trace, year, genre)
        elif ext == ".wav":
            logger.warning(f"[update_audio_tags] WAV 格式不支持元数据嵌入，跳过: {file_path}")
            if trace:
                print(f"⚠ WAV 格式不支持元数据嵌入")
        elif ext in (".wma", ".aac"):
            _write_generic_tags(file_path, title, artist, album, cover_url, trace, year, genre)
        else:
            raise ValueError(f"不支持的文件格式: {ext}")

        logger.info(f"[update_audio_tags] ✓ Tags saved successfully for {os.path.basename(file_path)}")

    except Exception as e:
        logger.error(f"[update_audio_tags] ✗ Failed to save tags: {e}", exc_info=True)
        raise


def _write_mp3_tags(
    file_path: str,
    title: str,
    artist: str,
    album: str,
    cover_url: str | None,
    trace: bool,
    year: str | None = None,
    genre: str | None = None,
) -> None:
    """写入 MP3 标签（内部函数）"""
    logger.info(f"[update_audio_tags] Writing MP3 tags...")
    update_mp3_tags(file_path, title, artist, album, year, genre)

    if cover_url:
        logger.info(f"[update_audio_tags] Adding MP3 cover art...")
        update_mp3_cover_art(file_path, cover_url, trace=trace)


def _write_vorbis_tags(
    file_path: str,
    title: str,
    artist: str,
    album: str,
    cover_url: str | None,
    trace: bool,
    year: str | None = None,
    genre: str | None = None,
) -> None:
    """写入 OGG/OPUS Vorbis Comment 标签（内部函数）"""
    logger.info(f"[update_audio_tags] Writing Vorbis tags (OGG/OPUS)...")
    update_ogg_tags(file_path, title, artist, album, cover_url or "", trace, year, genre)


def _write_flac_tags(
    file_path: str,
    title: str,
    artist: str,
    album: str,
    cover_url: str | None,
    trace: bool,
    year: str | None = None,
    genre: str | None = None,
) -> None:
    """
    写入 FLAC 标签（Vorbis Comment + FLAC Picture）

    FLAC 使用 Vorbis Comment 存储文本元数据，使用 FLAC PICTURE block 存储封面。
    """
    from mutagen.flac import FLAC

    logger.info(f"[update_audio_tags] Loading FLAC file...")

    try:
        audio = FLAC(file_path)
        logger.info(f"[update_audio_tags] FLAC file loaded successfully")
    except Exception as e:
        logger.error(f"[update_audio_tags] Failed to load FLAC file: {e}")
        raise RuntimeError(f"无法加载 FLAC 文件: {file_path}") from e

    try:
        audio["TITLE"] = title
        audio["ARTIST"] = artist
        audio["ALBUM"] = album
        if year:
            audio["DATE"] = year
        if genre:
            audio["GENRE"] = genre
        logger.info(f"[update_audio_tags] FLAC text tags set")

        if cover_url:
            try:
                logger.info(f"[update_audio_tags] Downloading FLAC cover art...")
                img_data = urlopen(cover_url).read()

                picture = Picture()
                picture.data = img_data
                picture.type = 3
                picture.mime = "image/jpeg"
                picture.width = 0
                picture.height = 0
                picture.depth = 0
                picture.colors = 0

                audio.clear_pictures()
                audio.add_picture(picture)
                logger.info(f"[update_audio_tags] FLAC cover art embedded")
            except Exception as exc:
                logger.warning(f"[update_audio_tags] FLAC cover art error (non-fatal): {exc}")
                if trace:
                    print(f"FLAC 封面错误: {exc}")

        audio.save()
        logger.info(f"[update_audio_tags] ✓ FLAC tags saved successfully")

    except Exception as e:
        logger.error(f"[update_audio_tags] Failed to save FLAC tags: {e}", exc_info=True)
        raise RuntimeError(f"保存 FLAC 标签失败: {e}") from e


def _write_mp4_tags(
    file_path: str,
    title: str,
    artist: str,
    album: str,
    cover_url: str | None,
    trace: bool,
    year: str | None = None,
    genre: str | None = None,
) -> None:
    """
    写入 M4A/MP4 标签（MP4 Atoms）

    M4A/MP4 使用 Apple 的 iTunes Metadata 格式存储元数据。
    """
    from mutagen.mp4 import MP4

    logger.info(f"[update_audio_tags] Loading M4A/MP4 file...")

    try:
        audio = MP4(file_path)
        logger.info(f"[update_audio_tags] M4A/MP4 file loaded successfully")
    except Exception as e:
        logger.error(f"[update_audio_tags] Failed to load M4A/MP4 file: {e}")
        raise RuntimeError(f"无法加载 M4A/MP4 文件: {file_path}") from e

    try:
        audio["©nam"] = title
        audio["©ART"] = artist
        audio["©alb"] = album
        if year:
            audio["©day"] = year
        if genre:
            audio["©gen"] = genre
        logger.info(f"[update_audio_tags] M4A/MP4 text tags set")

        if cover_url:
            try:
                logger.info(f"[update_audio_tags] Downloading M4A/MP4 cover art...")
                img_data = urlopen(cover_url).read()

                audio["covr"] = [MP4.Cover(img_data, imageformat=MP4.FORMAT_JPEG)]
                logger.info(f"[update_audio_tags] M4A/MP4 cover art embedded")
            except Exception as exc:
                logger.warning(f"[update_audio_tags] M4A/MP4 cover art error (non-fatal): {exc}")
                if trace:
                    print(f"M4A/MP4 封面错误: {exc}")

        audio.save()
        logger.info(f"[update_audio_tags] ✓ M4A/MP4 tags saved successfully")

    except Exception as e:
        logger.error(f"[update_audio_tags] Failed to save M4A/MP4 tags: {e}", exc_info=True)
        raise RuntimeError(f"保存 M4A/MP4 标签失败: {e}") from e


def _write_generic_tags(
    file_path: str,
    title: str,
    artist: str,
    album: str,
    cover_url: str | None,
    trace: bool,
    year: str | None = None,
    genre: str | None = None,
) -> None:
    """
    通用标签写入（用于 WMA、AAC 等其他格式）

    使用 mutagen 的 File 接口尝试自动检测并处理。
    注意：某些格式可能不完全支持所有字段。
    """
    from mutagen.id3 import TIT2, TPE1, TALB, TDRC, TCON

    logger.info(f"[update_audio_tags] Trying generic tag writer for {file_path}...")

    try:
        audio = File(file_path)
        if audio is None or not hasattr(audio, 'tags') or audio.tags is None:
            raise RuntimeError(f"无法读取文件标签: {file_path}")

        logger.info(f"[update_audio_tags] Generic file loaded: {type(audio).__name__}")

        if audio.tags is not None:
            if hasattr(audio.tags, 'add'):
                audio.tags.remove('TITLE')
                audio.tags.remove('ARTIST')
                audio.tags.remove('ALBUM')
                audio.tags.add(TIT2(encoding=3, text=title))
                audio.tags.add(TPE1(encoding=3, text=artist))
                audio.tags.add(TALB(encoding=3, text=album))
                if year:
                    try:
                        audio.tags.remove('TDRC')
                        audio.tags.add(TDRC(encoding=3, text=year))
                    except Exception:
                        pass
                if genre:
                    try:
                        audio.tags.remove('TCON')
                        audio.tags.add(TCON(encoding=3, text=genre))
                    except Exception:
                        pass
            else:
                audio["title"] = title
                audio["artist"] = artist
                audio["album"] = album
                if year:
                    audio["year"] = year
                if genre:
                    audio["genre"] = genre

            logger.info(f"[update_audio_tags] Generic tags set")

        audio.save()
        logger.info(f"[update_audio_tags] ✓ Generic tags saved successfully")

    except Exception as e:
        logger.error(f"[update_audio_tags] Generic tag write failed: {e}", exc_info=True)
        raise RuntimeError(f"保存标签失败 ({os.path.splitext(file_path)[1]}): {e}") from e
