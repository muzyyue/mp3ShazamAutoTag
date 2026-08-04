# -*- coding: utf-8 -*-
"""
音频转换模块的单元测试

测试覆盖：
- AudioConverter 类：格式检测、文件转换、批量转换
- MetadataManager 类：元数据读取、写入、文件名解析、批量编辑
- ConverterConfig 类：配置管理、FFmpeg 参数生成
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from auto_tag.converter import AudioConverter, ConverterConfig
from auto_tag.converter.config import OutputFormat, QualityPreset
from auto_tag.converter.metadata_manager import MetadataManager


class TestAudioConverter:
    """AudioConverter 类测试"""
    
    @pytest.fixture
    def converter(self):
        """创建 AudioConverter 实例"""
        return AudioConverter()
    
    @pytest.fixture
    def config(self):
        """创建默认配置"""
        return ConverterConfig()
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_supported_formats(self, converter):
        """测试支持的格式列表"""
        # 检查输入格式
        assert "mp3" in converter.SUPPORTED_INPUT_FORMATS
        assert "flac" in converter.SUPPORTED_INPUT_FORMATS
        assert "mp4" in converter.SUPPORTED_INPUT_FORMATS
        assert "mkv" in converter.SUPPORTED_INPUT_FORMATS
        
        # 检查输出格式
        assert "mp3" in converter.SUPPORTED_OUTPUT_FORMATS
        assert "flac" in converter.SUPPORTED_OUTPUT_FORMATS
        assert "mp4" not in converter.SUPPORTED_OUTPUT_FORMATS
    
    def test_detect_format_nonexistent_file(self, converter):
        """测试检测不存在的文件格式"""
        result = converter.detect_format("nonexistent_file.mp3")
        assert result is None
    
    def test_convert_file_nonexistent_input(self, converter, config, temp_dir):
        """测试转换不存在的文件"""
        output_path = os.path.join(temp_dir, "output.mp3")
        result = converter.convert_file("nonexistent.mp3", output_path, config)
        assert result is False
    
    def test_convert_file_unsupported_output_format(self, converter, config, temp_dir):
        """测试不支持的输出格式"""
        # 创建一个临时测试文件
        input_path = os.path.join(temp_dir, "test.txt")
        Path(input_path).touch()
        
        output_path = os.path.join(temp_dir, "output.mp3")
        
        # 由于文件格式不支持，应该返回 False
        result = converter.convert_file(input_path, output_path, config)
        assert result is False
    
    def test_parse_ffmpeg_args(self, converter):
        """测试解析 FFmpeg 参数"""
        args = ['-c:a', 'libmp3lame', '-b:a', '320k', '-ar', '48000']
        result = converter._parse_ffmpeg_args(args)
        
        assert result['c:a'] == 'libmp3lame'
        assert result['b:a'] == '320k'
        assert result['ar'] == '48000'
    
    def test_config_get_ffmpeg_args(self, config):
        """测试配置获取 FFmpeg 参数"""
        args = config.get_ffmpeg_args()
        
        # 默认配置是 MP3 格式
        assert '-c:a' in args
        assert 'libmp3lame' in args
        assert '-b:a' in args
    
    def test_config_set_output_format(self, config):
        """测试设置输出格式"""
        config.set_output_format("flac", QualityPreset.LOSSLESS)
        
        assert config.output_format.format == OutputFormat.FLAC
        assert config.output_format.codec == "flac"
    
    def test_config_get_output_extension(self, config):
        """测试获取输出扩展名"""
        config.set_output_format("mp3")
        assert config.get_output_extension() == ".mp3"
        
        config.set_output_format("flac")
        assert config.get_output_extension() == ".flac"
    
    def test_convert_batch_empty_list(self, converter, config, temp_dir):
        """测试批量转换空列表"""
        results = converter.convert_batch([], temp_dir, config)
        assert results == {}
    
    def test_convert_batch_nonexistent_files(self, converter, config, temp_dir):
        """测试批量转换不存在的文件"""
        files = ["nonexistent1.mp3", "nonexistent2.mp3"]
        results = converter.convert_batch(files, temp_dir, config)
        
        assert len(results) == 2
        assert all(not success for success in results.values())
    
    def test_progress_callback(self, converter, config, temp_dir):
        """测试进度回调功能"""
        # 创建一个临时测试文件
        input_path = os.path.join(temp_dir, "test.txt")
        Path(input_path).touch()
        
        output_path = os.path.join(temp_dir, "output.mp3")
        
        progress_values = []
        
        def callback(progress: float):
            progress_values.append(progress)
        
        # 由于文件格式不支持，转换会失败，但不会抛出异常
        result = converter.convert_file(input_path, output_path, config, callback)
        assert result is False


class TestConverterConfig:
    """ConverterConfig 类测试"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = ConverterConfig()
        
        assert config.output_format.format == OutputFormat.MP3
        assert config.quality_preset == QualityPreset.HIGH
        assert config.preserve_metadata is True
        assert config.overwrite_existing is False
        assert config.id3_version == "2.3"

    def test_id3_version_default_ffmpeg_args(self):
        """测试默认 ID3v2.3 时 MP3 输出带 -id3v2_version 3"""
        config = ConverterConfig()
        assert config.id3_version == "2.3"
        args = config.get_ffmpeg_args()
        assert '-id3v2_version' in args
        assert args[args.index('-id3v2_version') + 1] == '3'

    def test_id3_version_v24_ffmpeg_args(self):
        """测试 ID3v2.4 时 MP3 输出带 -id3v2_version 4"""
        config = ConverterConfig()
        config.id3_version = "2.4"
        args = config.get_ffmpeg_args()
        assert '-id3v2_version' in args
        assert args[args.index('-id3v2_version') + 1] == '4'

    def test_id3_version_not_applied_to_non_mp3(self):
        """测试非 MP3 输出不带 -id3v2_version 参数"""
        config = ConverterConfig()
        config.set_output_format("flac", QualityPreset.HIGH)
        args = config.get_ffmpeg_args()
        assert '-id3v2_version' not in args
    
    def test_quality_presets(self):
        """测试质量预设"""
        config = ConverterConfig()
        
        # 测试 LOW 预设
        config.set_output_format("mp3", QualityPreset.LOW)
        assert config.output_format.bitrate == 128
        
        # 测试 MEDIUM 预设
        config.set_output_format("mp3", QualityPreset.MEDIUM)
        assert config.output_format.bitrate == 192
        
        # 测试 HIGH 预设
        config.set_output_format("mp3", QualityPreset.HIGH)
        assert config.output_format.bitrate == 256
        
        # 测试 LOSSLESS 预设
        config.set_output_format("mp3", QualityPreset.LOSSLESS)
        assert config.output_format.bitrate == 320
    
    def test_flac_config(self):
        """测试 FLAC 格式配置"""
        config = ConverterConfig()
        config.set_output_format("flac", QualityPreset.LOSSLESS)
        
        assert config.output_format.format == OutputFormat.FLAC
        assert config.output_format.codec == "flac"
        assert config.output_format.bitrate is None  # FLAC 无损，无比特率
    
    def test_unsupported_format(self):
        """测试不支持的格式"""
        config = ConverterConfig()
        
        with pytest.raises(ValueError, match="不支持的输出格式"):
            config.set_output_format("xyz")


