# -*- coding: utf-8 -*-
"""
歌词获取功能综合测试模块

测试 LyricManager 类的各项功能，包括歌词获取、嵌入、提取、格式转换和批量操作。

@module test_lyric_comprehensive
@author Backend Architect
@version 1.0.0
"""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from auto_tag.lyric import LyricManager, get_provider, list_providers


class TestLyricFetchNormal:
    """
    歌词获取正常场景测试类

    测试歌词获取功能的正常使用场景
    """

    def test_init_lyric_manager(self, lyric_manager):
        """
        TC-N-000: 测试 LyricManager 初始化

        Args:
            lyric_manager: LyricManager实例fixture
        """
        assert lyric_manager is not None
        assert lyric_manager.logger is not None

    @pytest.mark.parametrize("provider", ["lrclib", "applemusic", "musixmatch"])
    @patch("auto_tag.lyric.manager.get_provider_api")
    @patch("lrxy.utils.load_audio")
    @patch("lrxy.utils.iter_files")
    def test_fetch_lyrics_from_providers(
        self, mock_iter_files, mock_load_audio, mock_get_provider_api,
        provider, lyric_manager, temp_audio_file, mock_audio_object
    ):
        """
        TC-N-001/002/003: 测试从不同提供商获取歌词

        Args:
            mock_iter_files: Mock iter_files函数
            mock_load_audio: Mock load_audio函数
            mock_get_provider_api: Mock get_provider_api函数
            provider: 提供商名称
            lyric_manager: LyricManager实例
            temp_audio_file: 临时音频文件
            mock_audio_object: Mock音频对象
        """
        mock_provider_api = MagicMock()
        mock_get_provider_api.return_value = mock_provider_api
        mock_load_audio.return_value = mock_audio_object
        mock_iter_files.return_value = [{
            'success': True,
            'data': {
                'plainLyrics': 'Test lyrics',
                'syncedLyrics': '[00:00.00]Test lyrics'
            }
        }]

        result = lyric_manager.fetch_lyrics(temp_audio_file, provider=provider)

        assert result is not None
        assert 'plain_lyrics' in result
        assert 'synced_lyrics' in result
        assert result['provider'] == provider

    @patch("auto_tag.lyric.manager.get_provider_api")
    @patch("lrxy.utils.load_audio")
    @patch("lrxy.utils.iter_files")
    def test_fetch_lyrics_content_accuracy(
        self, mock_iter_files, mock_load_audio, mock_get_provider_api,
        lyric_manager, temp_audio_file, mock_audio_object
    ):
        """
        TC-N-004: 测试获取歌词内容准确性验证

        Args:
            mock_iter_files: Mock iter_files函数
            mock_load_audio: Mock load_audio函数
            mock_get_provider_api: Mock get_provider_api函数
            lyric_manager: LyricManager实例
            temp_audio_file: 临时音频文件
            mock_audio_object: Mock音频对象
        """
        expected_plain = "花に亡霊\n夜に駆ける"
        expected_synced = "[00:00.00]花に亡霊\n[00:05.00]夜に駆ける"

        mock_provider_api = MagicMock()
        mock_get_provider_api.return_value = mock_provider_api
        mock_load_audio.return_value = mock_audio_object
        mock_iter_files.return_value = [{
            'success': True,
            'data': {
                'plainLyrics': expected_plain,
                'syncedLyrics': expected_synced
            }
        }]

        result = lyric_manager.fetch_lyrics(temp_audio_file, provider="lrclib")

        assert result is not None
        assert result['plain_lyrics'] == expected_plain
        assert result['synced_lyrics'] == expected_synced

    @patch("auto_tag.lyric.manager.get_provider_api")
    @patch("lrxy.utils.load_audio")
    @patch("lrxy.utils.iter_files")
    def test_fetch_lyrics_metadata_validation(
        self, mock_iter_files, mock_load_audio, mock_get_provider_api,
        lyric_manager, temp_audio_file
    ):
        """
        TC-N-005: 测试获取歌词元数据验证

        Args:
            mock_iter_files: Mock iter_files函数
            mock_load_audio: Mock load_audio函数
            mock_get_provider_api: Mock get_provider_api函数
            lyric_manager: LyricManager实例
            temp_audio_file: 临时音频文件
        """
        mock_audio = MagicMock()
        mock_audio.title = "Ghost In A Flower"
        mock_audio.artist = "Yorushika"
        mock_audio.album = "Plagiarism"
        mock_audio.duration = 245
        mock_audio.track_name = "Ghost In A Flower"
        mock_audio.artist_name = "Yorushika"
        mock_audio.album_name = "Plagiarism"

        mock_provider_api = MagicMock()
        mock_get_provider_api.return_value = mock_provider_api
        mock_load_audio.return_value = mock_audio
        mock_iter_files.return_value = [{
            'success': True,
            'data': {
                'plainLyrics': 'Test lyrics',
                'syncedLyrics': '[00:00.00]Test lyrics'
            }
        }]

        result = lyric_manager.fetch_lyrics(temp_audio_file, provider="lrclib")

        assert result is not None
        assert result['track_name'] == "Ghost In A Flower"
        assert result['artist_name'] == "Yorushika"
        assert result['album_name'] == "Plagiarism"
        assert result['duration'] == 245

    @patch("lrxy.utils.load_audio")
    def test_embed_lyrics_to_mp3(self, mock_load_audio, lyric_manager, temp_audio_file, sample_lrc_lyrics):
        """
        TC-N-006: 测试嵌入LRC格式歌词到MP3

        Args:
            mock_load_audio: Mock load_audio函数
            lyric_manager: LyricManager实例
            temp_audio_file: 临时音频文件
            sample_lrc_lyrics: 样本LRC歌词
        """
        mock_audio = MagicMock()
        mock_audio.embed_lyric = MagicMock(return_value=None)
        mock_load_audio.return_value = mock_audio

        result = lyric_manager.embed_lyrics(temp_audio_file, sample_lrc_lyrics, format='lrc')

        assert result is True
        mock_audio.embed_lyric.assert_called_once_with(sample_lrc_lyrics)

    @patch("lrxy.utils.load_audio")
    def test_embed_lyrics_to_flac(self, mock_load_audio, lyric_manager, temp_flac_file, sample_lrc_lyrics):
        """
        TC-N-007: 测试嵌入LRC格式歌词到FLAC

        Args:
            mock_load_audio: Mock load_audio函数
            lyric_manager: LyricManager实例
            temp_flac_file: 临时FLAC文件
            sample_lrc_lyrics: 样本LRC歌词
        """
        mock_audio = MagicMock()
        mock_audio.embed_lyric = MagicMock(return_value=None)
        mock_load_audio.return_value = mock_audio

        result = lyric_manager.embed_lyrics(temp_flac_file, sample_lrc_lyrics, format='lrc')

        assert result is True

    @patch("lrxy.utils.load_audio")
    def test_embed_ttml_lyrics(self, mock_load_audio, lyric_manager, temp_audio_file, sample_ttml_lyrics):
        """
        TC-N-008: 测试嵌入TTML格式歌词

        Args:
            mock_load_audio: Mock load_audio函数
            lyric_manager: LyricManager实例
            temp_audio_file: 临时音频文件
            sample_ttml_lyrics: 样本TTML歌词
        """
        mock_audio = MagicMock()
        mock_audio.embed_lyric = MagicMock(return_value=None)
        mock_load_audio.return_value = mock_audio

        result = lyric_manager.embed_lyrics(temp_audio_file, sample_ttml_lyrics, format='ttml')

        assert result is True

    @patch("lrxy.utils.load_audio")
    def test_embed_srt_lyrics(self, mock_load_audio, lyric_manager, temp_audio_file, sample_srt_lyrics):
        """
        TC-N-009: 测试嵌入SRT格式歌词

        Args:
            mock_load_audio: Mock load_audio函数
            lyric_manager: LyricManager实例
            temp_audio_file: 临时音频文件
            sample_srt_lyrics: 样本SRT歌词
        """
        mock_audio = MagicMock()
        mock_audio.embed_lyric = MagicMock(return_value=None)
        mock_load_audio.return_value = mock_audio

        result = lyric_manager.embed_lyrics(temp_audio_file, sample_srt_lyrics, format='srt')

        assert result is True

    @patch("lrxy.utils.load_audio")
    def test_embed_json_lyrics(self, mock_load_audio, lyric_manager, temp_audio_file, sample_json_lyrics):
        """
        TC-N-010: 测试嵌入JSON格式歌词

        Args:
            mock_load_audio: Mock load_audio函数
            lyric_manager: LyricManager实例
            temp_audio_file: 临时音频文件
            sample_json_lyrics: 样本JSON歌词
        """
        mock_audio = MagicMock()
        mock_audio.embed_lyric = MagicMock(return_value=None)
        mock_load_audio.return_value = mock_audio

        result = lyric_manager.embed_lyrics(temp_audio_file, sample_json_lyrics, format='json')

        assert result is True

    def test_extract_lyrics_from_mp3(self, lyric_manager, temp_audio_file):
        """
        TC-N-011: 测试从MP3提取歌词

        Args:
            lyric_manager: LyricManager实例
            temp_audio_file: 临时音频文件
        """
        with patch('auto_tag.lyric.manager.eyed3.load') as mock_eyed3_load:
            mock_audio = MagicMock()
            mock_tag = MagicMock()
            mock_lyrics_frame = MagicMock()
            mock_lyrics_frame.text = "[00:00.00]Test lyrics"
            mock_lyrics_frame.lang = "eng"
            mock_tag.lyrics = [mock_lyrics_frame]
            mock_tag.text = []
            mock_audio.tag = mock_tag
            mock_eyed3_load.return_value = mock_audio

            result = lyric_manager.extract_lyrics(temp_audio_file)

            assert result is not None
            assert 'synced_lyrics' in result

    def test_extract_lyrics_from_flac(self, lyric_manager, temp_flac_file):
        """
        TC-N-012: 测试从FLAC提取歌词

        Args:
            lyric_manager: LyricManager实例
            temp_flac_file: 临时FLAC文件
        """
        with patch('auto_tag.lyric.manager.File') as mock_file:
            mock_audio = MagicMock()
            mock_audio.get = MagicMock(side_effect=lambda key, default=None: {
                'SYNCEDLYRICS': ['[00:00.00]Test lyrics'],
                'LYRICS': ['Test lyrics']
            }.get(key, default))
            mock_file.return_value = mock_audio

            result = lyric_manager.extract_lyrics(temp_flac_file)

            assert result is not None

    def test_extract_lyrics_from_ogg(self, lyric_manager, temp_ogg_file):
        """
        TC-N-013: 测试从OGG提取歌词

        Args:
            lyric_manager: LyricManager实例
            temp_ogg_file: 临时OGG文件
        """
        with patch('auto_tag.lyric.manager.OggVorbis') as mock_ogg:
            mock_audio = MagicMock()
            mock_audio.get = MagicMock(side_effect=lambda key, default=None: {
                'SYNCEDLYRICS': ['[00:00.00]Test lyrics'],
                'LYRICS': ['Test lyrics']
            }.get(key, default))
            mock_ogg.return_value = mock_audio

            result = lyric_manager.extract_lyrics(temp_ogg_file)

            assert result is not None

    def test_extract_lyrics_from_m4a(self, lyric_manager, temp_m4a_file):
        """
        TC-N-014: 测试从M4A提取歌词

        Args:
            lyric_manager: LyricManager实例
            temp_m4a_file: 临时M4A文件
        """
        with patch('auto_tag.lyric.manager.File') as mock_file:
            mock_audio = MagicMock()
            mock_audio.get = MagicMock(side_effect=lambda key, default=None: {
                'SYNCEDLYRICS': ['[00:00.00]Test lyrics'],
                'LYRICS': ['Test lyrics']
            }.get(key, default))
            mock_file.return_value = mock_audio

            result = lyric_manager.extract_lyrics(temp_m4a_file)

            assert result is not None

    def test_convert_lrc_to_ttml(self, lyric_manager, sample_lrc_lyrics):
        """
        TC-N-015: 测试LRC转TTML

        Args:
            lyric_manager: LyricManager实例
            sample_lrc_lyrics: 样本LRC歌词
        """
        with patch('auto_tag.lyric.manager.converter') as mock_converter:
            mock_lrc_parser = MagicMock()
            mock_lrc_parser.parse = MagicMock(return_value={'lyrics': []})
            mock_ttml_generator = MagicMock()
            mock_ttml_generator.generate = MagicMock(return_value="<tt>test</tt>")

            mock_converter.lrc = mock_lrc_parser
            mock_converter.ttml = mock_ttml_generator

            result = lyric_manager.convert_lyrics(sample_lrc_lyrics, 'lrc', 'ttml')

            assert result is not None

    def test_convert_lrc_to_srt(self, lyric_manager, sample_lrc_lyrics):
        """
        TC-N-016: 测试LRC转SRT

        Args:
            lyric_manager: LyricManager实例
            sample_lrc_lyrics: 样本LRC歌词
        """
        with patch('auto_tag.lyric.manager.converter') as mock_converter:
            mock_lrc_parser = MagicMock()
            mock_lrc_parser.parse = MagicMock(return_value={'lyrics': []})
            mock_srt_generator = MagicMock()
            mock_srt_generator.generate = MagicMock(return_value="1\n00:00:00,000 --> 00:00:05,000\ntest")

            mock_converter.lrc = mock_lrc_parser
            mock_converter.srt = mock_srt_generator

            result = lyric_manager.convert_lyrics(sample_lrc_lyrics, 'lrc', 'srt')

            assert result is not None

    def test_convert_lrc_to_json(self, lyric_manager, sample_lrc_lyrics):
        """
        TC-N-017: 测试LRC转JSON

        Args:
            lyric_manager: LyricManager实例
            sample_lrc_lyrics: 样本LRC歌词
        """
        with patch('auto_tag.lyric.manager.converter') as mock_converter:
            mock_lrc_parser = MagicMock()
            mock_lrc_parser.parse = MagicMock(return_value={'lyrics': []})

            mock_converter.lrc = mock_lrc_parser

            result = lyric_manager.convert_lyrics(sample_lrc_lyrics, 'lrc', 'json')

            assert result is not None

    def test_convert_ttml_to_lrc(self, lyric_manager, sample_ttml_lyrics):
        """
        TC-N-018: 测试TTML转LRC

        Args:
            lyric_manager: LyricManager实例
            sample_ttml_lyrics: 样本TTML歌词
        """
        with patch('auto_tag.lyric.manager.converter') as mock_converter:
            mock_ttml_parser = MagicMock()
            mock_ttml_parser.parse = MagicMock(return_value={'lyrics': []})
            mock_lrc_generator = MagicMock()
            mock_lrc_generator.generate = MagicMock(return_value="[00:00.00]test")

            mock_converter.ttml = mock_ttml_parser
            mock_converter.lrc = mock_lrc_generator

            result = lyric_manager.convert_lyrics(sample_ttml_lyrics, 'ttml', 'lrc')

            assert result is not None

    def test_convert_srt_to_lrc(self, lyric_manager, sample_srt_lyrics):
        """
        TC-N-019: 测试SRT转LRC

        Args:
            lyric_manager: LyricManager实例
            sample_srt_lyrics: 样本SRT歌词
        """
        with patch('auto_tag.lyric.manager.converter') as mock_converter:
            mock_srt_parser = MagicMock()
            mock_srt_parser.parse = MagicMock(return_value={'lyrics': []})
            mock_lrc_generator = MagicMock()
            mock_lrc_generator.generate = MagicMock(return_value="[00:00.00]test")

            mock_converter.srt = mock_srt_parser
            mock_converter.lrc = mock_lrc_generator

            result = lyric_manager.convert_lyrics(sample_srt_lyrics, 'srt', 'lrc')

            assert result is not None

    def test_convert_json_to_lrc(self, lyric_manager, sample_json_lyrics):
        """
        TC-N-020: 测试JSON转LRC

        Args:
            lyric_manager: LyricManager实例
            sample_json_lyrics: 样本JSON歌词
        """
        with patch('auto_tag.lyric.manager.converter') as mock_converter:
            mock_lrc_generator = MagicMock()
            mock_lrc_generator.generate = MagicMock(return_value="[00:00.00]test")

            mock_converter.lrc = mock_lrc_generator

            result = lyric_manager.convert_lyrics(sample_json_lyrics, 'json', 'lrc')

            assert result is not None

    @patch("auto_tag.lyric.manager.get_provider_api")
    @patch("lrxy.utils.load_audio")
    @patch("lrxy.utils.iter_files")
    def test_batch_fetch_lyrics(
        self, mock_iter_files, mock_load_audio, mock_get_provider_api,
        lyric_manager, temp_audio_file, mock_audio_object
    ):
        """
        TC-N-021: 测试批量获取歌词

        Args:
            mock_iter_files: Mock iter_files函数
            mock_load_audio: Mock load_audio函数
            mock_get_provider_api: Mock get_provider_api函数
            lyric_manager: LyricManager实例
            temp_audio_file: 临时音频文件
            mock_audio_object: Mock音频对象
        """
        mock_provider_api = MagicMock()
        mock_get_provider_api.return_value = mock_provider_api
        mock_load_audio.return_value = mock_audio_object
        mock_iter_files.return_value = [{
            'success': True,
            'data': {
                'plainLyrics': 'Test lyrics',
                'syncedLyrics': '[00:00.00]Test lyrics'
            }
        }]

        file_paths = [temp_audio_file, temp_audio_file]
        results = lyric_manager.batch_fetch_lyrics(file_paths, provider="lrclib")

        assert len(results) == 2
        assert all(result is not None for result in results.values())

    @patch("lrxy.utils.load_audio")
    def test_batch_embed_lyrics(self, mock_load_audio, lyric_manager, temp_audio_file, sample_lrc_lyrics):
        """
        TC-N-022: 测试批量嵌入歌词

        Args:
            mock_load_audio: Mock load_audio函数
            lyric_manager: LyricManager实例
            temp_audio_file: 临时音频文件
            sample_lrc_lyrics: 样本LRC歌词
        """
        mock_audio = MagicMock()
        mock_audio.embed_lyric = MagicMock(return_value=None)
        mock_load_audio.return_value = mock_audio

        file_lyrics_pairs = [
            (temp_audio_file, sample_lrc_lyrics),
            (temp_audio_file, sample_lrc_lyrics)
        ]
        results = lyric_manager.batch_embed_lyrics(file_lyrics_pairs, format='lrc')

        assert len(results) == 2
        assert all(result for result in results.values())


