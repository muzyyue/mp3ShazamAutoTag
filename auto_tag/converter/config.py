# -*- coding: utf-8 -*-
"""
转换配置模块

定义音频转换的配置选项，包括输出格式、质量参数等。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class OutputFormat(Enum):
    """输出音频格式枚举"""
    MP3 = "mp3"
    FLAC = "flac"
    AAC = "aac"
    OGG = "ogg"
    WAV = "wav"
    M4A = "m4a"


class QualityPreset(Enum):
    """质量预设枚举"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    LOSSLESS = "lossless"
    CUSTOM = "custom"


@dataclass
class FormatConfig:
    """
    单个格式的配置
    
    Attributes:
        format: 输出格式
        bitrate: 比特率（kbps），适用于有损格式
        sample_rate: 采样率（Hz）
        channels: 声道数
        codec: 编解码器名称
    """
    format: OutputFormat = OutputFormat.MP3
    bitrate: Optional[int] = None
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    codec: Optional[str] = None
    smart_bitrate: bool = True
    
    def __post_init__(self):
        """初始化后设置默认值"""
        self._apply_quality_preset(QualityPreset.HIGH)
    
    def _apply_quality_preset(self, preset: QualityPreset) -> None:
        """
        应用质量预设
        
        Args:
            preset: 质量预设枚举值
        """
        if self.format == OutputFormat.MP3:
            if preset == QualityPreset.LOW:
                self.bitrate = 128
                self.sample_rate = 44100
                self.codec = "libmp3lame"
            elif preset == QualityPreset.MEDIUM:
                self.bitrate = 192
                self.sample_rate = 44100
                self.codec = "libmp3lame"
            elif preset == QualityPreset.HIGH:
                self.bitrate = 256
                self.sample_rate = 44100
                self.codec = "libmp3lame"
            elif preset == QualityPreset.LOSSLESS:
                self.bitrate = 320
                self.sample_rate = 44100
                self.codec = "libmp3lame"
        
        elif self.format == OutputFormat.FLAC:
            self.bitrate = None
            self.sample_rate = 44100
            self.codec = "flac"
        
        elif self.format == OutputFormat.AAC:
            if preset == QualityPreset.LOW:
                self.bitrate = 96
                self.sample_rate = 44100
                self.codec = "aac"
            elif preset == QualityPreset.MEDIUM:
                self.bitrate = 128
                self.sample_rate = 44100
                self.codec = "aac"
            elif preset == QualityPreset.HIGH:
                self.bitrate = 160
                self.sample_rate = 44100
                self.codec = "aac"
            elif preset == QualityPreset.LOSSLESS:
                self.bitrate = 192
                self.sample_rate = 44100
                self.codec = "aac"
        
        elif self.format == OutputFormat.OGG:
            if preset == QualityPreset.LOW:
                self.bitrate = 96
                self.sample_rate = 44100
                self.codec = "libvorbis"
            elif preset == QualityPreset.MEDIUM:
                self.bitrate = 128
                self.sample_rate = 44100
                self.codec = "libvorbis"
            elif preset == QualityPreset.HIGH:
                self.bitrate = 160
                self.sample_rate = 44100
                self.codec = "libvorbis"
            elif preset == QualityPreset.LOSSLESS:
                self.bitrate = 192
                self.sample_rate = 44100
                self.codec = "libvorbis"
        
        elif self.format == OutputFormat.WAV:
            self.bitrate = None
            self.sample_rate = 44100
            self.codec = "pcm_s16le"
        
        elif self.format == OutputFormat.M4A:
            if preset == QualityPreset.LOW:
                self.bitrate = 96
                self.sample_rate = 44100
                self.codec = "aac"
            elif preset == QualityPreset.MEDIUM:
                self.bitrate = 128
                self.sample_rate = 44100
                self.codec = "aac"
            elif preset == QualityPreset.HIGH:
                self.bitrate = 160
                self.sample_rate = 44100
                self.codec = "aac"
            elif preset == QualityPreset.LOSSLESS:
                self.bitrate = 192
                self.sample_rate = 44100
                self.codec = "aac"


@dataclass
class ConverterConfig:
    """
    转换器配置类
    
    管理音频转换的所有配置选项。
    
    Attributes:
        output_format: 输出格式配置
        output_directory: 输出目录路径
        quality_preset: 质量预设
        preserve_metadata: 是否保留原始元数据
        overwrite_existing: 是否覆盖已存在的文件
        filename_template: 文件名模板
        supported_input_formats: 支持的输入格式列表
    """
    output_format: FormatConfig = field(default_factory=lambda: FormatConfig(format=OutputFormat.MP3))
    output_directory: Optional[str] = None
    quality_preset: QualityPreset = QualityPreset.HIGH
    preserve_metadata: bool = True
    overwrite_existing: bool = False
    id3_version: str = "2.3"
    filename_template: str = "{artist} - {title}"
    supported_input_formats: list[str] = field(default_factory=lambda: [
        "mp3", "flac", "aac", "ogg", "wav", "m4a",
        "mp4", "mkv", "avi", "mov", "wmv", "webm"
    ])
    
    def set_output_format(self, format_name: str, preset: QualityPreset = QualityPreset.HIGH) -> None:
        """
        设置输出格式
        
        Args:
            format_name: 格式名称（mp3, flac, aac 等）
            preset: 质量预设
        """
        try:
            output_format = OutputFormat(format_name.lower())
            self.output_format = FormatConfig(format=output_format)
            self.output_format._apply_quality_preset(preset)
            self.quality_preset = preset
        except ValueError:
            raise ValueError(f"不支持的输出格式: {format_name}")
    
    def get_ffmpeg_args(self) -> list[str]:
        """
        获取 FFmpeg 命令行参数
        
        Returns:
            list[str]: FFmpeg 参数列表
        """
        args = []
        
        if self.output_format.codec:
            args.extend(["-c:a", self.output_format.codec])
        
        if self.output_format.bitrate:
            args.extend(["-b:a", f"{self.output_format.bitrate}k"])
        
        if self.output_format.sample_rate:
            args.extend(["-ar", str(self.output_format.sample_rate)])
        
        if self.output_format.channels:
            args.extend(["-ac", str(self.output_format.channels)])
        
        # ID3 标签版本 (仅 MP3 输出有效, 控制 MP3 标签产出版本)
        # 默认 ID3v2.3 以兼容 Windows 资源管理器封面预览; 可选 ID3v2.4
        if self.output_format.format == OutputFormat.MP3:
            if self.id3_version == "2.4":
                args.extend(["-id3v2_version", "4"])
            else:
                args.extend(["-id3v2_version", "3"])
        
        return args
    
    def get_output_extension(self) -> str:
        """
        获取输出文件扩展名
        
        Returns:
            str: 文件扩展名（包含点号）
        """
        return f".{self.output_format.format.value}"
