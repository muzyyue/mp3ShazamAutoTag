# -*- coding: utf-8 -*-
"""
音频编辑页面模块

提供音频编辑功能的用户界面
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    CheckBox,
    ComboBox,
    DoubleSpinBox,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    MessageBox,
    ProgressBar,
    PushButton,
    RadioButton,
    ScrollArea,
    SubtitleLabel,
    TableWidget,
    IconWidget,
    FluentIcon as FIF,
    isDarkTheme,
    qconfig,
)

from auto_tag.editor.workers.editor_worker import EditorWorker
from auto_tag.editor.config import EditorConfig, NormalizeConfig, OutputQuality, TrimConfig, TrimMode
from auto_tag.editor.presets import PresetManager
from auto_tag.converter.config import OutputFormat, QualityPreset
from auto_tag.gui.i18n import tr

logger = logging.getLogger(__name__)


class EditorPage(ScrollArea):
    """音频编辑页面"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.input_dir = ""
        self.output_dir = ""
        self.files: list[str] = []
        self.worker: EditorWorker | None = None
        self.config = EditorConfig()
        self.preset_manager = PresetManager()

        # 构建 UI
        self._setup_ui()

        # 连接主题切换信号
        qconfig.themeChanged.connect(self._on_theme_changed)
        logger.info("编辑页面初始化完成")

    def _setup_ui(self) -> None:
        """构建 UI 布局"""
        self.setWidgetResizable(True)
        self.setObjectName("editorPage")

        # 主布局（使用 QVBoxLayout）
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 创建内容容器 widget，包含所有页面元素
        self.content_widget = QWidget()
        self.content_widget.setObjectName("editorContentWidget")
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(40, 30, 40, 30)
        content_layout.setSpacing(16)

        # 标题
        title_label = SubtitleLabel(tr("editor.title"))
        content_layout.addWidget(title_label)

        # === 目录选择区域 ===
        dir_card = CardWidget(self)
        dir_card.setMinimumHeight(80)
        dir_layout = QHBoxLayout(dir_card)
        dir_layout.setContentsMargins(20, 16, 20, 16)

        input_label = BodyLabel(tr("input_directory") + ":")
        dir_layout.addWidget(input_label)

        self.input_entry = LineEdit()
        self.input_entry.setPlaceholderText(tr("select_directory"))
        self.input_entry.setFixedHeight(36)
        dir_layout.addWidget(self.input_entry, 1)

        browse_btn = PushButton(FIF.FOLDER, tr("browse"), self)
        browse_btn.clicked.connect(self._on_browse_input_dir)
        dir_layout.addWidget(browse_btn)

        output_label = BodyLabel(tr("output_directory") + ":")
        dir_layout.addWidget(output_label)

        self.output_entry = LineEdit()
        self.output_entry.setPlaceholderText(tr("select_directory"))
        self.output_entry.setText(tr("editor.same_directory"))
        self.output_entry.setFixedHeight(36)
        dir_layout.addWidget(self.output_entry, 1)

        output_browse_btn = PushButton(FIF.FOLDER, tr("browse"), self)
        output_browse_btn.clicked.connect(self._on_browse_output_dir)
        dir_layout.addWidget(output_browse_btn)

        content_layout.addWidget(dir_card)

        # === 文件列表区域 ===
        file_list_card = CardWidget(self)
        file_list_card.setMinimumHeight(250)
        file_list_layout = QVBoxLayout(file_list_card)
        file_list_layout.setContentsMargins(20, 15, 20, 15)
        file_list_layout.setSpacing(10)

        # 标题行（标题 + 搜索框）
        title_hbox = QHBoxLayout()
        title_hbox.setSpacing(12)

        table_title = SubtitleLabel(tr("editor.file_list"))
        title_hbox.addWidget(table_title)

        title_hbox.addStretch()

        # 搜索框
        self.search_edit = LineEdit()
        self.search_edit.setPlaceholderText(tr("editor.search_placeholder"))
        self.search_edit.setFixedWidth(240)
        self.search_edit.setFixedHeight(32)
        self.search_edit.textChanged.connect(self._on_search_text_changed)
        title_hbox.addWidget(self.search_edit)

        # 文件计数（Fluent 图标 + 计数标签）
        self._file_count_icon = IconWidget(FIF.CHECKBOX)
        self._file_count_icon.setFixedSize(16, 16)
        title_hbox.addWidget(self._file_count_icon)
        self.file_count_label = BodyLabel("")
        title_hbox.addWidget(self.file_count_label)

        file_list_layout.addLayout(title_hbox)

        self.file_table = TableWidget()
        self.file_table.setColumnCount(5)
        self.file_table.setHorizontalHeaderLabels([
            tr("check"),
            tr("file_name"),
            tr("format"),
            tr("size"),
            tr("status"),
        ])
        self.file_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.file_table.setAlternatingRowColors(True)
        self.file_table.verticalHeader().setVisible(False)
        file_list_layout.addWidget(self.file_table)

        content_layout.addWidget(file_list_card, 1)  # stretch=1 让表格可伸缩

        # === 操作按钮区域（文件列表卡片下方，独立区域） ===
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.setContentsMargins(40, 12, 40, 0)

        select_all_btn = PushButton(FIF.COMPLETED, tr("check_all"), self)
        select_all_btn.clicked.connect(self._on_select_all)
        btn_layout.addWidget(select_all_btn)

        deselect_all_btn = PushButton(FIF.CANCEL, tr("uncheck_all"), self)
        deselect_all_btn.clicked.connect(self._on_deselect_all)
        btn_layout.addWidget(deselect_all_btn)

        clear_data_btn = PushButton(FIF.DELETE, tr("clear_data"), self)
        clear_data_btn.clicked.connect(self._on_clear_data)
        btn_layout.addWidget(clear_data_btn)

        btn_layout.addStretch()

        self.start_btn = PushButton(FIF.PLAY, tr("editor.start_editing"), self)
        self.start_btn.clicked.connect(self._on_start_editing)
        btn_layout.addWidget(self.start_btn)

        self.stop_btn = PushButton(FIF.CANCEL, tr("editor.stop_editing"), self)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop_editing)
        btn_layout.addWidget(self.stop_btn)

        content_layout.addLayout(btn_layout)

        # === 进度条区域（操作按钮下方） ===
        progress_card = CardWidget(self)
        progress_card.setMinimumHeight(48)
        progress_layout = QHBoxLayout(progress_card)
        progress_layout.setContentsMargins(20, 10, 20, 10)

        self.progress_bar = ProgressBar(self)
        self.progress_bar.setFixedHeight(8)
        progress_layout.addWidget(self.progress_bar, 1)

        self.status_label = BodyLabel(tr("editor.editing_in_progress"))
        progress_layout.addWidget(self.status_label)

        content_layout.addWidget(progress_card)

        # === 裁剪设置区域 ===
        trim_card = CardWidget(self)
        trim_card.setMinimumHeight(200)
        trim_layout = QVBoxLayout(trim_card)
        trim_layout.setContentsMargins(20, 15, 20, 15)
        trim_layout.setSpacing(12)

        trim_title = SubtitleLabel(tr("editor.trim_settings"))
        trim_layout.addWidget(trim_title)

        # 裁剪模式选择
        mode_hbox = QHBoxLayout()
        mode_hbox.setSpacing(12)

        self.trim_auto_radio = RadioButton(tr("editor.auto_trim"))
        self.trim_manual_radio = RadioButton(tr("editor.manual_trim"))
        self.trim_duration_radio = RadioButton(tr("editor.duration_trim"))
        self.trim_manual_radio.setChecked(True)

        mode_hbox.addWidget(self.trim_auto_radio)
        mode_hbox.addWidget(self.trim_manual_radio)
        mode_hbox.addWidget(self.trim_duration_radio)
        mode_hbox.addStretch()
        trim_layout.addLayout(mode_hbox)

        # 第一行：开始时间 + 结束时间
        row1_hbox = QHBoxLayout()
        row1_hbox.setSpacing(16)

        start_time_label = BodyLabel(tr("editor.start_time"))
        row1_hbox.addWidget(start_time_label)

        self.start_time_spin = DoubleSpinBox()
        self.start_time_spin.setRange(0.0, 36000.0)
        self.start_time_spin.setValue(0.0)
        self.start_time_spin.setSuffix(" s")
        self.start_time_spin.setMinimumWidth(120)
        row1_hbox.addWidget(self.start_time_spin)

        row1_hbox.addSpacing(32)

        end_time_label = BodyLabel(tr("editor.end_time"))
        row1_hbox.addWidget(end_time_label)

        self.end_time_spin = DoubleSpinBox()
        self.end_time_spin.setRange(0.0, 36000.0)
        self.end_time_spin.setValue(180.0)
        self.end_time_spin.setSuffix(" s")
        self.end_time_spin.setMinimumWidth(120)
        row1_hbox.addWidget(self.end_time_spin)

        row1_hbox.addStretch()
        trim_layout.addLayout(row1_hbox)

        # 第二行：时长 + 淡入时长
        row2_hbox = QHBoxLayout()
        row2_hbox.setSpacing(16)

        duration_label = BodyLabel(tr("editor.duration"))
        row2_hbox.addWidget(duration_label)

        self.duration_spin = DoubleSpinBox()
        self.duration_spin.setRange(1.0, 600.0)
        self.duration_spin.setValue(30.0)
        self.duration_spin.setSuffix(" s")
        self.duration_spin.setMinimumWidth(120)
        self.duration_spin.setEnabled(False)
        row2_hbox.addWidget(self.duration_spin)

        row2_hbox.addSpacing(32)

        fade_in_label = BodyLabel(tr("editor.fade_in"))
        row2_hbox.addWidget(fade_in_label)

        self.fade_in_spin = DoubleSpinBox()
        self.fade_in_spin.setRange(0.0, 10.0)
        self.fade_in_spin.setValue(0.0)
        self.fade_in_spin.setSuffix(" s")
        self.fade_in_spin.setMinimumWidth(120)
        row2_hbox.addWidget(self.fade_in_spin)

        row2_hbox.addStretch()
        trim_layout.addLayout(row2_hbox)

        # 第三行：淡出时长
        row3_hbox = QHBoxLayout()
        row3_hbox.setSpacing(16)

        fade_out_label = BodyLabel(tr("editor.fade_out"))
        row3_hbox.addWidget(fade_out_label)

        self.fade_out_spin = DoubleSpinBox()
        self.fade_out_spin.setRange(0.0, 10.0)
        self.fade_out_spin.setValue(0.0)
        self.fade_out_spin.setSuffix(" s")
        self.fade_out_spin.setMinimumWidth(120)
        row3_hbox.addWidget(self.fade_out_spin)

        row3_hbox.addStretch()
        trim_layout.addLayout(row3_hbox)
        content_layout.addWidget(trim_card)

        # === 音量设置区域 ===
        volume_card = CardWidget(self)
        volume_card.setMinimumHeight(160)
        volume_layout = QVBoxLayout(volume_card)
        volume_layout.setContentsMargins(20, 15, 20, 15)
        volume_layout.setSpacing(12)

        volume_title = SubtitleLabel(tr("editor.volume_settings"))
        volume_layout.addWidget(volume_title)

        self.normalize_check = CheckBox(tr("editor.enable_normalization"))
        volume_layout.addWidget(self.normalize_check)

        # 第一行：目标响度 + 真峰值
        row1_hbox = QHBoxLayout()
        row1_hbox.setSpacing(16)

        loudness_label = BodyLabel(tr("editor.target_loudness"))
        row1_hbox.addWidget(loudness_label)

        self.loudness_spin = DoubleSpinBox()
        self.loudness_spin.setRange(-70.0, -5.0)
        self.loudness_spin.setValue(-16.0)
        self.loudness_spin.setSuffix(" LUFS")
        self.loudness_spin.setMinimumWidth(140)
        row1_hbox.addWidget(self.loudness_spin)

        row1_hbox.addSpacing(32)

        tp_label = BodyLabel(tr("editor.true_peak"))
        row1_hbox.addWidget(tp_label)

        self.true_peak_spin = DoubleSpinBox()
        self.true_peak_spin.setRange(-10.0, 0.0)
        self.true_peak_spin.setValue(-1.5)
        self.true_peak_spin.setSuffix(" dBFS")
        self.true_peak_spin.setMinimumWidth(120)
        row1_hbox.addWidget(self.true_peak_spin)

        row1_hbox.addStretch()
        volume_layout.addLayout(row1_hbox)

        # 第二行：响度范围 + 提示文字
        row2_hbox = QHBoxLayout()
        row2_hbox.setSpacing(16)

        lra_label = BodyLabel(tr("editor.lra"))
        row2_hbox.addWidget(lra_label)

        self.lra_spin = DoubleSpinBox()
        self.lra_spin.setRange(1.0, 50.0)
        self.lra_spin.setValue(11.0)
        self.lra_spin.setSuffix(" LU")
        self.lra_spin.setMinimumWidth(120)
        row2_hbox.addWidget(self.lra_spin)

        row2_hbox.addSpacing(32)

        loudness_tip = BodyLabel(tr("editor.tips.loudness_info"))
        loudness_tip.setStyleSheet("color: gray; font-size: 11px;")
        row2_hbox.addWidget(loudness_tip)

        row2_hbox.addStretch()
        volume_layout.addLayout(row2_hbox)
        content_layout.addWidget(volume_card)

        # === 输出格式区域 ===
        format_card = CardWidget(self)
        format_layout = QVBoxLayout(format_card)
        format_layout.setContentsMargins(20, 15, 20, 15)
        format_layout.setSpacing(12)

        format_title = SubtitleLabel(tr("editor.output_format_settings"))
        format_layout.addWidget(format_title)

        preset_hbox = QHBoxLayout()
        preset_hbox.setSpacing(16)

        preset_label = BodyLabel(tr("editor.preset") + ":")
        preset_hbox.addWidget(preset_label)

        self.preset_combo = ComboBox()
        self.preset_combo.setPlaceholderText(tr("editor.preset_placeholder"))
        self.preset_combo.setMinimumWidth(200)
        self.preset_combo.setFixedHeight(36)
        presets = self.preset_manager.get_all_presets()
        for preset in presets:
            # icon 字段为 FluentIcon 成员名（如 'PHONE'），无效值回退 SETTING
            icon_name = preset.get("icon", "")
            icon = getattr(FIF, icon_name, FIF.SETTING) if icon_name else FIF.SETTING
            self.preset_combo.addItem(list(preset["name"].values())[0], icon, userData=preset)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        preset_hbox.addWidget(self.preset_combo)

        preset_hbox.addStretch()

        self.overwrite_check = CheckBox(tr("editor.overwrite_original"))
        preset_hbox.addWidget(self.overwrite_check)

        format_layout.addLayout(preset_hbox)

        # 输出质量选择
        quality_hbox = QHBoxLayout()
        quality_hbox.setSpacing(16)

        quality_label = BodyLabel(tr("editor.output_quality") + ":")
        quality_hbox.addWidget(quality_label)

        self.quality_combo = ComboBox()
        self.quality_combo.setMinimumWidth(150)
        self.quality_combo.setFixedHeight(36)
        for quality in OutputQuality:
            display = f"{quality.display_name} - {quality.description}"
            self.quality_combo.addItem(display, userData=quality)
        self.quality_combo.setCurrentIndex(1)  # 默认选择"标准"
        self.quality_combo.currentIndexChanged.connect(self._on_quality_changed)
        quality_hbox.addWidget(self.quality_combo)

        quality_hbox.addSpacing(32)

        # 质量提示标签（显示当前选择的详细信息）
        self.quality_tip_label = BodyLabel("")
        self.quality_tip_label.setStyleSheet("color: gray; font-size: 11px;")
        quality_hbox.addWidget(self.quality_tip_label)

        quality_hbox.addStretch()
        format_layout.addLayout(quality_hbox)

        # 初始化质量提示文本
        self._on_quality_changed(1)
        content_layout.addWidget(format_card)

        # 添加弹性空间，确保可以滚动
        content_layout.addStretch()

        # 设置 ScrollArea 的内容 widget
        self.setWidget(self.content_widget)

        # 连接信号槽
        self.trim_auto_radio.toggled.connect(self._on_trim_mode_changed)
        self.trim_duration_radio.toggled.connect(lambda checked: self.duration_spin.setEnabled(checked))
        self.normalize_check.toggled.connect(self._on_normalize_toggled)

        # 初始化控件状态
        self._on_normalize_toggled(False)

        # 初始化主题
        self._apply_scroll_theme()

    def _on_theme_changed(self) -> None:
        """主题切换回调"""
        self._apply_scroll_theme()

    def _apply_scroll_theme(self) -> None:
        """应用滚动区域主题（使用透明背景让 QFluentWidgets 自动处理主题适配）"""
        if not hasattr(self, 'content_widget'):
            return

        self.setStyleSheet("""
            EditorPage {
                background-color: transparent;
            }
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollArea > QWidget > QWidget {
                background-color: transparent;
            }
            #editorContentWidget {
                background-color: transparent;
            }
        """)

    def refresh_texts(self) -> None:
        """刷新界面文本（国际化）"""
        pass

    def _update_file_count(self) -> None:
        """更新文件计数显示（格式：选中数/可见数/总数）"""
        total = len(self.files)
        visible = sum(1 for r in range(self.file_table.rowCount()) if not self.file_table.isRowHidden(r))
        selected = 0
        for row in range(self.file_table.rowCount()):
            if self.file_table.isRowHidden(row):
                continue
            item = self.file_table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                selected += 1

        keyword = self.search_edit.text().strip()
        if keyword:
            # 搜索模式：显示 "2/5/233"（选中/可见/总数），图标表示选中状态
            self.file_count_label.setText(f"{selected}/{visible}/{total}")
        elif selected > 0 and selected < visible:
            # 有部分选中：显示 "10/233"
            self.file_count_label.setText(f"{selected}/{total}")
        else:
            # 无搜索且全选或全不选
            self.file_count_label.setText(f"({total})")

    def _on_search_text_changed(self, text: str) -> None:
        """搜索框文本变化回调，实时过滤文件列表"""
        self._apply_search_filter()
        self._update_file_count()

    def _apply_search_filter(self) -> None:
        """
        根据搜索关键词过滤文件列表
        
        显示包含关键词的文件行，隐藏不匹配的行。
        搜索支持文件名模糊匹配（大小写不敏感）。
        """
        keyword = self.search_edit.text().strip().lower()

        if not keyword:
            for row in range(self.file_table.rowCount()):
                self.file_table.setRowHidden(row, False)
            return

        for row in range(self.file_table.rowCount()):
            if row < len(self.files):
                file_path = self.files[row]
                filename = os.path.basename(file_path).lower()
                is_match = keyword in filename
                self.file_table.setRowHidden(row, not is_match)

    def _on_browse_input_dir(self) -> None:
        """浏览输入目录"""
        dir_path = QFileDialog.getExistingDirectory(
            self,
            tr("select_directory"),
            "",
            QFileDialog.ShowDirsOnly,
        )
        if dir_path:
            self.input_dir = dir_path
            self.input_entry.setText(dir_path)
            self._scan_audio_files()

    def _on_browse_output_dir(self) -> None:
        """浏览输出目录"""
        dir_path = QFileDialog.getExistingDirectory(
            self,
            tr("output_directory"),
            "",
            QFileDialog.ShowDirsOnly,
        )
        if dir_path:
            self.output_dir = dir_path
            self.output_entry.setText(dir_path)

    def _scan_audio_files(self) -> None:
        """扫描目录中的音频文件"""
        if not self.input_dir:
            return

        supported_extensions = {".mp3", ".flac", ".aac", ".ogg", ".wav", ".m4a"}
        self.files.clear()
        self.file_table.setRowCount(0)

        for root, _, files in os.walk(self.input_dir):
            for filename in sorted(files):
                ext = Path(filename).suffix.lower()
                if ext in supported_extensions:
                    full_path = os.path.join(root, filename)
                    self.files.append(full_path)

                    row = self.file_table.rowCount()
                    self.file_table.insertRow(row)

                    check_item = QTableWidgetItem()
                    check_item.setCheckState(Qt.CheckState.Unchecked)
                    check_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                    self.file_table.setItem(row, 0, check_item)

                    self.file_table.setItem(row, 1, QTableWidgetItem(filename))
                    self.file_table.setItem(row, 2, QTableWidgetItem(ext.upper()))

                    size_kb = os.path.getsize(full_path) / 1024
                    size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"
                    self.file_table.setItem(row, 3, QTableWidgetItem(size_str))
                    self.file_table.setItem(row, 4, QTableWidgetItem(tr("converter.status.pending")))

        self._update_file_count()
        self._apply_search_filter()
        logger.info(f"扫描到 {len(self.files)} 个音频文件")

    def _on_trim_mode_changed(self) -> None:
        """裁剪模式切换回调"""
        is_auto = self.trim_auto_radio.isChecked()
        is_manual = self.trim_manual_radio.isChecked()
        is_duration = self.trim_duration_radio.isChecked()

        self.start_time_spin.setEnabled(is_manual or is_duration)
        self.end_time_spin.setEnabled(is_manual)
        self.duration_spin.setEnabled(is_duration)

    def _on_normalize_toggled(self, enabled: bool) -> None:
        """音量标准化开关切换"""
        self.loudness_spin.setEnabled(enabled)
        self.true_peak_spin.setEnabled(enabled)
        self.lra_spin.setEnabled(enabled)

    def _on_preset_changed(self, index: int) -> None:
        """预设选择变化回调"""
        if index < 0:
            return

        preset_data = self.preset_combo.currentData()
        if not preset_data:
            return

        try:
            config_dict = preset_data.get("config", {})
            if isinstance(config_dict, dict):
                config = EditorConfig.from_dict(config_dict)
                self._apply_config_to_ui(config)
        except Exception as e:
            logger.warning(f"应用预设失败: {e}")

    def _on_quality_changed(self, index: int) -> None:
        """输出质量选择变化回调"""
        if index < 0:
            return
        
        quality = self.quality_combo.currentData()
        if not quality or not isinstance(quality, OutputQuality):
            return
        
        self.config.output_quality = quality
        
        vbr_quality = quality.get_vbr_quality()
        max_bitrate = quality.get_max_bitrate() / 1000
        
        tip_text = f"VBR q:{vbr_quality}, ≤{max_bitrate:.0f}kbps"
        self.quality_tip_label.setText(tip_text)
        
        logger.debug(f"输出质量已更改为: {quality.display_name} (VBR q:{vbr_quality})")

    def _apply_config_to_ui(self, config: EditorConfig) -> None:
        """将配置应用到UI控件"""
        trim = config.trim
        normalize = config.normalize

        if trim.mode == TrimMode.AUTO:
            self.trim_auto_radio.setChecked(True)
        elif trim.mode == TrimMode.DURATION:
            self.trim_duration_radio.setChecked(True)
        else:
            self.trim_manual_radio.setChecked(True)

        self.start_time_spin.setValue(trim.start_time)
        if trim.end_time is not None:
            self.end_time_spin.setValue(trim.end_time)
        if trim.duration is not None:
            self.duration_spin.setValue(trim.duration)
        self.fade_in_spin.setValue(trim.fade_in)
        self.fade_out_spin.setValue(trim.fade_out)

        self.normalize_check.setChecked(True)
        self.loudness_spin.setValue(normalize.target_loudness)
        self.true_peak_spin.setValue(normalize.true_peak)
        self.lra_spin.setValue(normalize.lra)

        self.overwrite_check.setChecked(config.overwrite_original)

    def _get_current_config(self) -> EditorConfig:
        """从当前UI状态获取配置对象"""
        if self.trim_auto_radio.isChecked():
            trim_mode = TrimMode.AUTO
        elif self.trim_duration_radio.isChecked():
            trim_mode = TrimMode.DURATION
        else:
            trim_mode = TrimMode.MANUAL

        trim_config = TrimConfig(
            mode=trim_mode,
            start_time=self.start_time_spin.value(),
            end_time=self.end_time_spin.value(),
            duration=self.duration_spin.value(),
            fade_in=self.fade_in_spin.value(),
            fade_out=self.fade_out_spin.value(),
        )

        normalize_enabled = self.normalize_check.isChecked()
        normalize_config = NormalizeConfig(
            target_loudness=self.loudness_spin.value() if normalize_enabled else -16.0,
            true_peak=self.true_peak_spin.value(),
            lra=self.lra_spin.value(),
        )

        return EditorConfig(
            trim=trim_config,
            normalize=normalize_config,
            overwrite_original=self.overwrite_check.isChecked(),
        )

    def _on_select_all(self) -> None:
        """全选所有可见文件（搜索过滤后的文件）"""
        for row in range(self.file_table.rowCount()):
            if self.file_table.isRowHidden(row):
                continue
            item = self.file_table.item(row, 0)
            if item:
                item.setCheckState(Qt.CheckState.Checked)

    def _on_deselect_all(self) -> None:
        """取消全选所有可见文件"""
        for row in range(self.file_table.rowCount()):
            if self.file_table.isRowHidden(row):
                continue
            item = self.file_table.item(row, 0)
            if item:
                item.setCheckState(Qt.CheckState.Unchecked)

    def _on_clear_data(self) -> None:
        """清除数据"""
        msg_box = MessageBox(
            tr("confirm_clear_data"),
            tr("confirm_clear_data_desc"),
            self,
        )
        if msg_box.exec():
            self.files.clear()
            self.file_table.setRowCount(0)
            self.input_entry.clear()
            self.output_entry.clear()
            self.progress_bar.setValue(0)
            self.status_label.setText(tr("editor.editing_in_progress"))
            logger.info("已清除编辑页面数据")

    def _on_start_editing(self) -> None:
        """开始编辑"""
        selected_files = self._get_selected_files()
        if not selected_files:
            InfoBar.warning(
                title="",
                content=tr("editor.no_files_selected"),
                parent=self,
                position=InfoBarPosition.TOP_RIGHT,
                duration=3000,
            )
            return

        if not self.input_dir:
            InfoBar.warning(
                title="",
                content=tr("editor.select_input_directory"),
                parent=self,
                position=InfoBarPosition.TOP_RIGHT,
                duration=3000,
            )
            return

        output_dir = self.output_dir if self.output_dir and self.output_dir != tr("editor.same_directory") else self.input_dir
        config = self._get_current_config()

        self.worker = EditorWorker(selected_files, output_dir, config)
        self.worker.progress_updated.connect(self._on_progress_updated)
        self.worker.file_edited.connect(self._on_file_edited)
        self.worker.finished_all.connect(self._on_finished_all)
        self.worker.error_occurred.connect(self._on_error_occurred)

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self.status_label.setText(tr("editor.processing"))

        logger.info(f"开始编辑 {len(selected_files)} 个文件")
        self.worker.start()

    def _on_stop_editing(self) -> None:
        """停止编辑"""
        msg_box = MessageBox(
            tr("editor.confirm_stop_editing"),
            tr("editor.confirm_stop_editing_desc"),
            self,
        )
        if msg_box.exec():
            if self.worker:
                self.worker.stop()
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.status_label.setText(tr("editor.editing_in_progress"))
            logger.info("用户请求停止编辑")

    def _get_selected_files(self) -> list[str]:
        """
        获取用户勾选的文件列表

        只返回同时满足以下条件的文件：
        1. 勾选框已选中
        2. 行未被隐藏（搜索过滤后的可见行）
        3. 行索引在 self.files 范围内
        """
        selected_files = []
        for row in range(self.file_table.rowCount()):
            # 跳过被搜索过滤隐藏的行
            if self.file_table.isRowHidden(row):
                continue

            item = self.file_table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked and row < len(self.files):
                selected_files.append(self.files[row])
        return selected_files

    def _on_progress_updated(self, current: int, total: int, filename: str) -> None:
        """进度更新回调"""
        progress = int((current / total) * 100) if total > 0 else 0
        self.progress_bar.setValue(progress)
        self.status_label.setText(f"{current}/{total}: {filename}")

    def _on_file_edited(self, filepath: str, success: bool, message: str) -> None:
        """单文件编辑完成回调"""
        for row in range(self.file_table.rowCount()):
            if row < len(self.files) and self.files[row] == filepath:
                status_text = tr("editor.completed") if success else (tr("editor.failed") + ": " + message)
                self.file_table.setItem(row, 4, QTableWidgetItem(status_text))
                break

    def _on_finished_all(self, results: list[dict]) -> None:
        """全部编辑完成回调"""
        success_count = sum(1 for r in results if r.get("success"))
        fail_count = len(results) - success_count

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setValue(100)
        self.status_label.setText(
            tr("editor.edit_success_count").format(count=success_count) +
            ", " +
            tr("editor.edit_fail_count").format(count=fail_count)
        )

        InfoBar.success(
            title="",
            content=tr("editor.editing_completed"),
            parent=self,
            position=InfoBarPosition.TOP_RIGHT,
            duration=5000,
        )

        logger.info(f"编辑完成：成功 {success_count} 个，失败 {fail_count} 个")

    def _on_error_occurred(self, error_msg: str) -> None:
        """错误发生回调"""
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText(tr("error") + ": " + error_msg)

        InfoBar.error(
            title=tr("errors_occurred"),
            content=error_msg,
            parent=self,
            position=InfoBarPosition.TOP_RIGHT,
            duration=5000,
        )
        logger.error(f"编辑过程出错: {error_msg}")