class TestLyricFetchBoundary:
    """
    歌词获取边界条件测试类

    测试歌词获取功能的边界条件和特殊情况
    """

    def _assert_fetch_lyrics_with_suffix(self, lyric_manager, suffix):
        """Create temp file with given suffix and verify fetch_lyrics succeeds.

        Args:
            lyric_manager: LyricManager instance
            suffix: Filename suffix (e.g. '_歌曲名.mp3')
        """
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            temp_file = f.name
            f.write(b"fake mp3 content")

        try:
            with patch("auto_tag.lyric.manager.get_provider_api") as mock_get_provider_api:
                with patch("lrxy.utils.load_audio") as mock_load_audio:
                    with patch("lrxy.utils.iter_files") as mock_iter_files:
                        mock_provider_api = MagicMock()
                        mock_get_provider_api.return_value = mock_provider_api
                        mock_audio = MagicMock()
                        mock_load_audio.return_value = mock_audio
                        mock_iter_files.return_value = [{
                            'success': True,
                            'data': {
                                'plainLyrics': 'Test lyrics',
                                'syncedLyrics': '[00:00.00]Test lyrics'
                            }
                        }]

                        result = lyric_manager.fetch_lyrics(temp_file, provider="lrclib")
                        assert result is not None
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)

    def test_special_characters_in_filename_chinese(self, lyric_manager):
        """TC-B-001: 测试文件名包含中文"""
        self._assert_fetch_lyrics_with_suffix(lyric_manager, "_歌曲名.mp3")

    def test_special_characters_in_filename_japanese(self, lyric_manager):
        """TC-B-002: 测试文件名包含日文"""
        self._assert_fetch_lyrics_with_suffix(lyric_manager, "_花に亡霊.mp3")

    def test_special_characters_in_filename_symbols(self, lyric_manager):
        """TC-B-003: 测试文件名包含特殊符号"""
        self._assert_fetch_lyrics_with_suffix(lyric_manager, "_#test@song$.mp3")

    @patch("lrxy.utils.load_audio")
    def test_lyrics_with_special_characters(self, mock_load_audio, lyric_manager, temp_audio_file):
        """
        TC-B-004: 测试歌词包含特殊字符

        Args:
            mock_load_audio: Mock load_audio函数
            lyric_manager: LyricManager实例
            temp_audio_file: 临时音频文件
        """
        mock_audio = MagicMock()
        mock_audio.embed_lyric = MagicMock(return_value=None)
        mock_load_audio.return_value = mock_audio

        lyrics_with_special_chars = "[00:00.00]🎵花に亡霊🎉\n[00:05.00]夜に駆ける♪"

        result = lyric_manager.embed_lyrics(temp_audio_file, lyrics_with_special_chars, format='lrc')

        assert result is True

    @patch("lrxy.utils.load_audio")
    def test_multilingual_lyrics(self, mock_load_audio, lyric_manager, temp_audio_file):
        """
        TC-B-005: 测试歌词包含多语言

        Args:
            mock_load_audio: Mock load_audio函数
            lyric_manager: LyricManager实例
            temp_audio_file: 临时音频文件
        """
        mock_audio = MagicMock()
        mock_audio.embed_lyric = MagicMock(return_value=None)
        mock_load_audio.return_value = mock_audio

        multilingual_lyrics = "[00:00.00]花に亡霊\n[00:05.00]Ghost In A Flower\n[00:10.00]유령"

        result = lyric_manager.embed_lyrics(temp_audio_file, multilingual_lyrics, format='lrc')

        assert result is True

    def test_empty_audio_file(self, lyric_manager, temp_empty_file):
        """
        TC-B-006: 测试空音频文件

        Args:
            lyric_manager: LyricManager实例
            temp_empty_file: 临时空文件
        """
        with patch("auto_tag.lyric.manager.get_provider_api") as mock_get_provider_api:
            with patch("lrxy.utils.load_audio") as mock_load_audio:
                mock_provider_api = MagicMock()
                mock_get_provider_api.return_value = mock_provider_api
                mock_load_audio.return_value = None

                result = lyric_manager.fetch_lyrics(temp_empty_file, provider="lrclib")

                assert result is None

    @patch("lrxy.utils.load_audio")
    def test_empty_lyrics_content(self, mock_load_audio, lyric_manager, temp_audio_file):
        """
        TC-B-007: 测试空歌词内容

        Args:
            mock_load_audio: Mock load_audio函数
            lyric_manager: LyricManager实例
            temp_audio_file: 临时音频文件
        """
        mock_audio = MagicMock()
        mock_audio.embed_lyric = MagicMock(return_value=None)
        mock_load_audio.return_value = mock_audio

        result = lyric_manager.embed_lyrics(temp_audio_file, "", format='lrc')

        assert result is True

    @patch("lrxy.utils.load_audio")
    def test_very_long_lyrics_text(self, mock_load_audio, lyric_manager, temp_audio_file):
        """
        TC-B-008: 测试超长歌词文本

        Args:
            mock_load_audio: Mock load_audio函数
            lyric_manager: LyricManager实例
            temp_audio_file: 临时音频文件
        """
        mock_audio = MagicMock()
        mock_audio.embed_lyric = MagicMock(return_value=None)
        mock_load_audio.return_value = mock_audio

        long_lyrics = "[00:00.00]" + "测试歌词" * 2000

        result = lyric_manager.embed_lyrics(temp_audio_file, long_lyrics, format='lrc')

        assert result is True

    def test_very_long_filename(self, lyric_manager):
        """TC-B-009: 测试超长文件名"""
        self._assert_fetch_lyrics_with_suffix(lyric_manager, "x" * 200 + ".mp3")

    def test_audio_file_without_metadata(self, lyric_manager, temp_audio_file):
        """
        TC-B-010: 测试无元数据音频文件

        Args:
            lyric_manager: LyricManager实例
            temp_audio_file: 临时音频文件
        """
        with patch("auto_tag.lyric.manager.get_provider_api") as mock_get_provider_api:
            with patch("lrxy.utils.load_audio") as mock_load_audio:
                with patch("lrxy.utils.iter_files") as mock_iter_files:
                    mock_provider_api = MagicMock()
                    mock_get_provider_api.return_value = mock_provider_api
                    mock_audio = MagicMock()
                    mock_audio.title = None
                    mock_audio.artist = None
                    mock_audio.album = None
                    mock_audio.duration = 0
                    mock_load_audio.return_value = mock_audio
                    mock_iter_files.return_value = [{
                        'success': True,
                        'data': {
                            'plainLyrics': 'Test lyrics',
                            'syncedLyrics': '[00:00.00]Test lyrics'
                        }
                    }]

                    result = lyric_manager.fetch_lyrics(temp_audio_file, provider="lrclib")
                    assert result is not None

    def test_zero_duration_audio(self, lyric_manager, temp_audio_file):
        """
        TC-B-011: 测试零时长音频

        Args:
            lyric_manager: LyricManager实例
            temp_audio_file: 临时音频文件
        """
        with patch("auto_tag.lyric.manager.get_provider_api") as mock_get_provider_api:
            with patch("lrxy.utils.load_audio") as mock_load_audio:
                with patch("lrxy.utils.iter_files") as mock_iter_files:
                    mock_provider_api = MagicMock()
                    mock_get_provider_api.return_value = mock_provider_api
                    mock_audio = MagicMock()
                    mock_audio.duration = 0
                    mock_load_audio.return_value = mock_audio
                    mock_iter_files.return_value = [{
                        'success': True,
                        'data': {
                            'plainLyrics': 'Test lyrics',
                            'syncedLyrics': '[00:00.00]Test lyrics'
                        }
                    }]

                    result = lyric_manager.fetch_lyrics(temp_audio_file, provider="lrclib")
                    assert result is not None

    def test_very_long_duration_audio(self, lyric_manager, temp_audio_file):
        """
        TC-B-012: 测试超长音频

        Args:
            lyric_manager: LyricManager实例
            temp_audio_file: 临时音频文件
        """
        with patch("auto_tag.lyric.manager.get_provider_api") as mock_get_provider_api:
            with patch("lrxy.utils.load_audio") as mock_load_audio:
                with patch("lrxy.utils.iter_files") as mock_iter_files:
                    mock_provider_api = MagicMock()
                    mock_get_provider_api.return_value = mock_provider_api
                    mock_audio = MagicMock()
                    mock_audio.duration = 7200
                    mock_load_audio.return_value = mock_audio
                    mock_iter_files.return_value = [{
                        'success': True,
                        'data': {
                            'plainLyrics': 'Test lyrics',
                            'syncedLyrics': '[00:00.00]Test lyrics'
                        }
                    }]

                    result = lyric_manager.fetch_lyrics(temp_audio_file, provider="lrclib")
                    assert result is not None

    @patch("lrxy.utils.load_audio")
    def test_lyrics_timestamp_exceeds_duration(self, mock_load_audio, lyric_manager, temp_audio_file):
        """
        TC-B-013: 测试歌词时间戳超出时长

        Args:
            mock_load_audio: Mock load_audio函数
            lyric_manager: LyricManager实例
            temp_audio_file: 临时音频文件
        """
        mock_audio = MagicMock()
        mock_audio.embed_lyric = MagicMock(return_value=None)
        mock_load_audio.return_value = mock_audio

        lyrics_exceeding = "[00:00.00]Test\n[99:99.99]Exceeds duration"

        result = lyric_manager.embed_lyrics(temp_audio_file, lyrics_exceeding, format='lrc')

        assert result is True


