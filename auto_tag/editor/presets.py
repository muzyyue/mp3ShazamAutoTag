# -*- coding: utf-8 -*-
"""
编辑预设管理模块

提供音频编辑的预设配置管理，包括：
- 内置预设（手机铃声/车载播放/HiFi存档/Podcast/音乐分享）
- 自定义预设的创建、保存和加载
- 预设验证功能

使用示例：
>>> from auto_tag.editor.presets import PresetManager
>>> manager = PresetManager()
>>> preset = manager.get_preset("ringtone")
>>> all_presets = manager.get_all_presets()
"""

import json
import logging
from pathlib import Path
from typing import Any

from auto_tag.editor.config import EditorConfig, NormalizeConfig, TrimConfig, TrimMode
from auto_tag.converter.config import OutputFormat, QualityPreset

logger = logging.getLogger(__name__)

BUILTIN_PRESETS: dict[str, dict[str, Any]] = {
    "ringtone": {
        "name": {"zh": "手机铃声", "en": "Phone Ringtone"},
        "icon": "PHONE",
        "description": {
            "zh": "适合制作iPhone/Android铃声（30秒，淡入淡出）",
            "en": "Optimized for phone ringtones (30s with fade in/out)",
        },
        "config": EditorConfig(
            trim=TrimConfig(
                mode=TrimMode.DURATION,
                duration=30.0,
                fade_in=0.5,
                fade_out=1.0,
            ),
            output_format=OutputFormat.M4A,
            quality_preset=QualityPreset.LOW,
        ),
    },
    "car_audio": {
        "name": {"zh": "车载播放", "en": "Car Audio"},
        "icon": "CAR",
        "description": {
            "zh": "高兼容性MP3，适合车载音响系统",
            "en": "High compatibility MP3 for car audio systems",
        },
        "config": EditorConfig(
            normalize=NormalizeConfig(target_loudness=-14.0),
            output_format=OutputFormat.MP3,
            quality_preset=QualityPreset.LOSSLESS,
        ),
    },
    "hifi_archive": {
        "name": {"zh": "HiFi存档", "en": "HiFi Archive"},
        "icon": "SAVE",
        "description": {
            "zh": "无损FLAC格式，适合长期音乐归档",
            "en": "Lossless FLAC format for long-term music archiving",
        },
        "config": EditorConfig(
            normalize=NormalizeConfig(target_loudness=-16.0),
            output_format=OutputFormat.FLAC,
            quality_preset=QualityPreset.LOSSLESS,
        ),
    },
    "podcast": {
        "name": {"zh": "Podcast", "en": "Podcast"},
        "icon": "HEADPHONE",
        "description": {
            "zh": "语音优化MP3，适合播客和有声书",
            "en": "Voice-optimized MP3 for podcasts and audiobooks",
        },
        "config": EditorConfig(
            normalize=NormalizeConfig(target_loudness=-16.0, lra=8.0),
            trim=TrimConfig(
                mode=TrimMode.AUTO,
                silence_threshold=-40.0,
                min_silence_duration=0.5,
            ),
            output_format=OutputFormat.MP3,
            quality_preset=QualityPreset.LOW,
        ),
    },
    "music_share": {
        "name": {"zh": "音乐分享", "en": "Music Share"},
        "icon": "MUSIC",
        "description": {
            "zh": "高质量AAC格式，体积小音质好，适合社交媒体分享",
            "en": "High quality AAC format, small size with great quality for social media sharing",
        },
        "config": EditorConfig(
            normalize=NormalizeConfig(target_loudness=-14.0),
            output_format=OutputFormat.M4A,
            quality_preset=QualityPreset.HIGH,
        ),
    },
}


