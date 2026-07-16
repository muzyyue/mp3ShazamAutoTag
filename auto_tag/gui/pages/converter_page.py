# -*- coding: utf-8 -*-
"""
音频转换页面模块

该模块提供音频转换功能的页面界面，包括目录选择、格式转换、
进度显示、文件列表展示和批量操作等功能。
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    CheckBox,
    ComboBox,
    LineEdit,
    MessageBox,
    ProgressBar,
    PushButton,
    ScrollArea,
    SubtitleLabel,
    TableWidget,
    isDarkTheme,
)
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import qconfig

from auto_tag.converter.workers.converter_worker import ConverterWorker
from auto_tag.converter.config import ConverterConfig, OutputFormat, QualityPreset
from auto_tag.gui.config import config
from auto_tag.gui.i18n import tr


class ConverterPage(QWidget):
    """
    音频转换页面

    提供音频文件格式转换的用户界面。

    Attributes:
        input_dir (str): 输入目录路径
        output_dir (str): 输出目录路径
        files (list[str]): 待转换的文件列表
        worker (ConverterWorker | None): 当前工作线程实例
        config (ConverterConfig): 转换配置对象
        format_map (dict[str, OutputFormat]): 格式名称到枚举的映射
        quality_map (dict[str, QualityPreset]): 质量名称到枚举的映射
    """

    def __init__(self, parent=None) -> None:
        """
        初始化转换页面

        Args:
            parent (QWidget | None): 父窗口组件
        """
        super().__init__(parent)

        # 状态变量
        self.input_dir = ""
        self.output_dir = ""
        self.files: list[str] = []
        self.worker: ConverterWorker | None = None
        self.config = ConverterConfig()

        # 格式和预设映射
        self.format_map = {
            "MP3": OutputFormat.MP3,
            "FLAC": OutputFormat.FLAC,
            "AAC": OutputFormat.AAC,
            "OGG": OutputFormat.OGG,
            "WAV": OutputFormat.WAV,
            "M4A": OutputFormat.M4A,
        }

        self.quality_map = {
            "Low": QualityPreset.LOW,
            "Medium": QualityPreset.MEDIUM,
            "High": QualityPreset.HIGH,
            "Lossless": QualityPreset.LOSSLESS,
        }

        # 格式选择复选框字典
        self.audio_format_checkboxes: dict[str, CheckBox] = {}
        self.video_format_checkboxes: dict[str, CheckBox] = {}

        # 格式过滤区域的UI组件引用
        self.filter_title_label: SubtitleLabel | None = None
        self.audio_format_label: BodyLabel | None = None
        self.video_format_label: BodyLabel | None = None
        self.select_all_audio_btn: PushButton | None = None
        self.deselect_all_audio_btn: PushButton | None = None
        self.select_all_video_btn: PushButton | None = None
        self.deselect_all_video_btn: PushButton | None = None

        # 构建 UI
        self._setup_ui()

        # 加载配置中的格式选择
        self._load_format_config()

        # 连接主题切换信号
        qconfig.themeChanged.connect(self._on_theme_changed)

    def _setup_ui(self) -> None:
        """
        构建转换页面 UI 布局

        创建所有界面组件并使用布局管理器组织它们，
        包括输入区域、格式设置区域、进度区域、文件列表和操作按钮。
        整个页面使用统一的 ScrollArea 实现垂直滚动。
        """
        # 主布局（使用 QVBoxLayout）
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 创建内容容器 widget，包含所有页面元素
        self.content_widget = QWidget()
        self.content_widget.setObjectName("converterContentWidget")
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(40, 30, 40, 30)
        content_layout.setSpacing(16)

        # === 输入区域 ===
        input_layout = QHBoxLayout()
        input_layout.setSpacing(12)

        # 输入目录选择
        self.input_label = BodyLabel(tr("input_directory"))
        input_layout.addWidget(self.input_label)

        self.input_entry = LineEdit()
        self.input_entry.setPlaceholderText(tr("select_directory"))
        self.input_entry.setFixedHeight(36)
        input_layout.addWidget(self.input_entry)

        self.input_browse_btn = PushButton(tr("browse"))
        self.input_browse_btn.setFixedHeight(36)
        self.input_browse_btn.clicked.connect(self._on_browse)
        input_layout.addWidget(self.input_browse_btn)

        # 输出目录选择
        self.output_label = BodyLabel(tr("output_directory"))
        input_layout.addWidget(self.output_label)

        self.output_entry = LineEdit()
        self.output_entry.setPlaceholderText(tr("select_directory"))
        self.output_entry.setFixedHeight(36)
        input_layout.addWidget(self.output_entry)

        self.output_browse_btn = PushButton(tr("browse"))
        self.output_browse_btn.setFixedHeight(36)
        self.output_browse_btn.clicked.connect(self._on_browse_output)
        input_layout.addWidget(self.output_browse_btn)

        content_layout.addLayout(input_layout)

        # === 格式设置区域 ===
        format_layout = QHBoxLayout()
        format_layout.setSpacing(12)

        # 输出格式选择
        self.format_label = BodyLabel(tr("output_format"))
        format_layout.addWidget(self.format_label)

        self.format_combo = ComboBox()
        self.format_combo.addItems(list(self.format_map.keys()))
        self.format_combo.setCurrentIndex(0)  # 默认选择 MP3
        self.format_combo.setFixedHeight(36)
        self.format_combo.setFixedWidth(120)
        format_layout.addWidget(self.format_combo)

        # 质量预设选择
        self.quality_label = BodyLabel(tr("quality_preset"))
        format_layout.addWidget(self.quality_label)

        self.quality_combo = ComboBox()
        self.quality_combo.addItems(list(self.quality_map.keys()))
        self.quality_combo.setCurrentIndex(2)  # 默认选择 High
        self.quality_combo.setFixedHeight(36)
        self.quality_combo.setFixedWidth(120)
        format_layout.addWidget(self.quality_combo)

        format_layout.addStretch()

        content_layout.addLayout(format_layout)

        # === 文件格式过滤区域 ===
        self._setup_format_filter_ui(content_layout)

        # 增加文件格式过滤区域与进度条之间的垂直间隔
        content_layout.addSpacing(40)

        # === 进度区域（文件格式过滤区域外部独立显示）===
        progress_layout = QHBoxLayout()
        progress_layout.setSpacing(12)
        progress_layout.setContentsMargins(0, 0, 0, 16)  # 底部16px与文件列表分隔

        self.progress_bar = ProgressBar()
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed
        )
        progress_layout.addWidget(self.progress_bar, stretch=1)

        self.status_label = BodyLabel(tr("conversion_in_progress"))
        self.status_label.setMinimumWidth(150)
        progress_layout.addWidget(self.status_label)

        content_layout.addLayout(progress_layout)

        # === 文件列表 ===
        self.table_title = SubtitleLabel(tr("converter_file_list"))
        content_layout.addWidget(self.table_title)

        # 创建文件表格
        self.file_table = TableWidget()
        self.file_table.setColumnCount(5)
        self.file_table.setHorizontalHeaderLabels([
            tr("check"), tr("file_name"), tr("format"), tr("size"), tr("status")
        ])
        # 设置列宽
        self.file_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Fixed
        )
        self.file_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.file_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Fixed
        )
        self.file_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Fixed
        )
        self.file_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Fixed
        )
        self.file_table.setColumnWidth(0, 60)
        self.file_table.setColumnWidth(2, 80)
        self.file_table.setColumnWidth(3, 100)
        self.file_table.setColumnWidth(4, 100)

        # 表格最小高度，确保至少显示几行内容
        self.file_table.setMinimumHeight(200)

        content_layout.addWidget(self.file_table)

        # === 操作按钮区域 ===
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        btn_layout.setContentsMargins(0, 12, 0, 0)

        self.check_all_btn = PushButton(tr("check_all"))
        self.check_all_btn.clicked.connect(self._on_check_all)
        btn_layout.addWidget(self.check_all_btn)

        self.uncheck_all_btn = PushButton(tr("uncheck_all"))
        self.uncheck_all_btn.clicked.connect(self._on_uncheck_all)
        btn_layout.addWidget(self.uncheck_all_btn)

        btn_layout.addStretch()

        self.start_btn = PushButton(FIF.PLAY, tr("start_conversion"))
        self.start_btn.clicked.connect(self._start_conversion)
        btn_layout.addWidget(self.start_btn)

        self.stop_btn = PushButton(FIF.CANCEL, tr("stop_conversion"))
        self.stop_btn.clicked.connect(self._stop_conversion)
        self.stop_btn.setEnabled(False)
        btn_layout.addWidget(self.stop_btn)

        self.clear_data_btn = PushButton(FIF.DELETE, tr("clear_data"))
        self.clear_data_btn.clicked.connect(self._on_clear_data)
        btn_layout.addWidget(self.clear_data_btn)

        content_layout.addLayout(btn_layout)
        content_layout.addStretch()  # 底部弹性空间，内容少时按钮靠上

        # 使用 ScrollArea 包裹整个内容，实现全页面垂直滚动
        self.page_scroll = ScrollArea()
        self.page_scroll.setWidget(self.content_widget)
        self.page_scroll.setWidgetResizable(True)
        self.page_scroll.setMinimumHeight(400)
        self.page_scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        self.page_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.page_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.page_scroll.setObjectName("converterPageScroll")
        self._apply_page_scroll_theme()

        # 向后兼容：别名指向 page_scroll，确保旧测试代码仍能正常工作
        self.file_list_scroll = self.page_scroll

        main_layout.addWidget(self.page_scroll)

    def _apply_page_scroll_theme(self) -> None:
        """更新页面滚动区域样式以适配当前主题"""
        if not hasattr(self, 'page_scroll') or not hasattr(self, 'content_widget'):
            return

        # 使用透明背景，让 QFluentWidgets 自动处理主题适配
        self.page_scroll.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollArea > QWidget > QWidget {
                background-color: transparent;
            }
            #converterContentWidget {
                background-color: transparent;
            }
        """)

        self.setStyleSheet("""
            ConverterPage {
                background-color: transparent;
            }
        """)

    def _apply_scroll_area_theme(self) -> None:
        """更新滚动区域样式以适配当前主题（保留兼容性）"""
        self._apply_page_scroll_theme()

    def _setup_format_filter_ui(self, parent_layout: QVBoxLayout) -> None:
        """
        构建文件格式过滤UI组件

        创建音频格式和视频格式的多选框组，提供全选/取消全选快捷操作。

        Args:
            parent_layout (QVBoxLayout): 父布局管理器
        """
        # 标题
        self.filter_title_label = SubtitleLabel(tr("filter_formats"))
        parent_layout.addWidget(self.filter_title_label)

        # 音频格式组
        audio_group_layout = QVBoxLayout()
        audio_group_layout.setSpacing(8)

        # 音频格式标题行
        audio_header_layout = QHBoxLayout()
        audio_header_layout.setSpacing(12)

        self.audio_format_label = BodyLabel(tr("audio_formats"))
        audio_header_layout.addWidget(self.audio_format_label)

        audio_header_layout.addStretch()

        self.select_all_audio_btn = PushButton(tr("select_all_audio"))
        self.select_all_audio_btn.setFixedHeight(28)
        self.select_all_audio_btn.clicked.connect(self._on_select_all_audio)
        audio_header_layout.addWidget(self.select_all_audio_btn)

        self.deselect_all_audio_btn = PushButton(tr("deselect_all_audio"))
        self.deselect_all_audio_btn.setFixedHeight(28)
        self.deselect_all_audio_btn.clicked.connect(self._on_deselect_all_audio)
        audio_header_layout.addWidget(self.deselect_all_audio_btn)

        audio_group_layout.addLayout(audio_header_layout)

        # 音频格式复选框行
        audio_formats_layout = QHBoxLayout()
        audio_formats_layout.setSpacing(16)

        audio_formats = ["mp3", "flac", "aac", "ogg", "wav", "m4a"]
        for fmt in audio_formats:
            checkbox = CheckBox(fmt.upper())
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(self._update_supported_formats)
            audio_formats_layout.addWidget(checkbox)
            self.audio_format_checkboxes[fmt] = checkbox

        audio_formats_layout.addStretch()
        audio_group_layout.addLayout(audio_formats_layout)

        parent_layout.addLayout(audio_group_layout)

        # 视频格式组
        video_group_layout = QVBoxLayout()
        video_group_layout.setSpacing(8)

        # 视频格式标题行
        video_header_layout = QHBoxLayout()
        video_header_layout.setSpacing(12)

        self.video_format_label = BodyLabel(tr("video_formats"))
        video_header_layout.addWidget(self.video_format_label)

        video_header_layout.addStretch()

        self.select_all_video_btn = PushButton(tr("select_all_video"))
        self.select_all_video_btn.setFixedHeight(28)
        self.select_all_video_btn.clicked.connect(self._on_select_all_video)
        video_header_layout.addWidget(self.select_all_video_btn)

        self.deselect_all_video_btn = PushButton(tr("deselect_all_video"))
        self.deselect_all_video_btn.setFixedHeight(28)
        self.deselect_all_video_btn.clicked.connect(self._on_deselect_all_video)
        video_header_layout.addWidget(self.deselect_all_video_btn)

        video_group_layout.addLayout(video_header_layout)

        # 视频格式复选框行
        video_formats_layout = QHBoxLayout()
        video_formats_layout.setSpacing(16)

        video_formats = ["mp4", "mkv", "avi", "mov", "wmv", "webm"]
        for fmt in video_formats:
            checkbox = CheckBox(fmt.upper())
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(self._update_supported_formats)
            video_formats_layout.addWidget(checkbox)
            self.video_format_checkboxes[fmt] = checkbox

        video_formats_layout.addStretch()
        video_group_layout.addLayout(video_formats_layout)

        parent_layout.addLayout(video_group_layout)

        # === 自定义格式管理区域（与上方视频格式保持间隔）===
        parent_layout.addSpacing(16)  # 16px垂直间隔
        self._setup_custom_format_ui(parent_layout)

    def _setup_custom_format_ui(self, parent_layout: QVBoxLayout) -> None:
        """
        构建自定义格式管理UI组件

        创建自定义格式的添加、编辑、删除界面。

        Args:
            parent_layout (QVBoxLayout): 父布局管理器
        """
        from PySide6.QtWidgets import QListWidget, QListWidgetItem

        # 自定义格式卡片（使用 CardWidget 适配深色模式）
        custom_card = CardWidget(self)
        custom_card.setMinimumHeight(200)
        card_layout = QVBoxLayout(custom_card)
        card_layout.setContentsMargins(20, 15, 20, 15)
        card_layout.setSpacing(10)

        # 标题
        custom_title = SubtitleLabel(tr("custom_formats"))
        card_layout.addWidget(custom_title)

        # 输入区域
        input_layout = QHBoxLayout()
        input_layout.setSpacing(12)

        self.custom_ext_label = BodyLabel(tr("extension") + ":")
        input_layout.addWidget(self.custom_ext_label)

        self.custom_ext_entry = LineEdit()
        self.custom_ext_entry.setPlaceholderText(tr("enter_extension"))
        self.custom_ext_entry.setFixedHeight(32)
        self.custom_ext_entry.setFixedWidth(150)
        input_layout.addWidget(self.custom_ext_entry)

        self.custom_desc_label = BodyLabel(tr("description") + ":")
        input_layout.addWidget(self.custom_desc_label)

        self.custom_desc_entry = LineEdit()
        self.custom_desc_entry.setPlaceholderText(tr("enter_description"))
        self.custom_desc_entry.setFixedHeight(32)
        input_layout.addWidget(self.custom_desc_entry)

        self.add_custom_format_btn = PushButton(FIF.ADD, tr("add_format"))
        self.add_custom_format_btn.setFixedHeight(32)
        self.add_custom_format_btn.clicked.connect(self._on_add_custom_format)
        input_layout.addWidget(self.add_custom_format_btn)

        input_layout.addStretch()
        card_layout.addLayout(input_layout)

        # 自定义格式列表（设置透明背景以适配深色模式）
        self.custom_format_list = QListWidget()
        self.custom_format_list.setMinimumHeight(80)
        card_layout.addWidget(self.custom_format_list)

        # 适配深色主题样式
        self._apply_list_theme()

        # 操作按钮（增加顶部间距，使按钮靠下显示）
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.setContentsMargins(0, 12, 0, 4)  # 顶部12px间隔与列表分开

        self.edit_custom_format_btn = PushButton(FIF.EDIT, tr("edit_format"))
        self.edit_custom_format_btn.setFixedHeight(28)
        self.edit_custom_format_btn.clicked.connect(self._on_edit_custom_format)
        btn_layout.addWidget(self.edit_custom_format_btn)

        self.delete_custom_format_btn = PushButton(FIF.DELETE, tr("delete_format"))
        self.delete_custom_format_btn.setFixedHeight(28)
        self.delete_custom_format_btn.clicked.connect(self._on_delete_custom_format)
        btn_layout.addWidget(self.delete_custom_format_btn)

        btn_layout.addStretch()
        card_layout.addLayout(btn_layout)

        parent_layout.addWidget(custom_card)

        # 增加卡片与进度条之间的视觉分隔（避免卡片背景延伸到进度条区域）
        parent_layout.addSpacing(50)

        # 加载已有的自定义格式
        self._refresh_custom_format_list()

    def _refresh_custom_format_list(self) -> None:
        """
        刷新自定义格式列表

        从格式管理器获取所有自定义格式并显示在列表中。
        """
        self.custom_format_list.clear()

        custom_formats = config.custom_formats_manager.get_custom_formats()
        for fmt in custom_formats:
            item_text = f"{fmt.extension.upper()} - {fmt.description}"
            from PySide6.QtWidgets import QListWidgetItem
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, fmt.extension)
            self.custom_format_list.addItem(item)

    def _on_add_custom_format(self) -> None:
        """
        添加自定义格式按钮点击处理

        验证输入并添加新的自定义格式。
        """
        from auto_tag.converter.custom_format import CustomFormatManager

        extension = self.custom_ext_entry.text().strip()
        description = self.custom_desc_entry.text().strip()

        # 使用格式管理器验证和添加
        success, error_msg = config.custom_formats_manager.add_format(
            extension, description
        )

        if not success:
            MessageBox("错误", error_msg, self).exec()
            return

        # 清空输入框
        self.custom_ext_entry.clear()
        self.custom_desc_entry.clear()

        # 刷新列表
        self._refresh_custom_format_list()

        # 更新支持的格式列表（包含新添加的自定义格式）
        self._update_supported_formats()

        # 保存配置
        config.save()

        MessageBox("成功", f"已添加自定义格式: {extension.lower()}", self).exec()

    def _on_edit_custom_format(self) -> None:
        """
        编辑自定义格式按钮点击处理

        更新选中格式的描述信息。
        """
        current_item = self.custom_format_list.currentItem()
        if not current_item:
            MessageBox("提示", "请先选择要编辑的格式", self).exec()
            return

        extension = current_item.data(Qt.ItemDataRole.UserRole)
        new_description = self.custom_desc_entry.text().strip()

        if not new_description:
            MessageBox("错误", "请输入描述信息", self).exec()
            return

        success, error_msg = config.custom_formats_manager.update_format(
            extension, new_description
        )

        if not success:
            MessageBox("错误", error_msg, self).exec()
            return

        # 刷新列表
        self._refresh_custom_format_list()

        # 保存配置
        config.save()

        MessageBox("成功", f"已更新格式: {extension}", self).exec()

    def _on_delete_custom_format(self) -> None:
        """
        删除自定义格式按钮点击处理

        删除选中的自定义格式。
        """
        current_item = self.custom_format_list.currentItem()
        if not current_item:
            MessageBox("提示", "请先选择要删除的格式", self).exec()
            return

        extension = current_item.data(Qt.ItemDataRole.UserRole)

        # 确认删除（使用标准对话框）
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self,
            tr("confirm_delete"),
            f"{tr('confirm_delete_format')} '{extension}' ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.No:
            return

        success, error_msg = config.custom_formats_manager.remove_format(extension)

        if not success:
            MessageBox("错误", error_msg, self).exec()
            return

        # 刷新列表
        self._refresh_custom_format_list()

        # 更新支持的格式列表（移除已删除的自定义格式）
        self._update_supported_formats()

        # 保存配置
        config.save()

        MessageBox("成功", f"已删除自定义格式: {extension}", self).exec()

    def _update_supported_formats(self) -> None:
        """
        根据用户选择更新支持的格式列表

        遍历所有格式复选框，将选中的格式添加到配置中。
        同时包含用户自定义的格式。
        """
        selected_formats = []

        # 收集音频格式
        for fmt, checkbox in self.audio_format_checkboxes.items():
            if checkbox.isChecked():
                selected_formats.append(fmt)

        # 收集视频格式
        for fmt, checkbox in self.video_format_checkboxes.items():
            if checkbox.isChecked():
                selected_formats.append(fmt)

        # 收集自定义格式（始终包含）
        custom_formats = config.custom_formats_manager.get_custom_formats()
        for fmt in custom_formats:
            selected_formats.append(fmt.extension)

        # 更新配置
        self.config.supported_input_formats = selected_formats

        # 保存到配置文件
        self._save_format_config()

    def _on_select_all_audio(self) -> None:
        """全选音频格式"""
        for checkbox in self.audio_format_checkboxes.values():
            checkbox.setChecked(True)

    def _on_deselect_all_audio(self) -> None:
        """取消选择所有音频格式"""
        for checkbox in self.audio_format_checkboxes.values():
            checkbox.setChecked(False)

    def _on_select_all_video(self) -> None:
        """全选视频格式"""
        for checkbox in self.video_format_checkboxes.values():
            checkbox.setChecked(True)

    def _on_deselect_all_video(self) -> None:
        """取消选择所有视频格式"""
        for checkbox in self.video_format_checkboxes.values():
            checkbox.setChecked(False)

    def _load_format_config(self) -> None:
        """
        从配置文件加载格式选择

        根据配置文件中的格式列表更新复选框状态。
        如果配置为空或不存在，使用默认值（全选）。
        """
        saved_formats = config.converter_input_formats

        # 如果保存的格式列表为空，使用默认的全选状态
        if not saved_formats:
            # 默认全选所有预设格式
            for checkbox in self.audio_format_checkboxes.values():
                checkbox.setChecked(True)
            for checkbox in self.video_format_checkboxes.values():
                checkbox.setChecked(True)
        else:
            # 更新音频格式复选框
            for fmt, checkbox in self.audio_format_checkboxes.items():
                checkbox.setChecked(fmt in saved_formats)

            # 更新视频格式复选框
            for fmt, checkbox in self.video_format_checkboxes.items():
                checkbox.setChecked(fmt in saved_formats)

        # 更新配置
        self._update_supported_formats()

    def _save_format_config(self) -> None:
        """
        保存格式选择到配置文件

        将当前选择的格式列表保存到配置文件中。
        """
        try:
            config.set_converter_input_formats(self.config.supported_input_formats)
        except Exception as e:
            logger.exception(f"Error saving format config: {e}")

    def _scan_files(self, directory: str) -> list[str]:
        """
        扫描目录中的所有支持格式的文件

        Args:
            directory (str): 要扫描的目录路径

        Returns:
            list[str]: 找到的文件路径列表
        """
        try:
            files = []

            # 遍历目录
            for root, dirs, filenames in os.walk(directory):
                # 跳过 test 目录
                if 'test' in dirs:
                    dirs.remove('test')

                for filename in filenames:
                    # 获取文件扩展名
                    ext = os.path.splitext(filename)[1].lower().lstrip('.')

                    # 检查是否为支持的格式
                    if ext in self.config.supported_input_formats:
                        files.append(os.path.join(root, filename))

            return files
        except Exception as e:
            logger.exception(f"Error scanning files in {directory}: {e}")
            return []

    def _format_file_size(self, size_bytes: int) -> str:
        """
        格式化文件大小显示

        Args:
            size_bytes (int): 文件大小（字节）

        Returns:
            str: 格式化后的文件大小字符串
        """
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"

    def _on_browse(self) -> None:
        """
        浏览按钮点击处理

        打开文件夹选择对话框，选择后扫描文件并填充表格。
        """
        directory = QFileDialog.getExistingDirectory(
            self,
            "选择目录",
            "",
            QFileDialog.Option.ShowDirsOnly
        )

        if directory:
            try:
                self.input_dir = directory
                self.input_entry.setText(directory)

                # 扫描文件
                self.files = self._scan_files(directory)

                # 批量更新表格（禁用 UI 更新以提升性能）
                self.file_table.setUpdatesEnabled(False)
                try:
                    self.file_table.setRowCount(0)
                    self.file_table.setRowCount(len(self.files))

                    for row, file_path in enumerate(self.files):
                        # 勾选框列
                        checkbox_item = QTableWidgetItem()
                        checkbox_item.setFlags(
                            Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable
                        )
                        checkbox_item.setCheckState(Qt.CheckState.Checked)
                        self.file_table.setItem(row, 0, checkbox_item)

                        # 文件名列
                        filename = os.path.basename(file_path)
                        filename_item = QTableWidgetItem(filename)
                        filename_item.setFlags(filename_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                        # 存储完整路径
                        filename_item.setData(Qt.ItemDataRole.UserRole, file_path)
                        self.file_table.setItem(row, 1, filename_item)

                        # 格式列
                        ext = os.path.splitext(file_path)[1].upper().lstrip('.')
                        format_item = QTableWidgetItem(ext)
                        format_item.setFlags(format_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                        self.file_table.setItem(row, 2, format_item)

                        # 大小列
                        try:
                            size = os.path.getsize(file_path)
                            size_str = self._format_file_size(size)
                        except OSError:
                            size_str = "未知"
                        size_item = QTableWidgetItem(size_str)
                        size_item.setFlags(size_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                        self.file_table.setItem(row, 3, size_item)

                        # 状态列
                        status_item = QTableWidgetItem("待转换")
                        status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                        status_item.setForeground(Qt.GlobalColor.gray)
                        self.file_table.setItem(row, 4, status_item)
                finally:
                    self.file_table.setUpdatesEnabled(True)

                # 更新状态标签
                if self.files:
                    self.status_label.setText(f"找到 {len(self.files)} 个文件")
                else:
                    self.status_label.setText("未找到支持的文件")
            except Exception as e:
                logger.exception(f"Error browsing directory {directory}: {e}")
                self.status_label.setText("扫描目录时出错")

    def _on_browse_output(self) -> None:
        """
        输出目录浏览按钮处理

        打开文件夹选择对话框，选择输出目录。
        """
        try:
            directory = QFileDialog.getExistingDirectory(
                self,
                "选择目录",
                "",
                QFileDialog.Option.ShowDirsOnly
            )

            if directory:
                self.output_dir = directory
                self.output_entry.setText(directory)
        except Exception as e:
            logger.exception(f"Error browsing output directory: {e}")

    def _start_conversion(self) -> None:
        """
        开始转换

        创建工作线程并启动转换任务。
        """
        # 检查是否有选中的文件
        try:
            selected_files = []
            for row in range(self.file_table.rowCount()):
                item = self.file_table.item(row, 0)
                if item and item.checkState() == Qt.CheckState.Checked:
                    filename_item = self.file_table.item(row, 1)
                    if filename_item:
                        file_path = filename_item.data(Qt.ItemDataRole.UserRole)
                        selected_files.append(file_path)
        except Exception as e:
            logger.exception(f"Error collecting selected files: {e}")
            return

        if not selected_files:
            MessageBox(
                "提示",
                "请至少选择一个文件进行转换",
                self
            ).exec()
            return

        try:
            # 确定输出目录
            output_dir = self.output_dir if self.output_dir else self.input_dir

            # 获取格式和质量设置
            format_text = self.format_combo.currentText()
            quality_text = self.quality_combo.currentText()

            output_format = self.format_map.get(format_text, OutputFormat.MP3)
            quality_preset = self.quality_map.get(quality_text, QualityPreset.HIGH)

            # 更新配置
            self.config.set_output_format(output_format.value, quality_preset)
        except Exception as e:
            logger.exception(f"Error reading conversion settings: {e}")
            return

        try:
            # 重置进度
            self.progress_bar.setValue(0)
            self.status_label.setText("正在转换...")

            # 更新按钮状态
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
        except Exception as e:
            logger.exception(f"Error updating UI for conversion start: {e}")
            return

        try:
            # 创建工作线程
            self.worker = ConverterWorker(
                files=selected_files,
                output_dir=output_dir,
                config=self.config
            )

            # 连接信号
            self.worker.progress_updated.connect(self._on_progress_updated)
            self.worker.file_converted.connect(self._on_file_converted)
            self.worker.finished_all.connect(self._on_finished_all)
            self.worker.error_occurred.connect(self._on_error_occurred)
        except Exception as e:
            logger.exception(f"Error creating converter worker: {e}")
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.status_label.setText("创建转换任务失败")
            return

        try:
            # 启动线程
            self.worker.start()
        except Exception as e:
            logger.exception(f"Error starting converter worker: {e}")
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.status_label.setText("启动转换失败")

    def _stop_conversion(self) -> None:
        """
        停止转换

        停止当前工作线程。
        """
        if self.worker:
            self.worker.stop()
            self.status_label.setText("正在停止...")

    def _on_progress_updated(self, current: int, total: int, filename: str) -> None:
        """
        进度更新回调

        更新进度条和状态文本显示当前转换进度。

        Args:
            current (int): 当前文件索引
            total (int): 总文件数
            filename (str): 当前文件名
        """
        if total > 0:
            value = int(current / total * 100)
            self.progress_bar.setValue(value)

        self.status_label.setText(f"正在转换 {current}/{total}: {filename}")

    def _on_file_converted(self, path: str, success: bool, error: str) -> None:
        """
        单个文件转换完成回调

        更新表格中对应文件的状态。

        Args:
            path (str): 文件路径
            success (bool): 是否成功
            error (str): 错误信息
        """
        try:
            # 查找对应的表格行
            for row in range(self.file_table.rowCount()):
                filename_item = self.file_table.item(row, 1)
                if filename_item:
                    file_path = filename_item.data(Qt.ItemDataRole.UserRole)
                    if file_path == path:
                        # 更新状态列
                        status_item = self.file_table.item(row, 4)
                        if status_item:
                            if success:
                                status_item.setText("成功")
                                status_item.setForeground(Qt.GlobalColor.green)
                            else:
                                status_item.setText("失败")
                                status_item.setForeground(Qt.GlobalColor.red)
                        break
        except Exception as e:
            logger.exception(f"Error updating file converted status for {path}: {e}")

    def _on_finished_all(self, results: list) -> None:
        """
        所有文件转换完成回调

        显示转换结果统计信息。

        Args:
            results (list): 所有文件的转换结果列表
        """
        # 统计结果
        success_count = sum(1 for r in results if r.get("success"))
        total_count = len(results)

        # 更新进度
        self.progress_bar.setValue(100)
        self.status_label.setText(f"转换完成: {success_count}/{total_count} 成功")

        # 更新按钮状态
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

        # 显示完成消息
        if success_count == total_count:
            MessageBox(
                "成功",
                f"所有文件转换完成！共 {total_count} 个文件",
                self
            ).exec()
        else:
            failed_count = total_count - success_count
            MessageBox(
                "完成",
                f"转换完成：成功 {success_count} 个，失败 {failed_count} 个",
                self
            ).exec()

    def _on_error_occurred(self, error_msg: str) -> None:
        """
        错误发生回调

        显示错误消息对话框。

        Args:
            error_msg (str): 错误信息文本
        """
        try:
            MessageBox("错误", error_msg, self).exec()
        except Exception as e:
            logger.exception(f"Error showing error dialog: {e}")

        try:
            # 更新按钮状态
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
        except Exception as e:
            logger.exception(f"Error updating button state after error: {e}")

    def _on_check_all(self) -> None:
        """全选：将所有文件的勾选状态设为选中"""
        for row in range(self.file_table.rowCount()):
            item = self.file_table.item(row, 0)
            if item:
                item.setCheckState(Qt.CheckState.Checked)

    def _on_uncheck_all(self) -> None:
        """取消全选：将所有文件的勾选状态设为未选中"""
        for row in range(self.file_table.rowCount()):
            item = self.file_table.item(row, 0)
            if item:
                item.setCheckState(Qt.CheckState.Unchecked)

    def _on_clear_data(self) -> None:
        """
        清除数据按钮点击处理

        清除文件列表和表格数据，释放资源。
        如果正在转换则先停止任务，并显示确认对话框。
        """
        from PySide6.QtWidgets import QMessageBox

        try:
            # 检查是否有数据需要清除
            if not self.files and self.file_table.rowCount() == 0:
                return

            # 如果正在转换，先停止
            if self.worker and self.worker.isRunning():
                reply = QMessageBox.question(
                    self,
                    tr("confirm_stop_conversion"),
                    tr("confirm_stop_conversion_desc"),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )

                if reply != QMessageBox.StandardButton.Yes:
                    return

                self.worker.stop()
                self.worker.wait()

            # 显示确认对话框
            reply = QMessageBox.question(
                self,
                tr("confirm_clear_data"),
                tr("confirm_clear_data_desc"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if reply != QMessageBox.StandardButton.Yes:
                return

            # 清空文件列表
            self.files.clear()

            # 清空表格
            self.file_table.setRowCount(0)

            # 重置进度条
            self.progress_bar.setValue(0)

            # 更新状态标签
            self.status_label.setText(tr("conversion_in_progress"))

            # 重置按钮状态
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
        except Exception as e:
            logger.exception(f"Error clearing data: {e}")

    def _refresh_input_output_texts(self) -> None:
        """刷新输入输出区域的文本"""
        # 更新占位符文本
        self.input_entry.setPlaceholderText(tr("select_directory"))
        self.output_entry.setPlaceholderText(tr("select_directory"))

        # 更新输入区域标签文本
        self.input_label.setText(tr("input_directory"))
        self.output_label.setText(tr("output_directory"))

    def _refresh_format_texts(self) -> None:
        """刷新格式设置区域的文本"""
        # 更新格式设置区域标签文本
        self.format_label.setText(tr("output_format"))
        self.quality_label.setText(tr("quality_preset"))

        # 更新表头
        self.file_table.setHorizontalHeaderLabels([
            tr("check"), tr("file_name"), tr("format"), tr("size"), tr("status")
        ])

    def _refresh_button_texts(self) -> None:
        """刷新按钮和标题的文本"""
        # 更新标题
        self.table_title.setText(tr("converter_file_list"))

        # 更新按钮文本
        self.input_browse_btn.setText(tr("browse"))
        self.output_browse_btn.setText(tr("browse"))
        self.check_all_btn.setText(tr("check_all"))
        self.uncheck_all_btn.setText(tr("uncheck_all"))
        self.start_btn.setText(tr("start_conversion"))
        self.stop_btn.setText(tr("stop_conversion"))
        self.clear_data_btn.setText(tr("clear_data"))

    def _refresh_filter_texts(self) -> None:
        """刷新格式过滤区域的文本"""
        # 更新格式过滤区域的文本
        if self.filter_title_label:
            self.filter_title_label.setText(tr("filter_formats"))
        if self.audio_format_label:
            self.audio_format_label.setText(tr("audio_formats"))
        if self.video_format_label:
            self.video_format_label.setText(tr("video_formats"))
        if self.select_all_audio_btn:
            self.select_all_audio_btn.setText(tr("select_all_audio"))
        if self.deselect_all_audio_btn:
            self.deselect_all_audio_btn.setText(tr("deselect_all_audio"))
        if self.select_all_video_btn:
            self.select_all_video_btn.setText(tr("select_all_video"))
        if self.deselect_all_video_btn:
            self.deselect_all_video_btn.setText(tr("deselect_all_video"))

    def _refresh_custom_format_texts(self) -> None:
        """刷新自定义格式区域的文本"""
        # 更新自定义格式区域的文本
        if hasattr(self, 'custom_ext_label') and self.custom_ext_label:
            self.custom_ext_label.setText(tr("extension") + ":")
        if hasattr(self, 'custom_desc_label') and self.custom_desc_label:
            self.custom_desc_label.setText(tr("description") + ":")
        if hasattr(self, 'custom_ext_entry') and self.custom_ext_entry:
            self.custom_ext_entry.setPlaceholderText(tr("enter_extension"))
        if hasattr(self, 'custom_desc_entry') and self.custom_desc_entry:
            self.custom_desc_entry.setPlaceholderText(tr("enter_description"))
        if hasattr(self, 'add_custom_format_btn') and self.add_custom_format_btn:
            self.add_custom_format_btn.setText(tr("add_format"))
        if hasattr(self, 'edit_custom_format_btn') and self.edit_custom_format_btn:
            self.edit_custom_format_btn.setText(tr("edit_format"))
        if hasattr(self, 'delete_custom_format_btn') and self.delete_custom_format_btn:
            self.delete_custom_format_btn.setText(tr("delete_format"))

        # 刷新自定义格式列表（显示当前语言的格式信息）
        if hasattr(self, '_refresh_custom_format_list'):
            self._refresh_custom_format_list()

    def refresh_texts(self) -> None:
        """
        刷新页面文本

        当语言切换时调用此方法，更新所有 UI 文本为当前语言的翻译。
        """
        try:
            self._refresh_input_output_texts()
            self._refresh_format_texts()
            self._refresh_button_texts()
            self._refresh_filter_texts()
            self._refresh_custom_format_texts()
        except Exception as e:
            logger.exception(f"Error refreshing texts: {e}")

    def _apply_list_theme(self) -> None:
        """
        应用主题样式到 QListWidget

        根据当前主题设置列表控件的背景色和文字颜色，
        确保在深色模式下正确显示。
        """
        from PySide6.QtGui import QColor, QPalette

        if not hasattr(self, 'custom_format_list'):
            return

        if isDarkTheme():
            bg_color = QColor(45, 45, 51)
            text_color = QColor(255, 255, 255)
            item_bg = QColor(55, 55, 62)
            item_selected = QColor(82, 143, 224)
            hover_color = QColor(82, 143, 224)
            hover_color.setAlpha(80)
        else:
            bg_color = QColor(252, 252, 252)
            text_color = QColor(0, 0, 0)
            item_bg = QColor(255, 255, 255)
            item_selected = QColor(82, 143, 224)
            hover_color = QColor(82, 143, 224)
            hover_color.setAlpha(80)

        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Base, bg_color)
        palette.setColor(QPalette.ColorRole.Text, text_color)
        palette.setColor(QPalette.ColorRole.AlternateBase, item_bg)
        palette.setColor(QPalette.ColorRole.Highlight, item_selected)
        self.custom_format_list.setPalette(palette)

        hover_rgba = f"rgba({hover_color.red()}, {hover_color.green()}, {hover_color.blue()}, {hover_color.alpha() / 255:.2f})"

        self.custom_format_list.setStyleSheet(
            f"QListWidget {{"
            f"  background-color: {bg_color.name()};"
            f"  color: {text_color.name()};"
            f"  border: 1px solid {item_bg.name()};"
            f"  border-radius: 5px;"
            f"}}"
            f"QListWidget::item {{"
            f"  padding: 4px 8px;"
            f"  border-radius: 3px;"
            f"}}"
            f"QListWidget::item:selected {{"
            f"  background-color: {item_selected.name()};"
            f"  color: white;"
            f"}}"
            f"QListWidget::item:hover {{"
            f"  background-color: {hover_rgba};"
            f"}}"
        )

    def _on_theme_changed(self) -> None:
        """
        主题切换回调

        当用户切换深色/浅色主题时，更新滚动区域和列表控件样式。
        """
        self._apply_page_scroll_theme()
        self._apply_list_theme()