class TestLyricFetchException:
    """
    歌词获取异常处理测试类

    测试歌词获取功能的异常处理能力
    """

    def test_file_not_found(self, lyric_manager):
        """
        TC-E-001: 测试文件不存在

        Args:
            lyric_manager: LyricManager实例
        """
        with pytest.raises(FileNotFoundError):
            lyric_manager.fetch_lyrics("/nonexistent/file.mp3")

    def test_file_permission_denied(self, lyric_manager):
        """
        TC-E-002: 测试文件权限不足

        Args:
            lyric_manager: LyricManager实例
        """
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            temp_file = f.name
            f.write(b"fake mp3 content")

        try:
            os.chmod(temp_file, 0o000)

            with pytest.raises(PermissionError):
                lyric_manager.fetch_lyrics(temp_file)
        finally:
            os.chmod(temp_file, 0o644)
            if os.path.exists(temp_file):
                os.unlink(temp_file)

    def test_corrupted_audio_file(self, lyric_manager, temp_corrupted_file):
        """
        TC-E-003: 测试损坏的音频文件

        Args:
            lyric_manager: LyricManager实例
            temp_corrupted_file: 临时损坏文件
        """
        with patch("auto_tag.lyric.manager.get_provider_api") as mock_get_provider_api:
            with patch("lrxy.utils.load_audio") as mock_load_audio:
                mock_provider_api = MagicMock()
                mock_get_provider_api.return_value = mock_provider_api
                mock_load_audio.return_value = None

                result = lyric_manager.fetch_lyrics(temp_corrupted_file, provider="lrclib")

                assert result is None

    def test_non_audio_file(self, lyric_manager):
        """
        TC-E-004: 测试非音频文件

        Args:
            lyric_manager: LyricManager实例
        """
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            temp_file = f.name
            f.write(b"not an audio file")

        try:
            with patch("auto_tag.lyric.manager.get_provider_api") as mock_get_provider_api:
                with patch("lrxy.utils.load_audio") as mock_load_audio:
                    mock_provider_api = MagicMock()
                    mock_get_provider_api.return_value = mock_provider_api
                    mock_load_audio.return_value = None

                    result = lyric_manager.fetch_lyrics(temp_file, provider="lrclib")

                    assert result is None
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)

    def test_file_locked_by_another_process(self, lyric_manager, temp_audio_file):
        """
        TC-E-005: 测试文件被占用

        Args:
            lyric_manager: LyricManager实例
            temp_audio_file: 临时音频文件
        """
        with patch("auto_tag.lyric.manager.get_provider_api") as mock_get_provider_api:
            with patch("lrxy.utils.load_audio") as mock_load_audio:
                mock_provider_api = MagicMock()
                mock_get_provider_api.return_value = mock_provider_api
                mock_load_audio.side_effect = IOError("File is locked by another process")

                result = lyric_manager.fetch_lyrics(temp_audio_file, provider="lrclib")

                assert result is None

    def test_network_connection_failed(self, lyric_manager, temp_audio_file):
        """
        TC-E-006: 测试网络连接失败

        Args:
            lyric_manager: LyricManager实例
            temp_audio_file: 临时音频文件
        """
        with patch("auto_tag.lyric.manager.get_provider_api") as mock_get_provider_api:
            with patch("lrxy.utils.load_audio") as mock_load_audio:
                with patch("lrxy.utils.iter_files") as mock_iter_files:
                    mock_provider_api = MagicMock()
                    mock_get_provider_api.return_value = mock_provider_api
                    mock_audio = MagicMock()
                    mock_load_audio.return_value = mock_audio
                    mock_iter_files.side_effect = ConnectionError("Network is unreachable")

                    result = lyric_manager.fetch_lyrics(temp_audio_file, provider="lrclib")

                    assert result is None

    def test_api_request_timeout(self, lyric_manager, temp_audio_file):
        """
        TC-E-007: 测试API请求超时

        Args:
            lyric_manager: LyricManager实例
            temp_audio_file: 临时音频文件
        """
        with patch("auto_tag.lyric.manager.get_provider_api") as mock_get_provider_api:
            with patch("lrxy.utils.load_audio") as mock_load_audio:
                with patch("lrxy.utils.iter_files") as mock_iter_files:
                    mock_provider_api = MagicMock()
                    mock_get_provider_api.return_value = mock_provider_api
                    mock_audio = MagicMock()
                    mock_load_audio.return_value = mock_audio
                    mock_iter_files.side_effect = TimeoutError("Request timed out")

                    result = lyric_manager.fetch_lyrics(temp_audio_file, provider="lrclib")

                    assert result is None

    def test_api_rate_limit(self, lyric_manager, temp_audio_file):
        """
        TC-E-008: 测试API限流

        Args:
            lyric_manager: LyricManager实例
            temp_audio_file: 临时音频文件
        """
        with patch("auto_tag.lyric.manager.get_provider_api") as mock_get_provider_api:
            with patch("lrxy.utils.load_audio") as mock_load_audio:
                with patch("lrxy.utils.iter_files") as mock_iter_files:
                    mock_provider_api = MagicMock()
                    mock_get_provider_api.return_value = mock_provider_api
                    mock_audio = MagicMock()
                    mock_load_audio.return_value = mock_audio
                    mock_iter_files.return_value = [{
                        'success': False,
                        'error': 'Rate limit exceeded (429)'
                    }]

                    result = lyric_manager.fetch_lyrics(temp_audio_file, provider="lrclib")

                    assert result is None

    def test_api_returns_invalid_data(self, lyric_manager, temp_audio_file):
        """
        TC-E-009: 测试API返回错误数据

        Args:
            lyric_manager: LyricManager实例
            temp_audio_file: 临时音频文件
        """
        with patch("auto_tag.lyric.manager.get_provider_api") as mock_get_provider_api:
            with patch("lrxy.utils.load_audio") as mock_load_audio:
                with patch("lrxy.utils.iter_files") as mock_iter_files:
                    mock_provider_api = MagicMock()
                    mock_get_provider_api.return_value = mock_provider_api
                    mock_audio = MagicMock()
                    mock_load_audio.return_value = mock_audio
                    mock_iter_files.return_value = [{
                        'success': True,
                        'data': {}
                    }]

                    result = lyric_manager.fetch_lyrics(temp_audio_file, provider="lrclib")

                    assert result is not None
                    assert result['plain_lyrics'] == ''
                    assert result['synced_lyrics'] == ''

    def test_dns_resolution_failed(self, lyric_manager, temp_audio_file):
        """
        TC-E-010: 测试DNS解析失败

        Args:
            lyric_manager: LyricManager实例
            temp_audio_file: 临时音频文件
        """
        with patch("auto_tag.lyric.manager.get_provider_api") as mock_get_provider_api:
            with patch("lrxy.utils.load_audio") as mock_load_audio:
                with patch("lrxy.utils.iter_files") as mock_iter_files:
                    mock_provider_api = MagicMock()
                    mock_get_provider_api.return_value = mock_provider_api
                    mock_audio = MagicMock()
                    mock_load_audio.return_value = mock_audio
                    mock_iter_files.side_effect = Exception("DNS resolution failed")

                    result = lyric_manager.fetch_lyrics(temp_audio_file, provider="lrclib")

                    assert result is None

    def test_invalid_provider_name(self, lyric_manager, temp_audio_file):
        """
        TC-E-011: 测试无效的提供商名称

        Args:
            lyric_manager: LyricManager实例
            temp_audio_file: 临时音频文件
        """
        with pytest.raises(ValueError):
            lyric_manager.fetch_lyrics(temp_audio_file, provider="invalid_provider")

    def test_invalid_lyrics_format(self, lyric_manager, temp_audio_file):
        """
        TC-E-012: 测试无效的歌词格式

        Args:
            lyric_manager: LyricManager实例
            temp_audio_file: 临时音频文件
        """
        with pytest.raises(ValueError):
            lyric_manager.embed_lyrics(temp_audio_file, "lyrics", format="invalid_format")

    def test_invalid_file_path_type(self, lyric_manager):
        """
        TC-E-013: 测试无效的文件路径类型

        Args:
            lyric_manager: LyricManager实例
        """
        with pytest.raises((TypeError, AttributeError)):
            lyric_manager.fetch_lyrics(12345)

    def test_none_parameter(self, lyric_manager):
        """
        TC-E-014: 测试None参数

        Args:
            lyric_manager: LyricManager实例
        """
        with pytest.raises((TypeError, AttributeError)):
            lyric_manager.fetch_lyrics(None)