class PresetManager:
    """音频编辑预设管理器"""

    def __init__(self, custom_presets_file: str | None = None) -> None:
        """
        初始化预设管理器

        Args:
            custom_presets_file: 自定义预设文件路径，默认为 ~/.imusic/custom_presets.json
        """
        if custom_presets_file is None:
            home = Path.home()
            presets_dir = home / ".imusic"
            presets_dir.mkdir(exist_ok=True)
            custom_presets_file = str(presets_dir / "custom_presets.json")

        self.custom_presets_file = Path(custom_presets_file)
        self._custom_presets: dict[str, dict[str, Any]] = {}
        self._load_custom_presets()

    def get_preset(self, name: str) -> dict[str, Any] | None:
        """
        获取指定名称的预设配置

        Args:
            name: 预设名称（如 'ringtone', 'car_audio'）

        Returns:
            dict | None: 预设字典（包含 name, icon, description, config），不存在返回 None
        """
        if name in BUILTIN_PRESETS:
            return BUILTIN_PRESETS[name]

        if name in self._custom_presets:
            return self._custom_presets[name]

        logger.warning(f"未找到预设: {name}")
        return None

    def get_all_presets(self) -> list[dict[str, Any]]:
        """
        获取所有可用预设列表（内置 + 自定义）

        Returns:
            list[dict]: 预设字典列表
        """
        presets = list(BUILTIN_PRESETS.values())
        presets.extend(self._custom_presets.values())
        return presets

    def get_builtin_presets(self) -> dict[str, dict[str, Any]]:
        """获取所有内置预设"""
        return BUILTIN_PRESETS.copy()

    def get_custom_presets(self) -> dict[str, dict[str, Any]]:
        """获取所有自定义预设"""
        return self._custom_presets.copy()

    def create_custom_preset(
        self,
        name: str,
        config: EditorConfig,
        icon: str = "SETTING",
        description_zh: str = "",
        description_en: str = "",
    ) -> tuple[bool, str]:
        """
        创建新的自定义预设

        Args:
            name: 预设名称（唯一标识符）
            config: 编辑器配置对象
            icon: Fluent 图标名（如 'PHONE'，对应 qfluentwidgets.FluentIcon 成员）
            description_zh: 中文描述
            description_en: 英文描述

        Returns:
            tuple[bool, str]: (是否成功, 错误信息)
        """
        valid, error = config.validate()
        if not valid:
            logger.error(f"创建自定义预设失败 - 配置无效: {error}")
            return False, f"配置无效: {error}"

        if name in BUILTIN_PRESETS:
            error_msg = f"不能覆盖内置预设: {name}"
            logger.error(error_msg)
            return False, error_msg

        self._custom_presets[name] = {
            "name": {"zh": name, "en": name},
            "icon": icon,
            "description": {"zh": description_zh, "en": description_en},
            "config": config.to_dict(),
            "is_custom": True,
        }

        success, save_error = self.save_custom_presets()
        if not success:
            logger.error(f"保存自定义预设失败: {save_error}")

        logger.info(f"创建自定义预设成功: {name}")
        return True, ""

    def delete_custom_preset(self, name: str) -> tuple[bool, str]:
        """
        删除指定的自定义预设

        Args:
            name: 预设名称

        Returns:
            tuple[bool, str]: (是否成功, 错误信息)
        """
        if name not in self._custom_presets:
            error_msg = f"自定义预设不存在: {name}"
            logger.warning(error_msg)
            return False, error_msg

        del self._custom_presets[name]
        success, save_error = self.save_custom_presets()
        if not success:
            logger.error(f"删除后保存失败: {save_error}")
            return False, save_error

        logger.info(f"删除自定义预设成功: {name}")
        return True, ""

    def validate_preset(self, preset_data: dict[str, Any]) -> tuple[bool, str]:
        """
        验证预设数据的有效性

        Args:
            preset_data: 预设字典

        Returns:
            tuple[bool, str]: (是否有效, 错误信息)
        """
        required_keys = ["name", "icon", "description", "config"]
        for key in required_keys:
            if key not in preset_data:
                return False, f"缺少必需字段: {key}"

        try:
            config_data = preset_data["config"]
            if isinstance(config_data, dict):
                config = EditorConfig.from_dict(config_data)
            elif isinstance(config_data, EditorConfig):
                config = config_data
            else:
                return False, "config 字段必须是字典或 EditorConfig 类型"
            
            valid, error = config.validate()
            if not valid:
                return False, f"配置无效: {error}"
        except Exception as e:
            return False, f"解析配置失败: {str(e)}"

        return True, ""

    def save_custom_presets(self) -> tuple[bool, str]:
        """
        保存所有自定义预设到文件

        Returns:
            tuple[bool, str]: (是否成功, 错误信息)
        """
        try:
            with open(self.custom_presets_file, "w", encoding="utf-8") as f:
                json.dump(self._custom_presets, f, ensure_ascii=False, indent=2)
            logger.info(f"保存自定义预设到: {self.custom_presets_file}")
            return True, ""
        except Exception as e:
            error_msg = f"保存自定义预设失败: {str(e)}"
            logger.exception(error_msg)
            return False, error_msg

    def _load_custom_presets(self) -> None:
        """从文件加载自定义预设"""
        if not self.custom_presets_file.exists():
            logger.debug("自定义预设文件不存在，使用空预设")
            return

        try:
            with open(self.custom_presets_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            for name, preset_data in data.items():
                valid, error = self.validate_preset(preset_data)
                if valid:
                    self._custom_presets[name] = preset_data
                    self._custom_presets[name]["is_custom"] = True
                else:
                    logger.warning(f"跳过无效的自定义预设 '{name}': {error}")

            logger.info(f"加载了 {len(self._custom_presets)} 个自定义预设")
        except Exception as e:
            logger.warning(f"加载自定义预设失败: {str(e)}，将使用空预设")
            self._custom_presets = {}

    @staticmethod
    def get_preset_names() -> list[str]:
        """获取所有内置预设名称列表"""
        return list(BUILTIN_PRESETS.keys())

    @staticmethod
    def get_preset_for_language(name: str, language: str = "zh") -> dict[str, Any] | None:
        """
        获取指定语言的预设信息

        Args:
            name: 预设名称
            language: 语言代码 ('zh' 或 'en')

        Returns:
            dict | None: 本地化后的预设信息
        """
        preset = BUILTIN_PRESETS.get(name)
        if preset is None:
            return None

        localized = preset.copy()
        localized["display_name"] = preset["name"].get(language, name)
        localized["display_description"] = preset["description"].get(language, "")
        return localized
