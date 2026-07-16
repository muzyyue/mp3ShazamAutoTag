# -*- coding: utf-8 -*-
"""
音频编辑器核心模块

提供专业的音频编辑功能，包括：
- 智能音频裁剪（自动静音检测/手动时间选择/指定时长）
- 音量标准化（基于 EBU R128 loudnorm 滤镜）
- 音频信息获取（时长/采样率/声道数/响度等）

基于 FFmpeg 实现，支持多种音频格式。

使用示例：
>>> editor = AudioEditor()
>>> result = editor.trim_audio("input.mp3", "output.mp3", start_time=10.0, end_time=180.0)
>>> info = editor.get_audio_info("song.mp3")
"""

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import ffmpeg

from auto_tag.editor.config import EditorConfig, NormalizeConfig, OutputQuality, TrimConfig, TrimMode
from auto_tag.converter.config import ConverterConfig, FormatConfig, OutputFormat, QualityPreset
# 为避免命名冲突，将 converter 的 QualityPreset 别名为 ConvQualityPreset
ConvQualityPreset = QualityPreset
from auto_tag.utils.ffmpeg_utils import get_silent_process_kwargs

logger = logging.getLogger(__name__)


class AudioEditor:
    """音频编辑器核心类"""

    def __init__(self) -> None:
        """初始化编辑器，检查 FFmpeg 可用性"""
        self._check_ffmpeg_available()

    def _check_ffmpeg_available(self) -> None:
        """检查 FFmpeg 是否已安装并可用"""
        try:
            ffmpeg.run(ffmpeg.probe("dummy"), quiet=True, overwrite_output=True)
        except ffmpeg.Error:
            pass
        except FileNotFoundError:
            raise RuntimeError(
                "FFmpeg 未安装或不在系统 PATH 中。请安装 FFmpeg 后重试。\n"
                "Windows: 从 https://ffmpeg.org/download.html 下载并添加到 PATH\n"
                "Linux: sudo apt install ffmpeg\n"
                "macOS: brew install ffmpeg"
            )

    @staticmethod
    def _has_special_chars(file_path: str) -> bool:
        """
        检查文件路径是否包含 FFmpeg 特殊字符
        
        FFmpeg 将以下字符解释为特殊语法：
        - [] 流选择器（如 [0:a]）
        - : 协议分隔符（如 file:）
        - ; 选项分隔符
        - = 赋值符
        
        Args:
            file_path: 文件路径
            
        Returns:
            bool: 是否包含特殊字符
        """
        special_chars = set('[]:;=')
        return any(c in os.path.basename(file_path) for c in special_chars)
    
    @staticmethod
    def _create_safe_temp_link(original_path: str) -> tuple:
        """
        为含特殊字符的文件创建临时符号链接（或硬链接/复制作为回退）
        
        当文件名包含 FFmpeg 特殊字符时，创建一个安全的临时链接，
        使用该安全路径调用 FFmpeg，避免特殊字符解析问题。
        
        Args:
            original_path: 原始文件路径
            
        Returns:
            tuple: (safe_temp_path, cleanup_func)
                   - safe_temp_path: 安全的临时路径（无特殊字符）
                   - cleanup_func: 清理函数（调用后删除临时文件）
        """
        import tempfile
        
        # 生成安全的临时文件名（保留原始扩展名）
        original_ext = os.path.splitext(original_path)[1]
        temp_dir = tempfile.gettempdir()
        safe_name = f"imusic_safe_{os.getpid()}_{id(original_path)}{original_ext}"
        safe_path = os.path.join(temp_dir, safe_name)
        
        # 如果已存在则先清理（防止冲突）
        if os.path.exists(safe_path):
            try:
                os.unlink(safe_path)
            except OSError:
                pass
        
        # 策略1：尝试硬链接（快速，但需要同一文件系统）
        # 注意：Windows 上符号链接需要管理员权限，不可靠，直接跳过
        try:
            os.link(original_path, safe_path)
            
            # 验证硬链接是否真的创建成功
            if not os.path.exists(safe_path):
                raise OSError("硬链接创建后文件不存在")
            
            logger.debug(f"创建硬链接: {original_path} -> {safe_path}")
            
            def cleanup():
                try:
                    if os.path.exists(safe_path):
                        os.unlink(safe_path)
                except OSError:
                    pass
            
            return safe_path, cleanup
            
        except OSError as link_error:
            logger.debug(f"硬链接失败: {link_error}，使用文件复制")
        
        # 策略3：复制文件（最慢但最可靠）
        import shutil
        try:
            shutil.copy2(original_path, safe_path)
            
            # 验证复制是否成功
            if not os.path.exists(safe_path):
                raise OSError(f"复制后目标文件不存在: {safe_path}")
            
            original_size = os.path.getsize(original_path)
            copied_size = os.path.getsize(safe_path)
            logger.debug(f"复制文件: {original_path} -> {safe_path} ({copied_size/1024/1024:.2f} MB)")
            
        except Exception as copy_error:
            logger.error(f"文件复制失败: {copy_error}")
            raise RuntimeError(
                f"无法为含特殊字符的文件创建安全副本。\n"
                f"原始路径: {original_path}\n"
                f"尝试的方案: 符号链接 → 硬链接 → 文件复制\n"
                f"最后错误: {copy_error}"
            ) from copy_error
        
        def cleanup():
            try:
                if os.path.exists(safe_path):
                    os.unlink(safe_path)
            except OSError:
                pass
        
        return safe_path, cleanup
    
    @staticmethod
    def _safe_path(file_path: str) -> str:
        """
        处理文件路径中的特殊字符，确保 FFmpeg 能正确处理

        Windows 命令行中以下字符需要特殊处理：
        - 方括号 []: 被解释为通配符
        - 括号 (): 被解释为命令分组
        - 百分号 %: 被解释为环境变量
        - 空格、&、^、|、<、>: 特殊命令符号

        Args:
            file_path: 原始文件路径

        Returns:
            str: 安全的文件路径（绝对路径格式）
        """
        # 转换为绝对路径并使用正斜杠（FFmpeg 兼容）
        abs_path = os.path.abspath(file_path)
        # 在Windows上使用正斜杠，避免反斜杠转义问题
        safe = abs_path.replace('\\', '/')
        return safe
    
    @staticmethod
    def _optimize_mp3_bitrate(input_bitrate: int) -> int:
        """
        根据输入文件比特率优化 MP3 输出质量参数 (VBR)
        
        使用 VBR (可变比特率) 而非 CBR (固定比特率)，
        在保持音质的同时最小化文件体积。
        
        VBR 质量等级 (q:a):
        - 0: 最高质量 (~220-250 kbps)
        - 2: 高质量 (~170-210 kbps) ← 推荐，透明质量
        - 4: 中等质量 (~130-160 kbps)
        - 6: 较低质量 (~100-120 kbps)
        - 9: 最低质量 (~65-80 kbps)
        
        Args:
            input_bitrate: 输入文件的比特率 (bps)
            
        Returns:
            int: VBR 质量等级 (0-9)
        """
        if input_bitrate <= 0:
            return 2  # 默认高质量
        
        # 将 bps 转换为 kbps
        kbps = input_bitrate / 1000
        
        # 根据输入比特率选择合适的 VBR 质量
        if kbps >= 256:
            return 0   # 高比特率输入 → 最高质量
        elif kbps >= 192:
            return 1   # 接近 CD 质量
        elif kbps >= 128:
            return 2   # 标准 MP3 质量（推荐）
        elif kbps >= 96:
            return 4   # 中等质量
        else:
            return 6   # 低比特率输入 → 节省空间
    
    @staticmethod
    def _run_ffmpeg_safe(ffmpeg_output) -> None:
        """
        安全执行 FFmpeg 命令，绕过 Windows shell 的特殊字符解释

        使用 shell=False 并手动构建参数列表，
        避免方括号、括号等特殊字符被命令行解析器误解。
        自动隐藏 Windows CMD 窗口。

        Args:
            ffmpeg_output: ffmpeg.output() 返回的对象
        """
        # 编译 FFmpeg 命令为参数列表（不通过 shell）
        cmd = ffmpeg_output.compile()

        # 确保 FFmpeg 使用完整路径（Windows shell=False 需要）
        import shutil
        ffmpeg_path = shutil.which('ffmpeg')
        if ffmpeg_path and cmd:
            cmd[0] = ffmpeg_path

        logger.debug(f"FFmpeg 命令: {' '.join(cmd)}")

        # 使用静默参数执行（隐藏CMD窗口）
        kwargs = get_silent_process_kwargs()
        kwargs['shell'] = False  # 关键：禁用 shell，避免特殊字符问题

        process = subprocess.Popen(cmd, **kwargs)
        _, stderr = process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode('utf-8', errors='ignore') if stderr else ''
            raise ffmpeg.Error('ffmpeg', None, error_msg)

    @staticmethod
    def _run_ffmpeg_safe_capture(ffmpeg_output) -> tuple:
        """
        安全执行 FFmpeg 命令并捕获输出（用于 loudnorm 等需要解析输出的场景）
        自动隐藏 Windows CMD 窗口。

        Args:
            ffmpeg_output: ffmpeg.output() 返回的对象

        Returns:
            tuple: (stdout_bytes, stderr_bytes)
        """
        cmd = ffmpeg_output.compile()

        # 确保 FFmpeg 使用完整路径（Windows shell=False 需要）
        import shutil
        ffmpeg_path = shutil.which('ffmpeg')
        if ffmpeg_path and cmd:
            cmd[0] = ffmpeg_path

        logger.debug(f"FFmpeg 命令 (capture): {' '.join(cmd)}")

        # 使用静默参数执行（隐藏CMD窗口）
        kwargs = get_silent_process_kwargs()
        kwargs['shell'] = False

        process = subprocess.Popen(cmd, **kwargs)
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode('utf-8', errors='ignore') if stderr else ''
            raise ffmpeg.Error('ffmpeg', stdout, error_msg)

        return stdout, stderr

    # ── 裁剪模式处理器 ──────────────────────────────────────────────

    @staticmethod
    def _build_auto_trim_filter(input_stream, config: TrimConfig):
        """
        构建自动裁剪滤镜（静音检测）

        使用 silenceremove 滤镜自动移除音频首尾的静音部分。

        Args:
            input_stream: ffmpeg 输入流
            config: 裁剪配置（使用 silence_threshold 和 min_silence_duration）

        Returns:
            ffmpeg.Stream: 应用滤镜后的音频流
        """
        # 使用关键字参数避免 ffmpeg-python 过度转义特殊字符
        # 注意：min_silence_duration 不被所有 FFmpeg 版本支持
        # 改用 start_duration/stop_duration 控制最小静音时长
        return input_stream.audio.filter("silenceremove",
            start_periods=1,
            start_duration=config.min_silence_duration,  # 使用用户配置的最小静音时长
            start_threshold=f"{config.silence_threshold}dB",
            stop_periods=1,
            stop_duration=config.min_silence_duration,  # 同样应用于停止检测
            stop_threshold=f"{config.silence_threshold}dB",
        )

    @staticmethod
    def _build_manual_trim_filter(input_stream, config: TrimConfig):
        """
        构建手动裁剪滤镜（指定起止时间）

        使用 atrim 滤镜按给定的开始和结束时间裁剪音频。

        Args:
            input_stream: ffmpeg 输入流
            config: 裁剪配置（使用 start_time 和 end_time）

        Returns:
            ffmpeg.Stream: 应用滤镜后的音频流
        """
        return input_stream.audio.filter(
            "atrim",
            start=config.start_time,
            end=config.end_time,
        )

    @staticmethod
    def _build_duration_trim_filter(input_stream, config: TrimConfig):
        """
        构建时长裁剪滤镜（指定开始时间和持续时长）

        使用 atrim 滤镜从 start_time 开始裁剪 duration 秒。

        Args:
            input_stream: ffmpeg 输入流
            config: 裁剪配置（使用 start_time 和 duration）

        Returns:
            ffmpeg.Stream: 应用滤镜后的音频流
        """
        end_time = config.start_time + (config.duration or 0)
        return input_stream.audio.filter(
            "atrim",
            start=config.start_time,
            end=end_time,
        )

    # ── 编码参数配置 ────────────────────────────────────────────────

    @staticmethod
    def _get_codec_config(output_quality: "OutputQuality", output_ext: str) -> dict:
        """
        根据输出质量和文件扩展名获取编码参数配置

        统一使用 ConverterConfig 的质量预设体系，确保与格式转换步骤一致。

        Args:
            output_quality: 输出质量配置（HIGH/STANDARD/SMALL）
            output_ext: 输出文件扩展名（如 .mp3, .flac）

        Returns:
            dict: 编码参数字典，空 dict 表示无需特殊编码参数
        """
        # 统一使用 ConverterConfig 的质量预设体系，确保与格式转换步骤一致
        quality_mapping = {
            OutputQuality.HIGH: ConvQualityPreset.HIGH,
            OutputQuality.STANDARD: ConvQualityPreset.MEDIUM,
            OutputQuality.SMALL: ConvQualityPreset.LOW,
        }
        conv_preset = quality_mapping.get(output_quality, ConvQualityPreset.MEDIUM)

        logger.debug(f"输出质量: {output_quality.display_name} -> ConverterPreset: {conv_preset.value}")

        # 统一的编码参数配置（与 converter/config.py FormatConfig 保持一致）
        codec_config = {
            '.wav': {'acodec': 'pcm_s16le'},                    # WAV 无损
            '.flac': {'acodec': 'flac'},                        # FLAC 无损
            '.mp3': {'acodec': 'libmp3lame'},                   # MP3
            '.aac': {'acodec': 'aac'},                          # AAC
            '.ogg': {'acodec': 'libvorbis'},                    # OGG Vorbis
            '.m4a': {'acodec': 'aac'},                          # M4A (AAC)
        }

        # 比特率配置（kbps）- 与 FormatConfig._apply_quality_preset 完全一致
        bitrate_config = {
            ConvQualityPreset.LOW: {'.mp3': 128, '.aac': 96,  '.ogg': 96,  '.m4a': 96},
            ConvQualityPreset.MEDIUM: {'.mp3': 192, '.aac': 128, '.ogg': 128, '.m4a': 128},
            ConvQualityPreset.HIGH: {'.mp3': 256, '.aac': 160, '.ogg': 160, '.m4a': 160},
            ConvQualityPreset.LOSSLESS: {'.mp3': 320, '.aac': 192, '.ogg': 192, '.m4a': 192},
        }

        base_kwargs = codec_config.get(output_ext, {})

        if not base_kwargs:
            return {}

        kwargs = dict(base_kwargs)

        # 为有损格式设置比特率（WAV/FLAC 不需要）
        if output_ext in ['.mp3', '.aac', '.ogg', '.m4a']:
            preset_bitrates = bitrate_config.get(conv_preset, {})
            target_kbps = preset_bitrates.get(output_ext, 192)
            kwargs['b:a'] = f'{target_kbps}k'
            logger.debug(f"编码参数: codec={kwargs['acodec']}, bitrate={target_kbps}kbps")

        return kwargs

    def trim_audio(
        self,
        input_path: str,
        output_path: str,
        config: TrimConfig | None = None,
        output_quality: "OutputQuality" = None,
    ) -> dict[str, Any]:
        """
        裁剪音频文件

        Args:
            input_path: 输入文件路径
            output_path: 输出文件路径
            config: 裁剪配置，默认使用手动模式从0秒开始
            output_quality: 输出质量配置（控制文件体积与音质平衡）

        Returns:
            dict: 包含 success, duration, error 等信息的字典
        """
        if config is None:
            config = TrimConfig()
        
        if output_quality is None:
            output_quality = OutputQuality.STANDARD

        result = {"success": False, "input_file": input_path, "output_file": output_path}

        if not os.path.exists(input_path):
            result["error"] = f"输入文件不存在: {input_path}"
            logger.error(result["error"])
            return result

        valid, error_msg = config.validate()
        if not valid:
            result["error"] = f"配置验证失败: {error_msg}"
            logger.error(result["error"])
            return result

        try:
            # 处理包含特殊字符的文件路径（使用临时链接方案）
            input_cleanup = None
            output_cleanup = None
            
            # 检查输入路径是否含特殊字符
            if self._has_special_chars(input_path):
                safe_input, input_cleanup = self._create_safe_temp_link(input_path)
                logger.info(f"输入路径含特殊字符，使用临时链接: {safe_input}")
            else:
                safe_input = self._safe_path(input_path)
            
            # 检查输出路径是否含特殊字符（输出目录可能不含特殊字符）
            if self._has_special_chars(output_path):
                safe_output, output_cleanup = self._create_safe_temp_link(output_path)
                logger.info(f"输出路径含特殊字符，使用临时链接: {safe_output}")
            else:
                safe_output = self._safe_path(output_path)
            
            input_stream = ffmpeg.input(safe_input)

            # 使用处理器模式映射代替 if/elif 链
            trim_handlers = {
                TrimMode.AUTO: self._build_auto_trim_filter,
                TrimMode.MANUAL: self._build_manual_trim_filter,
                TrimMode.DURATION: self._build_duration_trim_filter,
            }
            handler = trim_handlers.get(config.mode)
            if handler is None:
                result["error"] = f"不支持的裁剪模式: {config.mode}"
                logger.error(result["error"])
                return result
            processed = handler(input_stream, config)

            if config.fade_in > 0 or config.fade_out > 0:
                fade_kwargs = {"t": "in", "d": config.fade_in}
                if config.fade_out > 0:
                    # 淡出需要计算起始时间（从末尾往前）
                    fade_kwargs["t"] = "out"
                    fade_kwargs["d"] = config.fade_out
                processed = processed.filter("afade", **fade_kwargs)

            # 根据输出质量和扩展名配置编码参数
            output_ext = os.path.splitext(safe_output)[1].lower()
            codec_kwargs = self._get_codec_config(output_quality, output_ext)
            if codec_kwargs:
                output = processed.output(safe_output, **codec_kwargs)
            else:
                output = processed.output(safe_output)
            try:
                self._run_ffmpeg_safe(output)
            except ffmpeg.Error as e:
                error_detail = ""
                if hasattr(e, 'stderr') and e.stderr:
                    stderr_text = e.stderr.decode('utf-8', errors='ignore') if isinstance(e.stderr, bytes) else str(e.stderr)
                    lines = [l.strip() for l in stderr_text.split('\n') if l.strip()]
                    if lines:
                        error_detail = lines[-1][:200]
                logger.error(f"FFmpeg 执行失败详情: {error_detail or str(e)}")
                raise  # 直接抛出原始异常，保留完整的 stdout/stderr 信息

            # 验证输出文件是否存在且非空
            if not os.path.exists(safe_output):
                result["error"] = "FFmpeg 执行完成但输出文件未生成"
                logger.error(f"裁剪失败: {input_path}, {result['error']}")
                return result
            
            output_size = os.path.getsize(safe_output)
            if output_size == 0:
                result["error"] = "FFmpeg 执行完成但输出文件为空 (0 bytes)"
                logger.error(f"裁剪失败: {input_path}, {result['error']}")
                return result
            
            logger.debug(f"输出文件大小: {output_size} bytes")

            # 验证输出文件（safe_output 可能是临时链接）
            if output_cleanup:
                probe_path = safe_output  # 使用临时链接路径
            else:
                probe_path = output_path  # 直接使用输出路径
            
            logger.debug(f"验证输出文件: {probe_path}")
            probe = ffmpeg.probe(probe_path)
            duration = float(probe["format"]["duration"])

            result.update({
                "success": True,
                "duration": duration,
                "mode": config.mode.value,
            })
            logger.info(f"裁剪成功: {input_path} -> {output_path} (时长: {duration:.2f}秒)")
            
            # 如果输出使用了临时链接，将结果移动到真实目标位置
            if output_cleanup and os.path.exists(safe_output):
                import shutil
                shutil.move(safe_output, output_path)
                logger.debug(f"移动输出文件: {safe_output} -> {output_path}")
        
        except ffmpeg.Error as e:
            result["error"] = f"FFmpeg 处理错误: {str(e)}"
            logger.error(f"裁剪失败: {input_path}, 错误: {e}")
        except Exception as e:
            result["error"] = f"未知错误: {str(e)}"
            logger.exception(f"裁剪异常: {input_path}")
        finally:
            # 清理临时链接（无论成功或失败）
            if 'input_cleanup' in dir() and input_cleanup:
                try:
                    input_cleanup()
                except Exception as e:
                    logger.warning(f"清理输入临时链接失败: {e}")
            
            if 'output_cleanup' in dir() and output_cleanup:
                try:
                    # 如果输出文件已移动，则不需要清理输出链接
                    if not os.path.exists(output_path) or ('safe_output' in dir() and os.path.exists(safe_output)):
                        output_cleanup()
                except Exception as e:
                    logger.warning(f"清理输出临时链接失败: {e}")

        return result

    def normalize_volume(
        self,
        input_path: str,
        output_path: str,
        config: NormalizeConfig | None = None,
    ) -> dict[str, Any]:
        """
        标准化音量至目标响度（EBU R128 标准）

        Args:
            input_path: 输入文件路径
            output_path: 输出文件路径
            config: 音量标准化配置

        Returns:
            dict: 包含处理前后响度信息的结果字典
        """
        if config is None:
            config = NormalizeConfig()

        result = {
            "success": False,
            "input_file": input_path,
            "output_file": output_path,
            "before_loudness": None,
            "after_loudness": None,
        }

        if not os.path.exists(input_path):
            result["error"] = f"输入文件不存在: {input_path}"
            logger.error(result["error"])
            return result

        try:
            # 处理包含特殊字符的文件路径（使用临时链接方案）
            norm_input_cleanup = None
            norm_output_cleanup = None
            
            if self._has_special_chars(input_path):
                safe_input, norm_input_cleanup = self._create_safe_temp_link(input_path)
                logger.debug(f"normalize_volume 输入使用临时链接: {safe_input}")
            else:
                safe_input = self._safe_path(input_path)
            
            if self._has_special_chars(output_path):
                safe_output, norm_output_cleanup = self._create_safe_temp_link(output_path)
                logger.debug(f"normalize_volume 输出使用临时链接: {safe_output}")
            else:
                safe_output = self._safe_path(output_path)

            before_info = self.get_audio_info(safe_input)
            if before_info.get("success"):
                result["before_loudness"] = before_info.get("loudness_i")

            filter_str = config.to_ffmpeg_filter()
            input_stream = ffmpeg.input(safe_input)
            processed = input_stream.audio.filter(filter_str)
            output = processed.output(safe_output)
            try:
                self._run_ffmpeg_safe(output)
            except ffmpeg.Error as e:
                error_detail = ""
                if hasattr(e, 'stderr') and e.stderr:
                    stderr_text = e.stderr.decode('utf-8', errors='ignore') if isinstance(e.stderr, bytes) else str(e.stderr)
                    lines = [l.strip() for l in stderr_text.split('\n') if l.strip()]
                    if lines:
                        error_detail = lines[-1][:200]
                logger.error(f"FFmpeg 执行失败详情: {error_detail or str(e)}")
                raise  # 直接抛出原始异常，保留完整的 stdout/stderr 信息

            after_info = self.get_audio_info(safe_output)
            if after_info.get("success"):
                result["after_loudness"] = after_info.get("loudness_i")

            result["success"] = True
            logger.info(
                f"音量标准化完成: {input_path} -> {output_path} "
                f"(响度: {result['before_loudness']} -> {result['after_loudness']} LUFS)"
            )

        except ffmpeg.Error as e:
            result["error"] = f"FFmpeg 处理错误: {str(e)}"
            logger.error(f"音量标准化失败: {input_path}, 错误: {e}")
        except Exception as e:
            result["error"] = f"未知错误: {str(e)}"
            logger.exception(f"音量标准化异常: {input_path}")
        finally:
            if 'norm_input_cleanup' in dir() and norm_input_cleanup:
                try:
                    norm_input_cleanup()
                except Exception as e:
                    logger.warning(f"清理 normalize_volume 输入临时链接失败: {e}")
            if 'norm_output_cleanup' in dir() and norm_output_cleanup:
                try:
                    norm_output_cleanup()
                except Exception as e:
                    logger.warning(f"清理 normalize_volume 输出临时链接失败: {e}")

        return result

    def get_audio_info(self, file_path: str) -> dict[str, Any]:
        """
        获取音频文件的详细信息

        Args:
            file_path: 文件路径

        Returns:
            dict: 包含时长、采样率、声道数、比特率、响度等信息
        """
        result = {"success": False, "file_path": file_path}

        if not os.path.exists(file_path):
            result["error"] = f"文件不存在: {file_path}"
            return result

        try:
            # 处理包含特殊字符的文件路径
            probe_cleanup = None
            if self._has_special_chars(file_path):
                safe_path, probe_cleanup = self._create_safe_temp_link(file_path)
                logger.debug(f"get_audio_info 使用临时链接: {safe_path}")
            else:
                safe_path = self._safe_path(file_path)
            
            probe = ffmpeg.probe(safe_path)
            format_info = probe.get("format", {})
            streams = probe.get("streams", [])

            audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
            if not audio_streams:
                result["error"] = "未找到音频流"
                return result

            audio_stream = audio_streams[0]

            result.update({
                "success": True,
                "duration": float(format_info.get("duration", 0)),
                "size": int(format_info.get("size", 0)),
                "bit_rate": int(format_info.get("bit_rate", 0)) or audio_stream.get("bit_rate", 0),
                "sample_rate": int(audio_stream.get("sample_rate", 0)),
                "channels": int(audio_stream.get("channels", 0)),
                "codec_name": audio_stream.get("codec_name", "unknown"),
                "format_name": format_info.get("format_long_name", "unknown"),
            })

            loudnorm_result = self._measure_loudness(file_path)
            if loudnorm_result:
                result.update(loudnorm_result)

        except ffmpeg.Error as e:
            result["error"] = f"FFmpeg 探测错误: {str(e)}"
            logger.error(f"获取音频信息失败: {file_path}, 错误: {e}")
        except Exception as e:
            result["error"] = f"未知错误: {str(e)}"
            logger.exception(f"获取音频信息异常: {file_path}")
        finally:
            if 'probe_cleanup' in dir() and probe_cleanup:
                try:
                    probe_cleanup()
                except Exception as e:
                    logger.warning(f"清理 get_audio_info 临时链接失败: {e}")

        return result

    def _measure_loudness(self, file_path: str) -> dict[str, float] | None:
        """
        测量音频文件的响度（EBU R128 标准）

        Args:
            file_path: 文件路径

        Returns:
            dict | None: 响度测量结果字典，失败返回 None
        """
        try:
            # 处理包含特殊字符的文件路径
            loudness_cleanup = None
            if self._has_special_chars(file_path):
                safe_path, loudness_cleanup = self._create_safe_temp_link(file_path)
                logger.debug(f"_measure_loudness 使用临时链接: {safe_path}")
            else:
                safe_path = self._safe_path(file_path)
            
            input_stream = ffmpeg.input(safe_path)
            processed = input_stream.audio.filter(
                "loudnorm",
                print_format="json",
                I=-16,
                TP=-1.5,
                LRA=11,
            )
            output = processed.output("-", format="null")
            raw_output = self._run_ffmpeg_safe_capture(output)
            import json as json_module
            output_data = json_module.loads(raw_output[1].decode("utf-8"))

            parsed = output_data.get("input_i", {})
            return {
                "loudness_i": float(parsed.get("i", 0)),
                "loudness_tp": float(parsed.get("tp", 0)),
                "loudness_lra": float(parsed.get("lra", 0)),
                "loudness_thresh": float(parsed.get("thresh", 0)),
            }
        except Exception:
            return None
        finally:
            if 'loudness_cleanup' in dir() and loudness_cleanup:
                try:
                    loudness_cleanup()
                except Exception as e:
                    logger.warning(f"清理 _measure_loudness 临时链接失败: {e}")

    def apply_preset(
        self,
        input_path: str,
        output_path: str,
        config: EditorConfig,
    ) -> dict[str, Any]:
        """
        应用完整编辑预设（裁剪 + 音量标准化 + 格式转换）

        Args:
            input_path: 输入文件路径
            output_path: 输出文件路径
            config: 完整的编辑器配置

        Returns:
            dict: 处理结果字典
        """
        result = {
            "success": False,
            "input_file": input_path,
            "output_file": output_path,
            "steps_completed": [],
            "errors": [],
        }

        temp_path = output_path
        final_path = output_path

        if not os.path.exists(input_path):
            result["errors"].append(f"输入文件不存在: {input_path}")
            logger.error(result["errors"][-1])
            return result

        try:
            if config.trim.mode != TrimMode.MANUAL or config.trim.start_time > 0 or config.trim.end_time is not None:
                import tempfile
                temp_dir = tempfile.gettempdir()
                temp_trimmed = os.path.join(temp_dir, f"imusic_trim_{os.getpid()}_{id(input_path)}.wav")
                
                # 确保文件不存在（避免 Windows 文件锁定问题）
                if os.path.exists(temp_trimmed):
                    os.unlink(temp_trimmed)

                trim_result = self.trim_audio(input_path, temp_trimmed, config.trim, config.output_quality)
                if trim_result["success"]:
                    result["steps_completed"].append("trim")
                    temp_path = temp_trimmed
                else:
                    result["errors"].append(f"裁剪步骤失败: {trim_result.get('error', '未知错误')}")
                    if os.path.exists(temp_trimmed):
                        os.unlink(temp_trimmed)
                    return result

            normalize_enabled = (
                hasattr(config, 'normalize') and
                config.normalize.target_loudness != -16.0
            )
            if normalize_enabled:
                temp_dir = tempfile.gettempdir()
                temp_normalized = os.path.join(temp_dir, f"imusic_norm_{os.getpid()}_{id(input_path)}.wav")
                
                if os.path.exists(temp_normalized):
                    os.unlink(temp_normalized)

                norm_result = self.normalize_volume(temp_path, temp_normalized, config.normalize)
                if norm_result["success"]:
                    result["steps_completed"].append("normalize")
                    if temp_path != input_path and os.path.exists(temp_path):
                        os.unlink(temp_path)
                    temp_path = temp_normalized
                else:
                    result["errors"].append(f"音量标准化步骤失败: {norm_result.get('error', '未知错误')}")
                    if os.path.exists(temp_normalized):
                        os.unlink(temp_normalized)

            converter_config = ConverterConfig()
            
            output_quality = getattr(config, 'output_quality', None)
            if output_quality is not None:
                quality_mapping = {
                    OutputQuality.HIGH: QualityPreset.HIGH,
                    OutputQuality.STANDARD: QualityPreset.MEDIUM,
                    OutputQuality.SMALL: QualityPreset.LOW,
                }
                mapped_preset = quality_mapping.get(output_quality, config.quality_preset)
                logger.debug(f"质量配置映射: {output_quality.value} -> {mapped_preset.value}")
                converter_config.set_output_format(config.output_format.value, mapped_preset)
            else:
                converter_config.set_output_format(config.output_format.value, config.quality_preset)

            from auto_tag.converter.converter import AudioConverter
            converter = AudioConverter()
            convert_success = converter.convert_file(
                temp_path,
                final_path,
                converter_config,
            )

            if convert_success:
                result["steps_completed"].append("format_conversion")
                result["success"] = True
                logger.info(f"预设应用成功: {input_path} -> {final_path}")
            else:
                result["errors"].append("格式转换步骤失败")

            if temp_path != input_path and temp_path != final_path and os.path.exists(temp_path):
                os.unlink(temp_path)

        except Exception as e:
            result["errors"].append(f"应用预设时发生异常: {str(e)}")
            logger.exception(f"应用预设异常: {input_path}")

        return result