class TestLyricPerformance:
    """
    歌词功能性能测试类

    测试歌词获取功能的性能表现
    """

    @pytest.mark.skipif(True, reason="pytest-benchmark not installed")
    @patch("auto_tag.lyric.manager.get_provider_api")
    @patch("lrxy.utils.load_audio")
    @patch("lrxy.utils.iter_files")
    def test_fetch_lyrics_response_time(
        self, mock_iter_files, mock_load_audio, mock_get_provider_api,
        lyric_manager, temp_audio_file, mock_audio_object
    ):
        """TC-P-001: 测试单文件歌词获取响应时间 (跳过: 缺少 pytest-benchmark)"""
        mock_provider_api = MagicMock()
        mock_get_provider_api.return_value = mock_provider_api
        mock_load_audio.return_value = mock_audio_object
        mock_iter_files.return_value = [{
            'success': True,
            'data': {
                'plainLyrics': 'Test lyrics',
                'syncedLyrics': '[00:00.00]Test lyrics'
            }
        }]

        result = lyric_manager.fetch_lyrics(temp_audio_file, "lrclib")

        assert result is not None

    @pytest.mark.skipif(True, reason="pytest-benchmark not installed")
    @patch("lrxy.utils.load_audio")
    def test_embed_lyrics_response_time(
        self, mock_load_audio, lyric_manager, temp_audio_file, sample_lrc_lyrics
    ):
        """TC-P-002: 测试单文件歌词嵌入响应时间 (跳过: 缺少 pytest-benchmark)"""
        mock_audio = MagicMock()
        mock_audio.embed_lyric = MagicMock(return_value=None)
        mock_load_audio.return_value = mock_audio

        result = lyric_manager.embed_lyrics(temp_audio_file, sample_lrc_lyrics, 'lrc')

        assert result is True

    @pytest.mark.skipif(True, reason="pytest-benchmark not installed")
    def test_extract_lyrics_response_time(self, lyric_manager, temp_audio_file):
        """TC-P-003: 测试单文件歌词提取响应时间 (跳过: 缺少 pytest-benchmark)"""
        with patch('auto_tag.lyric.manager.eyed3.load') as mock_eyed3_load:
            mock_audio = MagicMock()
            mock_tag = MagicMock()
            mock_lyrics_frame = MagicMock()
            mock_lyrics_frame.text = "[00:00.00]Test lyrics"
            mock_lyrics_frame.lang = "eng"
            mock_tag.lyrics = [mock_lyrics_frame]
            mock_tag.text = []
            mock_audio.tag = mock_tag
            mock_eyed3_load.return_value = mock_audio

            result = lyric_manager.extract_lyrics(temp_audio_file)

            assert result is not None

    @pytest.mark.skipif(True, reason="pytest-benchmark not installed")
    def test_convert_lyrics_response_time(self, lyric_manager, sample_lrc_lyrics):
        """TC-P-004: 测试格式转换响应时间 (跳过: 缺少 pytest-benchmark)"""
        with patch('auto_tag.lyric.manager.converter') as mock_converter:
            mock_lrc_parser = MagicMock()
            mock_lrc_parser.parse = MagicMock(return_value={'lyrics': []})
            mock_ttml_generator = MagicMock()
            mock_ttml_generator.generate = MagicMock(return_value="<tt>test</tt>")

            mock_converter.lrc = mock_lrc_parser
            mock_converter.ttml = mock_ttml_generator

            result = lyric_manager.convert_lyrics(sample_lrc_lyrics, 'lrc', 'ttml')

            assert result is not None