class TestMetadataManager:
    """MetadataManager 类测试"""
    
    @pytest.fixture
    def manager(self):
        """创建 MetadataManager 实例"""
        return MetadataManager()
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_parse_filename_three_parts(self, manager):
        """
        测试解析三段式文件名
        
        格式: "Artist - Title - Album"
        """
        filename = "The Beatles - Drive My Car - Rubber Soul.mp3"
        result = manager.parse_filename(filename)
        
        assert result['artist'] == "The Beatles"
        assert result['title'] == "Drive My Car"
        assert result['album'] == "Rubber Soul"
    
    def test_parse_filename_two_parts(self, manager):
        """
        测试解析两段式文件名
        
        格式: "Artist - Title"
        """
        filename = "Evanescence - Bring Me To Life.ogg"
        result = manager.parse_filename(filename)
        
        assert result['artist'] == "Evanescence"
        assert result['title'] == "Bring Me To Life"
        assert result['album'] == ""
    
    def test_parse_filename_single_part(self, manager):
        """
        测试解析单段文件名
        
        无法解析时，使用整个文件名作为标题
        """
        filename = "Unknown Song.mp3"
        result = manager.parse_filename(filename)
        
        assert result['title'] == "Unknown Song"
        assert result['artist'] == ""
        assert result['album'] == ""
    
    def test_parse_filename_with_spaces(self, manager):
        """
        测试解析带空格的文件名
        
        确保正确处理空格
        """
        filename = "  Artist  -  Title  -  Album  .mp3"
        result = manager.parse_filename(filename)
        
        assert result['artist'] == "Artist"
        assert result['title'] == "Title"
        assert result['album'] == "Album"
    
    @patch('auto_tag.converter.metadata_manager.eyed3.load')
    def test_read_metadata_mp3(self, mock_load, manager, temp_dir):
        """
        测试读取 MP3 文件元数据
        
        使用 mock 模拟 eyed3.load 返回值
        """
        # 创建测试文件
        file_path = os.path.join(temp_dir, "test.mp3")
        Path(file_path).touch()
        
        # Mock eyed3.load 返回值
        mock_audio = MagicMock()
        mock_tag = MagicMock()
        mock_tag.title = "Test Title"
        mock_tag.artist = "Test Artist"
        mock_tag.album = "Test Album"
        mock_tag.recording_date = 2023
        mock_genre = MagicMock()
        mock_genre.name = "Rock"
        mock_tag.genre = mock_genre
        mock_tag.images = []
        mock_audio.tag = mock_tag
        mock_load.return_value = mock_audio
        
        # 执行测试
        metadata = manager.read_metadata(file_path)
        
        assert metadata['title'] == "Test Title"
        assert metadata['artist'] == "Test Artist"
        assert metadata['album'] == "Test Album"
        assert metadata['year'] == "2023"
        assert metadata['genre'] == "Rock"
    
    @patch('auto_tag.converter.metadata_manager.eyed3.load')
    def test_read_metadata_mp3_no_tag(self, mock_load, manager, temp_dir):
        """
        测试读取无标签的 MP3 文件
        
        返回空元数据
        """
        # 创建测试文件
        file_path = os.path.join(temp_dir, "test.mp3")
        Path(file_path).touch()
        
        # Mock eyed3.load 返回无标签的音频对象
        mock_audio = MagicMock()
        mock_audio.tag = None
        mock_load.return_value = mock_audio
        
        # 执行测试
        metadata = manager.read_metadata(file_path)
        
        assert metadata['title'] == ""
        assert metadata['artist'] == ""
        assert metadata['album'] == ""
    
    @patch('auto_tag.converter.metadata_manager.OggVorbis')
    def test_read_metadata_ogg(self, mock_ogg, manager, temp_dir):
        """
        测试读取 OGG 文件元数据
        
        使用 mock 模拟 OggVorbis 返回值
        """
        # 创建测试文件
        file_path = os.path.join(temp_dir, "test.ogg")
        Path(file_path).touch()
        
        # Mock OggVorbis 返回值
        mock_audio = MagicMock()
        mock_audio.get = lambda key, default: {
            'TITLE': ['Test Title'],
            'ARTIST': ['Test Artist'],
            'ALBUM': ['Test Album'],
            'DATE': ['2023'],
            'GENRE': ['Rock']
        }.get(key, default)
        mock_audio.__contains__ = lambda self, key: key in ['TITLE', 'ARTIST', 'ALBUM', 'DATE', 'GENRE']
        mock_ogg.return_value = mock_audio
        
        # 执行测试
        metadata = manager.read_metadata(file_path)
        
        assert metadata['title'] == "Test Title"
        assert metadata['artist'] == "Test Artist"
        assert metadata['album'] == "Test Album"
        assert metadata['year'] == "2023"
        assert metadata['genre'] == "Rock"
    
    def test_read_metadata_nonexistent_file(self, manager):
        """
        测试读取不存在的文件
        
        应该抛出 FileNotFoundError
        """
        with pytest.raises(FileNotFoundError, match="文件不存在"):
            manager.read_metadata("nonexistent.mp3")
    
    def test_read_metadata_unsupported_format(self, manager, temp_dir):
        """
        测试读取不支持的格式
        
        应该抛出 ValueError
        """
        # 创建测试文件
        file_path = os.path.join(temp_dir, "test.xyz")
        Path(file_path).touch()
        
        with pytest.raises(ValueError, match="不支持的文件格式"):
            manager.read_metadata(file_path)
    
    @patch('auto_tag.converter.metadata_manager.eyed3.load')
    def test_write_metadata_mp3(self, mock_load, manager, temp_dir):
        """
        测试写入 MP3 文件元数据
        
        使用 mock 模拟 eyed3 操作
        """
        # 创建测试文件
        file_path = os.path.join(temp_dir, "test.mp3")
        Path(file_path).touch()
        
        # Mock eyed3.load 返回值
        mock_audio = MagicMock()
        mock_tag = MagicMock()
        mock_audio.tag = mock_tag
        mock_audio.initTag = MagicMock()
        mock_load.return_value = mock_audio
        
        # 执行测试
        metadata = {
            'title': 'New Title',
            'artist': 'New Artist',
            'album': 'New Album',
            'year': '2024',
            'genre': 'Pop'
        }
        result = manager.write_metadata(file_path, metadata)
        
        assert result is True
        assert mock_tag.title == 'New Title'
        assert mock_tag.artist == 'New Artist'
        assert mock_tag.album == 'New Album'
        mock_tag.save.assert_called_once()
    
    @patch('auto_tag.converter.metadata_manager.OggVorbis')
    def test_write_metadata_ogg(self, mock_ogg, manager, temp_dir):
        """
        测试写入 OGG 文件元数据
        
        使用 mock 模拟 OggVorbis 操作
        """
        # 创建测试文件
        file_path = os.path.join(temp_dir, "test.ogg")
        Path(file_path).touch()
        
        # Mock OggVorbis 返回值
        mock_audio = MagicMock()
        mock_ogg.return_value = mock_audio
        
        # 执行测试
        metadata = {
            'title': 'New Title',
            'artist': 'New Artist',
            'album': 'New Album',
            'year': '2024',
            'genre': 'Pop'
        }
        result = manager.write_metadata(file_path, metadata)
        
        assert result is True
        mock_audio.__setitem__.assert_called()
        mock_audio.save.assert_called_once()
    
    def test_write_metadata_nonexistent_file(self, manager):
        """
        测试写入不存在的文件
        
        应该返回 False
        """
        metadata = {'title': 'Test'}
        result = manager.write_metadata("nonexistent.mp3", metadata)
        
        assert result is False
    
    @patch('auto_tag.converter.metadata_manager.eyed3.load')
    def test_batch_edit_success(self, mock_load, manager, temp_dir):
        """
        测试批量编辑元数据
        
        所有文件都成功
        """
        # 创建测试文件
        file_paths = []
        for i in range(3):
            file_path = os.path.join(temp_dir, f"test{i}.mp3")
            Path(file_path).touch()
            file_paths.append(file_path)
        
        # Mock eyed3.load 返回值
        mock_audio = MagicMock()
        mock_tag = MagicMock()
        mock_audio.tag = mock_tag
        mock_load.return_value = mock_audio
        
        # 执行测试
        metadata = {'title': 'Batch Title', 'artist': 'Batch Artist'}
        results = manager.batch_edit(file_paths, metadata)
        
        assert len(results) == 3
        assert all(results.values())
    
    @patch('auto_tag.converter.metadata_manager.eyed3.load')
    def test_batch_edit_partial_failure(self, mock_load, manager, temp_dir):
        """
        测试批量编辑部分失败的情况
        
        部分文件失败不影响其他文件
        """
        # 创建测试文件
        file_paths = []
        for i in range(3):
            file_path = os.path.join(temp_dir, f"test{i}.mp3")
            Path(file_path).touch()
            file_paths.append(file_path)
        
        # Mock eyed3.load 返回值，第二个文件返回 None
        mock_audio = MagicMock()
        mock_tag = MagicMock()
        mock_audio.tag = mock_tag
        
        def load_side_effect(path):
            if "test1.mp3" in path:
                return None  # 第二个文件失败
            return mock_audio
        
        mock_load.side_effect = load_side_effect
        
        # 执行测试
        metadata = {'title': 'Batch Title'}
        results = manager.batch_edit(file_paths, metadata)
        
        assert len(results) == 3
        assert results[file_paths[0]] is True
        assert results[file_paths[1]] is False
        assert results[file_paths[2]] is True
    
    @patch('auto_tag.converter.metadata_manager.eyed3.load')
    def test_get_cover_mp3(self, mock_load, manager, temp_dir):
        """
        测试获取 MP3 文件封面
        
        使用 mock 模拟封面图片
        """
        # 创建测试文件
        file_path = os.path.join(temp_dir, "test.mp3")
        Path(file_path).touch()
        
        # Mock eyed3.load 返回值
        mock_audio = MagicMock()
        mock_tag = MagicMock()
        mock_image = MagicMock()
        mock_image.picture_type = 3  # Front cover
        mock_image.image_data = b'fake_image_data'
        mock_tag.images = [mock_image]
        mock_audio.tag = mock_tag
        mock_load.return_value = mock_audio
        
        # 执行测试
        cover = manager.get_cover(file_path)
        
        assert cover == b'fake_image_data'
    
    @patch('auto_tag.converter.metadata_manager.eyed3.load')
    def test_set_cover_mp3(self, mock_load, manager, temp_dir):
        """
        测试设置 MP3 文件封面
        
        使用 mock 模拟封面设置操作
        """
        # 创建测试文件
        file_path = os.path.join(temp_dir, "test.mp3")
        Path(file_path).touch()
        
        # Mock eyed3.load 返回值
        mock_audio = MagicMock()
        mock_tag = MagicMock()
        mock_audio.tag = mock_tag
        mock_audio.initTag = MagicMock()
        mock_load.return_value = mock_audio
        
        # 执行测试
        cover_data = b'\xff\xd8\xff\xe0'  # JPEG 文件头
        result = manager.set_cover(file_path, cover_data)
        
        assert result is True
        mock_tag.images.set.assert_called_once()
        mock_tag.save.assert_called_once()
