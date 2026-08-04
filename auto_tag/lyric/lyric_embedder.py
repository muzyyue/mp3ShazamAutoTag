# -*- coding: utf-8 -*-
"""
歌词嵌入与提取模块

提供 LyricEmbedder 类，负责将歌词嵌入到音频文件（MP3/FLAC/M4A/OGG/OPUS）
以及从音频文件中提取歌词。
"""

from __future__ import annotations

import logging
import os
from typing import Any

import eyed3
from mutagen import File
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis

logger = logging.getLogger(__name__)


class LyricEmbedder:
    """
    歌词嵌入与提取类

    支持格式：
    - MP3：使用 eyed3 处理 ID3 标签（USLT/SYLT 帧）
    - FLAC：使用 mutagen.flac.FLAC（LYRICS Vorbis Comment）
    - M4A：使用 mutagen.mp4.MP4（©lyr iTunes 原子）
    - OGG：使用 mutagen.oggvorbis.OggVorbis（LYRICS Vorbis Comment）
    - OPUS：使用 mutagen.oggopus.OggOpus（LYRICS Vorbis Comment）
    """

    def __init__(self, logger):
        """
        初始化歌词嵌入器

        Args:
            logger: 日志记录器实例
        """
        self.logger = logger

    def embed_lyrics(
        self,
        file_path: str,
        lyrics: str,
        format: str = 'lrc',
        mode: str = 'embed_only'
    ) -> bool:
        """
        将歌词嵌入到音频文件

        Args:
            file_path: 音频文件路径
            lyrics: 歌词内容（LRC、TTML、SRT 或 JSON 格式）
            format: 歌词格式（'lrc', 'ttml', 'srt', 'json'）
            mode: 嵌入模式
                - 'embed_only' (默认): 仅嵌入音频文件，不生成 .lrc 文件
                - 'embed_and_lrc': 嵌入音频文件 + 生成同名 .lrc 文件

        Returns:
            bool: 嵌入成功返回 True，失败返回 False

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: 不支持的歌词格式或嵌入模式

        Example:
            >>> embedder = LyricEmbedder(logger)
            >>> lyrics = "[00:00.00]第一行歌词\\n[00:05.00]第二行歌词"
            >>> success = embedder.embed_lyrics('song.mp3', lyrics, 'lrc', 'embed_only')
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        supported_formats = ['lrc', 'ttml', 'srt', 'json']
        if format.lower() not in supported_formats:
            raise ValueError(
                f"不支持的歌词格式: {format}, 支持的格式: {supported_formats}"
            )

        supported_modes = ['embed_only', 'embed_and_lrc']
        if mode not in supported_modes:
            raise ValueError(
                f"不支持的嵌入模式: {mode}, 支持的模式: {supported_modes}"
            )

        ext = os.path.splitext(file_path)[1].lower()

        try:
            if ext == '.mp3':
                return self._embed_mp3_lyrics(file_path, lyrics, format, mode)
            elif ext in ['.flac', '.m4a', '.ogg']:
                return self._embed_generic_lyrics(file_path, lyrics, format, mode)
            else:
                self.logger.warning(f"不支持的文件格式: {ext}")
                return False

        except Exception as e:
            self.logger.error(f"嵌入歌词失败: {file_path}, 错误: {e}")
            return False

    def _embed_mp3_lyrics(
        self,
        file_path: str,
        lyrics: str,
        format: str,
        mode: str = 'embed_only'
    ) -> bool:
        """
        使用 mutagen 将歌词嵌入到 MP3 文件

        Args:
            file_path: MP3 文件路径
            lyrics: 歌词内容
            format: 歌词格式
            mode: 嵌入模式 ('embed_only' 或 'embed_and_lrc')

        Returns:
            bool: 成功返回 True

        Note:
            - 使用 mutagen.mp3 + mutagen.id3.USLT 帧写入歌词
            - 写入前先删除所有已有的 USLT 帧，避免旧数据残留
            - mutagen 的 API 比 eyed3 更可靠，不存在帧追加/替换歧义
        """
        try:
            from mutagen.mp3 import MP3
            from mutagen.id3 import USLT, ID3NoHeaderError

            audio = MP3(file_path)
            if audio.tags is None:
                audio.add_tags()

            keys_to_remove = [k for k in audio.tags.keys() if k.startswith('USLT:')]
            for k in keys_to_remove:
                del audio.tags[k]

            audio.tags.add(USLT(encoding=3, lang='eng', desc='Lyrics', text=lyrics))
            # Windows 资源管理器只解析 ID3v2.3, 强制降到 v2.3 (避免 preserve 原 v2.4)
            audio.tags.save(file_path, v2_version=3)
            self.logger.info(f"成功嵌入歌词到 MP3 (mutagen): {file_path}")

        except Exception as e:
            self.logger.error(f"mutagen 嵌入歌词失败: {file_path}, 错误: {e}", exc_info=True)
            return False

        if mode == 'embed_and_lrc':
            lrc_success = self._generate_lrc_file(file_path, lyrics)
            if lrc_success:
                self.logger.info(f"成功嵌入歌词并生成 LRC 文件: {file_path}")
            else:
                self.logger.warning(f"歌词嵌入成功，但 LRC 文件生成失败: {file_path}")

        return True

    def _embed_synced_lyrics_frame(self, tag, lyrics: str) -> None:
        """
        嵌入同步歌词（SYLT 帧）
        某些播放器（如 Foobar2000）支持此格式。
        """
        try:
            import re
            time_pattern = re.compile(r'\[(\d{2}):(\d{2})\.(\d{2,3})\]')
            matches = time_pattern.findall(lyrics)
            if not matches:
                return

            timestamp_millis = []
            for mm, ss, frac in matches:
                millis = (int(mm) * 60 + int(ss)) * 1000 + int(frac.ljust(3, '0')[:3])
                timestamp_millis.append(millis)

            text_without_tags = time_pattern.sub('', lyrics)
            lines = [line for line in text_without_tags.split('\n') if line.strip()]
            line_count = min(len(lines), len(timestamp_millis))

            if line_count == 0:
                return

            import eyed3.id3
            import struct
            timestamp_format = 1
            content_type = 1

            frame = eyed3.id3.SyltFrame()
            frame.timestamp_format = timestamp_format
            frame.content_type = content_type
            frame.language = b'eng'
            frame.content_descriptor = ''

            text_content = []
            for i in range(line_count):
                text_content.append((lines[i], timestamp_millis[i]))

            frame.text = text_content
            frame.encoding = eyed3.id3.UTF_8_ENCODING

            tag.synchronized_lyrics.set(frame)
            self.logger.debug("成功写入 SYLT 帧")

        except Exception as e:
            self.logger.debug(f"SYLT 帧写入失败（fallback 到 USLT）: {e}")

    def _embed_unsynced_lyrics_frame(self, tag, lyrics: str) -> None:
        """
        嵌入无同步歌词（USLT 帧）
        这是最广泛支持的歌词帧格式。

        Note:
            eyed3 v0.9.9 的 tag.lyrics.set() 要求使用**位置参数**而非关键字参数！
            签名: set(text: str, lang: str, description: bytes)

            **关键修复**：description 必须为非空值（如 b'Lyrics'），
            否则 Windows Media Player、Melosik 等播放器无法识别歌词帧。
        """
        try:
            # description 设为 b'Lyrics'（非空），确保播放器能识别歌词
            # eyed3 v0.9.9 decorator requires positional arguments!
            tag.lyrics.set(lyrics, 'eng', b'Lyrics')
            self.logger.debug("成功写入 USLT 帧 (description='Lyrics')")
        except TypeError:
            # 某些版本的 eyed3 可能要求 description 为 str
            try:
                tag.lyrics.set(lyrics, 'eng', 'Lyrics')
                self.logger.debug("成功写入 USLT 帧 (str description='Lyrics')")
            except Exception as e:
                self.logger.warning(f"USLT 帧写入失败: {e}")
                raise
        except Exception as e:
            self.logger.warning(f"USLT 帧写入失败: {e}")
            raise

    def _generate_lrc_file(self, file_path: str, lyrics: str) -> bool:
        """
        生成独立的 LRC 文件（网易云音乐等播放器需要）

        Args:
            file_path: 音频文件路径
            lyrics: 歌词内容

        Returns:
            bool: 成功返回 True

        Note:
            网易云音乐对 LRC 文件有严格要求：
            1. 文件名必须与音频文件完全相同（除扩展名）
            2. 编码必须是 UTF-8 无 BOM
            3. 必须与音频文件位于同一目录
            4. 时间戳格式必须符合 [mm:ss.xx] 标准
        """
        try:
            # 生成 LRC 文件路径
            lrc_path = os.path.splitext(file_path)[0] + '.lrc'

            # 确保 LRC 文件内容是 UTF-8 无 BOM 编码
            # Python 的 open() 函数默认写入 UTF-8，但可能会添加 BOM
            # 使用 utf-8 编码并明确不写入 BOM
            with open(lrc_path, 'w', encoding='utf-8', newline='') as f:
                # 写入歌词内容
                f.write(lyrics)

            self.logger.info(f"成功生成 LRC 文件: {lrc_path}")
            return True

        except Exception as e:
            self.logger.error(f"生成 LRC 文件失败: {file_path}, 错误: {e}")
            return False

    def _embed_generic_lyrics(
        self,
        file_path: str,
        lyrics: str,
        format: str,
        mode: str = 'embed_only'
    ) -> bool:
        """
        将歌词嵌入到通用音频文件（FLAC/M4A/OGG）
        使用 mutagen 格式特定的 API 进行嵌入。

        Args:
            file_path: 音频文件路径
            lyrics: 歌词内容
            format: 歌词格式
            mode: 嵌入模式 ('embed_only' 或 'embed_and_lrc')

        Returns:
            bool: 成功返回 True
        """
        ext = os.path.splitext(file_path)[1].lower()

        try:
            if ext == '.flac':
                from mutagen.flac import FLAC
                audio = FLAC(file_path)
                audio['LYRICS'] = lyrics
                audio.save()
                self.logger.debug("FLAC: 使用 mutagen.FLAC 写入 LYRICS 标签")

            elif ext == '.ogg':
                audio = OggVorbis(file_path)
                audio['LYRICS'] = lyrics
                audio.save()
                self.logger.debug("OGG: 使用 mutagen.OggVorbis 写入 LYRICS 标签")

            elif ext == '.opus':
                audio = OggOpus(file_path)
                audio['LYRICS'] = lyrics
                audio.save()
                self.logger.debug("OPUS: 使用 mutagen.OggOpus 写入 LYRICS 标签")

            elif ext in ('.m4a', '.mp4'):
                from mutagen.mp4 import MP4
                audio = MP4(file_path)
                audio['\xa9lyr'] = lyrics
                audio.save()
                self.logger.debug("M4A: 使用 mutagen.MP4 写入 ©lyr 原子")

            else:
                audio = File(file_path)
                if audio is None:
                    self.logger.error(f"无法识别的音频格式: {ext}")
                    return False
                audio['LYRICS'] = lyrics
                audio.save()
                self.logger.debug(f"{ext.upper()}: 使用 mutagen.File 写入 LYRICS 标签")

            if mode == 'embed_and_lrc':
                lrc_success = self._generate_lrc_file(file_path, lyrics)
                if lrc_success:
                    self.logger.info(f"成功嵌入歌词并生成 LRC 文件: {file_path}")
                else:
                    self.logger.warning(f"歌词嵌入成功，但 LRC 文件生成失败: {file_path}")
            else:
                self.logger.info(f"成功嵌入歌词 (仅嵌入模式): {file_path}")

            return True

        except Exception as e:
            self.logger.error(f"使用 mutagen 嵌入歌词失败: {file_path}, 错误: {e}")
            return False

    def extract_lyrics(self, file_path: str) -> dict[str, Any] | None:
        """
        从音频文件提取歌词

        Args:
            file_path: 音频文件路径

        Returns:
            dict | None: 歌词数据字典，格式为：
                {
                    'plain_lyrics': str,      # 纯文本歌词
                    'synced_lyrics': str,     # 同步歌词
                    'format': str             # 歌词格式
                }
            无歌词或提取失败返回 None

        Raises:
            FileNotFoundError: 文件不存在

        Example:
            >>> embedder = LyricEmbedder(logger)
            >>> lyrics = embedder.extract_lyrics('song.mp3')
            >>> if lyrics:
            ...     print(lyrics['synced_lyrics'])
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        ext = os.path.splitext(file_path)[1].lower()

        try:
            if ext == '.mp3':
                return self._extract_mp3_lyrics(file_path)
            elif ext == '.ogg':
                return self._extract_ogg_lyrics(file_path)
            elif ext in ['.flac', '.m4a']:
                return self._extract_generic_lyrics(file_path)
            else:
                self.logger.warning(f"不支持的文件格式: {ext}")
                return None

        except Exception as e:
            self.logger.error(f"提取歌词失败: {file_path}, 错误: {e}")
            return None

    def _extract_mp3_lyrics(self, file_path: str) -> dict[str, Any] | None:
        """
        从 MP3 文件提取歌词

        Args:
            file_path: MP3 文件路径

        Returns:
            dict | None: 歌词数据字典
        """
        audio = eyed3.load(file_path)
        if audio is None or audio.tag is None:
            self.logger.warning(f"MP3 文件无标签: {file_path}")
            return None

        tag = audio.tag
        synced_lyrics = ''
        plain_lyrics = ''

        # 方法1: 尝试读取 USLT 帧（非同步歌词传输）
        # 这是最常见的歌词存储方式，网易云音乐等播放器使用此格式
        if hasattr(tag, 'lyrics') and tag.lyrics:
            for lyrics_frame in tag.lyrics:
                if lyrics_frame.text:
                    synced_lyrics = lyrics_frame.text
                    break

        # 方法2: 尝试读取 SYLT 帧（同步歌词）
        if not synced_lyrics and hasattr(tag, 'lyrics'):
            try:
                for frame in tag.lyrics:
                    if hasattr(frame, 'text') and frame.text:
                        synced_lyrics = frame.text
                        break
            except Exception:
                pass

        # 方法3: 尝试读取 TXXX 帧（用户定义文本）
        if not synced_lyrics and hasattr(tag, 'user_text_frames'):
            try:
                for frame in tag.user_text_frames:
                    if frame.description in ['LYRICS', 'SYNCEDLYRICS', 'lyrics', 'syncedlyrics']:
                        synced_lyrics = frame.text
                        break
            except Exception:
                pass

        # 方法4: 尝试读取普通文本帧
        if not synced_lyrics and hasattr(tag, 'text'):
            try:
                for text_frame in tag.text:
                    if text_frame.description in ['LYRICS', 'SYNCEDLYRICS', 'lyrics', '']:
                        if text_frame.text:
                            synced_lyrics = text_frame.text
                            break
            except Exception:
                pass

        # 方法5: 尝试读取 comments
        if not synced_lyrics and hasattr(tag, 'comments'):
            try:
                for comment in tag.comments:
                    if comment.description in ['LYRICS', 'lyrics', '']:
                        if comment.text:
                            synced_lyrics = comment.text
                            break
            except Exception:
                pass

        if not synced_lyrics and not plain_lyrics:
            self.logger.info(f"MP3 文件无歌词: {file_path}")
            return None

        self.logger.info(f"成功提取 MP3 歌词: {file_path}")
        return {
            'plain_lyrics': plain_lyrics,
            'synced_lyrics': synced_lyrics,
            'format': 'lrc' if synced_lyrics else 'plain'
        }

    def _extract_ogg_lyrics(self, file_path: str) -> dict[str, Any] | None:
        """
        从 OGG 文件提取歌词

        Args:
            file_path: OGG 文件路径

        Returns:
            dict | None: 歌词数据字典
        """
        # 尝试 Vorbis，然后 Opus，最后通用格式
        audio = None
        try:
            audio = OggVorbis(file_path)
        except Exception:
            try:
                audio = OggOpus(file_path)
            except Exception:
                audio = File(file_path)

        if audio is None:
            self.logger.warning(f"无法识别的 OGG 格式: {file_path}")
            return None

        # 读取歌词标签
        synced_lyrics = audio.get('SYNCEDLYRICS', [''])[0]
        plain_lyrics = audio.get('LYRICS', [''])[0]

        if not synced_lyrics and not plain_lyrics:
            self.logger.info(f"OGG 文件无歌词: {file_path}")
            return None

        self.logger.info(f"成功提取 OGG 歌词: {file_path}")
        return {
            'plain_lyrics': plain_lyrics,
            'synced_lyrics': synced_lyrics,
            'format': 'lrc' if synced_lyrics else 'plain'
        }

    def _extract_generic_lyrics(self, file_path: str) -> dict[str, Any] | None:
        """
        从通用音频文件提取歌词

        Args:
            file_path: 音频文件路径

        Returns:
            dict | None: 歌词数据字典
        """
        audio = File(file_path)
        if audio is None:
            self.logger.warning(f"无法加载音频文件: {file_path}")
            return None

        # 尝试读取歌词标签
        synced_lyrics = audio.get('SYNCEDLYRICS', [''])[0]
        plain_lyrics = audio.get('LYRICS', [''])[0]

        if not synced_lyrics and not plain_lyrics:
            # 尝试其他可能的标签名
            synced_lyrics = audio.get('UNSYNCEDLYRICS', [''])[0]
            plain_lyrics = audio.get('UNSYNCED LYRICS', [''])[0]

        if not synced_lyrics and not plain_lyrics:
            self.logger.info(f"音频文件无歌词: {file_path}")
            return None

        self.logger.info(f"成功提取歌词: {file_path}")
        return {
            'plain_lyrics': plain_lyrics,
            'synced_lyrics': synced_lyrics,
            'format': 'lrc' if synced_lyrics else 'plain'
        }

    def batch_embed_lyrics(
        self,
        file_lyrics_pairs: list[tuple[str, str]],
        format: str = 'lrc',
        mode: str = 'embed_only'
    ) -> dict[str, bool]:
        """
        批量嵌入歌词

        Args:
            file_lyrics_pairs: 文件路径和歌词内容的元组列表
            format: 歌词格式
            mode: 嵌入模式 ('embed_only' 或 'embed_and_lrc')

        Returns:
            dict[str, bool]: 文件路径到操作结果的映射

        Example:
            >>> embedder = LyricEmbedder(logger)
            >>> results = embedder.batch_embed_lyrics([
            ...     ('song1.mp3', '[00:00.00]歌词1'),
            ...     ('song2.flac', '[00:00.00]歌词2')
            ... ], format='lrc', mode='embed_only')
        """
        results = {}

        for file_path, lyrics in file_lyrics_pairs:
            try:
                success = self.embed_lyrics(file_path, lyrics, format, mode)
                results[file_path] = success
            except Exception as e:
                self.logger.error(f"批量嵌入歌词失败: {file_path}, 错误: {e}")
                results[file_path] = False

        success_count = sum(1 for v in results.values() if v)
        self.logger.info(
            f"批量嵌入歌词完成: 成功 {success_count}/{len(file_lyrics_pairs)}"
        )

        return results