class TestLyricCompatibility:
    """
    歌词功能兼容性测试类

    测试歌词获取功能对不同音频格式和提供商的兼容性
    """

    @patch("auto_tag.lyric.manager.get_provider_api")
    @patch("lrxy.utils.load_audio")
    @patch("lrxy.utils.iter_files")
    def test_mp3_format_support(
        self, mock_iter_files, mock_load_audio, mock_get_provider_api,
        lyric_manager, temp_audio_file, mock_audio_object
    ):
        """
        TC-C-001: 测试MP3格式支持

        Args:
            mock_iter_files: Mock iter_files函数
            mock_load_audio: Mock load_audio函数
            mock_get_provider_api: Mock get_provider_api函数
            lyric_manager: LyricManager实例
            temp_audio_file: 临时音频文件
            mock_audio_object: Mock音频对象
        """
        mock_provider_api = MagicMock()
        mock_get_provider_api.return_value = mock_provider_api
        mock_load_audio.return_value = mock_audio_object
        mock_iter_files.return_value = [{
            'success': True,
            'data': {
                'plainLyrics': 'Test lyrics',
                'syncedLyrics': '[00:00.00]Test lyrics'
            }
        }]

        result = lyric_manager.fetch_lyrics(temp_audio_file, provider="lrclib")

        assert result is not None

    @patch("auto_tag.lyric.manager.get_provider_api")
    @patch("lrxy.utils.load_audio")
    @patch("lrxy.utils.iter_files")
    def test_flac_format_support(
        self, mock_iter_files, mock_load_audio, mock_get_provider_api,
        lyric_manager, temp_flac_file, mock_audio_object
    ):
        """
        TC-C-002: 测试FLAC格式支持

        Args:
            mock_iter_files: Mock iter_files函数
            mock_load_audio: Mock load_audio函数
            mock_get_provider_api: Mock get_provider_api函数
            lyric_manager: LyricManager实例
            temp_flac_file: 临时FLAC文件
            mock_audio_object: Mock音频对象
        """
        mock_provider_api = MagicMock()
        mock_get_provider_api.return_value = mock_provider_api
        mock_load_audio.return_value = mock_audio_object
        mock_iter_files.return_value = [{
            'success': True,
            'data': {
                'plainLyrics': 'Test lyrics',
                'syncedLyrics': '[00:00.00]Test lyrics'
            }
        }]

        result = lyric_manager.fetch_lyrics(temp_flac_file, provider="lrclib")

        assert result is not None

    @patch("auto_tag.lyric.manager.get_provider_api")
    @patch("lrxy.utils.load_audio")
    @patch("lrxy.utils.iter_files")
    def test_ogg_format_support(
        self, mock_iter_files, mock_load_audio, mock_get_provider_api,
        lyric_manager, temp_ogg_file, mock_audio_object
    ):
        """
        TC-C-003: 测试OGG格式支持

        Args:
            mock_iter_files: Mock iter_files函数
            mock_load_audio: Mock load_audio函数
            mock_get_provider_api: Mock get_provider_api函数
            lyric_manager: LyricManager实例
            temp_ogg_file: 临时OGG文件
            mock_audio_object: Mock音频对象
        """
        mock_provider_api = MagicMock()
        mock_get_provider_api.return_value = mock_provider_api
        mock_load_audio.return_value = mock_audio_object
        mock_iter_files.return_value = [{
            'success': True,
            'data': {
                'plainLyrics': 'Test lyrics',
                'syncedLyrics': '[00:00.00]Test lyrics'
            }
        }]

        result = lyric_manager.fetch_lyrics(temp_ogg_file, provider="lrclib")

        assert result is not None

    @patch("auto_tag.lyric.manager.get_provider_api")
    @patch("lrxy.utils.load_audio")
    @patch("lrxy.utils.iter_files")
    def test_m4a_format_support(
        self, mock_iter_files, mock_load_audio, mock_get_provider_api,
        lyric_manager, temp_m4a_file, mock_audio_object
    ):
        """
        TC-C-004: 测试M4A格式支持

        Args:
            mock_iter_files: Mock iter_files函数
            mock_load_audio: Mock load_audio函数
            mock_get_provider_api: Mock get_provider_api函数
            lyric_manager: LyricManager实例
            temp_m4a_file: 临时M4A文件
            mock_audio_object: Mock音频对象
        """
        mock_provider_api = MagicMock()
        mock_get_provider_api.return_value = mock_provider_api
        mock_load_audio.return_value = mock_audio_object
        mock_iter_files.return_value = [{
            'success': True,
            'data': {
                'plainLyrics': 'Test lyrics',
                'syncedLyrics': '[00:00.00]Test lyrics'
            }
        }]

        result = lyric_manager.fetch_lyrics(temp_m4a_file, provider="lrclib")

        assert result is not None

    @pytest.mark.parametrize("provider", ["lrclib", "applemusic", "musixmatch"])
    @patch("auto_tag.lyric.manager.get_provider_api")
    @patch("lrxy.utils.load_audio")
    @patch("lrxy.utils.iter_files")
    def test_provider_compatibility(
        self, mock_iter_files, mock_load_audio, mock_get_provider_api,
        provider, lyric_manager, temp_audio_file, mock_audio_object
    ):
        """
        TC-C-006/007/008: 测试提供商兼容性

        Args:
            mock_iter_files: Mock iter_files函数
            mock_load_audio: Mock load_audio函数
            mock_get_provider_api: Mock get_provider_api函数
            provider: 提供商名称
            lyric_manager: LyricManager实例
            temp_audio_file: 临时音频文件
            mock_audio_object: Mock音频对象
        """
        mock_provider_api = MagicMock()
        mock_get_provider_api.return_value = mock_provider_api
        mock_load_audio.return_value = mock_audio_object
        mock_iter_files.return_value = [{
            'success': True,
            'data': {
                'plainLyrics': 'Test lyrics',
                'syncedLyrics': '[00:00.00]Test lyrics'
            }
        }]

        result = lyric_manager.fetch_lyrics(temp_audio_file, provider=provider)

        assert result is not None
        assert result['provider'] == provider


class TestLyricProvider:
    """
    歌词提供商测试类

    测试提供商配置和API获取功能
    """

    def test_get_provider_valid(self):
        """
        测试获取有效的提供商配置
        """
        provider = get_provider("lrclib")
        assert provider is not None
        assert provider.name == "lrclib"
        assert provider.display_name == "LRCLib"

    def test_get_provider_invalid(self):
        """
        测试获取无效的提供商配置
        """
        provider = get_provider("invalid_provider")
        assert provider is None

    def test_list_providers(self):
        """
        测试获取所有提供商列表
        """
        providers = list_providers()
        assert "lrclib" in providers
        assert "applemusic" in providers
        assert "musixmatch" in providers

    def test_providers_config(self):
        """
        测试提供商配置完整性
        """
        from auto_tag.lyric import PROVIDERS

        for name, provider in PROVIDERS.items():
            assert provider.name == name
            assert provider.display_name
            assert provider.description
            assert provider.api_module
