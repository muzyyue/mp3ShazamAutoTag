# -*- coding: utf-8 -*-
"""
音乐管理页面模块

该模块提供音乐文件管理功能的页面界面，包括元信息编辑、
封面管理和歌词管理等功能。

@module music_manager_page
@author Frontend Architect
@version 1.0.0
"""

from __future__ import annotations

import os
import time
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QPixmap, QImage, QCursor
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
try:
    from shiboken6 import isDeleted
except ImportError:
    def isDeleted(obj):
        """Fallback function for checking if object is deleted"""
        try:
            repr(obj)
            return False
        except RuntimeError:
            return True
from qfluentwidgets import (
    BodyLabel,
    ComboBox,
    ImageLabel,
    LineEdit,
    MessageBox,
    ProgressBar,
    PushButton,
    SearchLineEdit,
    SegmentedWidget,
    SubtitleLabel,
    TableWidget,
    TextEdit,
)
from qfluentwidgets import FluentIcon as FIF

if TYPE_CHECKING:
    from auto_tag.gui.workers.lyric_worker import LyricWorker, LyricEmbedWorker

from auto_tag.converter.metadata_manager import MetadataManager
from auto_tag.gui.i18n import tr
from auto_tag.gui.workers import LyricWorker, LyricEmbedWorker, SongSearchWorker
from auto_tag.gui.components import CoverPreviewDialog, SongSearchResultDialog
from auto_tag.lyric import LyricManager
from auto_tag.utils import is_file_in_use_error


class MusicManagerPage(QWidget):
    """
    音乐管理页面

    提供音频文件元信息编辑、封面管理和歌词管理的用户界面。

    Attributes:
        files (list[str]): 当前加载的文件路径列表
        selected_files (list[str]): 当前选中的文件路径列表
        current_file (str | None): 当前正在编辑的文件路径
        metadata_manager (MetadataManager): 元数据管理器实例
        lyric_manager (LyricManager): 歌词管理器实例
        lyric_worker (LyricWorker | None): 歌词获取工作线程
        embed_worker (LyricEmbedWorker | None): 歌词嵌入工作线程
        current_lyrics (dict | None): 当前文件的歌词数据
    """

    def __init__(self, parent=None) -> None:
        """
        初始化音乐管理页面

        Args:
            parent (QWidget | None): 父窗口组件
        """
        super().__init__(parent)

        self.logger = logging.getLogger(__name__)

        # 状态变量
        self.files: list[str] = []
        self.selected_files: list[str] = []
        self.current_file: str | None = None

        # 管理器实例
        self.metadata_manager = MetadataManager()
        self.lyric_manager = LyricManager()

        # 工作线程
        self.lyric_worker: LyricWorker | None = None
        self.embed_worker: LyricEmbedWorker | None = None
        self.search_worker: SongSearchWorker | None = None

        # 歌词数据缓存
        self.current_lyrics: dict | None = None
        self.lyrics_cache: dict[str, dict] = {}

        # 封面数据缓存（用于预览）
        self._current_cover_data: bytes | None = None

        # 预览对话框实例（延迟创建）
        self._preview_dialog: CoverPreviewDialog | None = None

        # 搜索相关状态（用于异步搜索后继续歌词获取）
        self._pending_file_paths: list[str] = []
        self._pending_provider: str = ""
        self._loading_dialog: QDialog | None = None
        self._batch_mode: bool = False  # 是否为批量模式（自动选择最佳匹配）
        self._batch_current_index: int = 0  # 批量模式当前处理的文件索引
        self._batch_results: dict[str, dict | None] = {}  # 批量模式结果缓存

        # 文件列表搜索功能
        self._search_timer: QTimer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._perform_search)

        # 构建 UI
        self._setup_ui()

    def _setup_ui(self) -> None:
        """
        构建音乐管理页面 UI 布局

        创建所有界面组件并使用布局管理器组织它们，
        包括文件列表、元信息编辑表单、封面管理和歌词管理区域。
        """
        # 主布局
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(40, 30, 40, 30)
        main_layout.setSpacing(20)

        # === 左侧：文件列表 ===
        left_panel = self._setup_file_list_panel()
        main_layout.addWidget(left_panel, stretch=1)

        # === 右侧：标签页区域 ===
        right_panel = self._setup_right_panel()
        main_layout.addWidget(right_panel, stretch=2)

    def _setup_file_list_panel(self) -> QWidget:
        """
        构建文件列表面板

        创建包含目录选择、文件表格和操作按钮的左侧面板。

        Returns:
            QWidget: 文件列表面板组件
        """
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # 标题
        self.file_list_title = SubtitleLabel(tr("music_manager.file_list"))
        layout.addWidget(self.file_list_title)

        # 目录选择区域
        dir_layout = QHBoxLayout()
        dir_layout.setSpacing(8)

        self.browse_btn = PushButton(FIF.FOLDER, tr("converter.browse"))
        self.browse_btn.setFixedHeight(36)
        self.browse_btn.clicked.connect(self._on_browse_directory)
        dir_layout.addWidget(self.browse_btn)

        # 文件列表搜索框
        self.search_edit = SearchLineEdit()
        self.search_edit.setPlaceholderText(tr("music_manager.search_placeholder"))
        self.search_edit.setFixedHeight(36)
        self.search_edit.setFixedWidth(240)
        self.search_edit.textChanged.connect(self._on_search_text_changed)
        dir_layout.addWidget(self.search_edit)

        dir_layout.addStretch()
        layout.addLayout(dir_layout)

        # 文件表格
        self.file_table = TableWidget()
        self.file_table.setColumnCount(4)
        self.file_table.setHorizontalHeaderLabels([
            tr("music_manager.check"), tr("music_manager.file_name"), tr("music_manager.format"), tr("music_manager.size")
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
        self.file_table.setColumnWidth(0, 50)
        self.file_table.setColumnWidth(2, 70)
        self.file_table.setColumnWidth(3, 80)
        self.file_table.setSelectionBehavior(TableWidget.SelectionBehavior.SelectRows)
        self.file_table.itemClicked.connect(self._on_file_clicked)
        self.file_table.itemChanged.connect(self._on_file_check_changed)
        layout.addWidget(self.file_table)

        # 操作按钮区域
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.check_all_btn = PushButton(tr("converter.check_all"))
        self.check_all_btn.setFixedHeight(32)
        self.check_all_btn.clicked.connect(self._on_check_all)
        btn_layout.addWidget(self.check_all_btn)

        self.uncheck_all_btn = PushButton(tr("converter.uncheck_all"))
        self.uncheck_all_btn.setFixedHeight(32)
        self.uncheck_all_btn.clicked.connect(self._on_uncheck_all)
        btn_layout.addWidget(self.uncheck_all_btn)

        self.clear_data_btn = PushButton(FIF.DELETE, tr("search.clear_data"))
        self.clear_data_btn.setFixedHeight(32)
        self.clear_data_btn.clicked.connect(self._on_clear_data)
        btn_layout.addWidget(self.clear_data_btn)

        layout.addLayout(btn_layout)

        return panel

    def _setup_right_panel(self) -> QWidget:
        """
        构建右侧面板

        创建包含标签页切换和内容区域的右侧面板。

        Returns:
            QWidget: 右侧面板组件
        """
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        # 标签页切换器
        self.segmented_widget = SegmentedWidget()
        self.metadata_tab = QWidget()
        self.lyrics_tab = QWidget()

        # 添加标签页
        self.segmented_widget.addItem(
            routeKey="metadata",
            text=tr("lyrics.metadata_tab"),
            onClick=lambda: self._switch_tab("metadata")
        )
        self.segmented_widget.addItem(
            routeKey="lyrics",
            text=tr("lyrics.lyrics_tab"),
            onClick=lambda: self._switch_tab("lyrics")
        )
        layout.addWidget(self.segmented_widget)

        # 内容区域（使用堆叠布局）
        self.content_stack = QWidget()
        self.stack_layout = QVBoxLayout(self.content_stack)
        self.stack_layout.setContentsMargins(0, 0, 0, 0)

        # 元信息标签页内容
        self._setup_metadata_tab()
        self.stack_layout.addWidget(self.metadata_tab)

        # 歌词标签页内容
        self._setup_lyrics_tab()
        self.stack_layout.addWidget(self.lyrics_tab)

        # 默认显示元信息标签页
        self.lyrics_tab.hide()

        layout.addWidget(self.content_stack)

        return panel

    def _setup_metadata_tab(self) -> None:
        """
        构建元信息标签页

        创建元信息编辑表单和封面管理区域。
        """
        layout = QVBoxLayout(self.metadata_tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        # === 元信息编辑表单 ===
        form_group = QWidget()
        form_layout = QGridLayout(form_group)
        form_layout.setSpacing(12)

        # 标题
        self.title_label = BodyLabel(tr("music_manager.fields.title"))
        form_layout.addWidget(self.title_label, 0, 0)
        self.title_edit = LineEdit()
        self.title_edit.setPlaceholderText(tr("music_manager.fields.title"))
        self.title_edit.setFixedHeight(36)
        form_layout.addWidget(self.title_edit, 0, 1)

        self.artist_label = BodyLabel(tr("music_manager.fields.artist"))
        form_layout.addWidget(self.artist_label, 1, 0)
        self.artist_edit = LineEdit()
        self.artist_edit.setPlaceholderText(tr("music_manager.fields.artist"))
        self.artist_edit.setFixedHeight(36)
        form_layout.addWidget(self.artist_edit, 1, 1)

        self.album_label = BodyLabel(tr("music_manager.fields.album"))
        form_layout.addWidget(self.album_label, 2, 0)
        self.album_edit = LineEdit()
        self.album_edit.setPlaceholderText(tr("music_manager.fields.album"))
        self.album_edit.setFixedHeight(36)
        form_layout.addWidget(self.album_edit, 2, 1)

        self.year_label = BodyLabel(tr("music_manager.fields.year"))
        form_layout.addWidget(self.year_label, 3, 0)
        self.year_edit = LineEdit()
        self.year_edit.setPlaceholderText(tr("music_manager.fields.year"))
        self.year_edit.setFixedHeight(36)
        form_layout.addWidget(self.year_edit, 3, 1)

        self.genre_label = BodyLabel(tr("music_manager.fields.genre"))
        form_layout.addWidget(self.genre_label, 4, 0)
        self.genre_edit = LineEdit()
        self.genre_edit.setPlaceholderText(tr("music_manager.fields.genre"))
        self.genre_edit.setFixedHeight(36)
        form_layout.addWidget(self.genre_edit, 4, 1)

        layout.addWidget(form_group)

        # === 保存按钮 ===
        save_layout = QHBoxLayout()
        save_layout.addStretch()

        self.save_metadata_btn = PushButton(FIF.SAVE, tr("music_manager.save"))
        self.save_metadata_btn.setFixedHeight(36)
        self.save_metadata_btn.clicked.connect(self._on_save_metadata)
        save_layout.addWidget(self.save_metadata_btn)

        layout.addLayout(save_layout)

        # === 封面管理区域 ===
        cover_group = QWidget()
        cover_layout = QVBoxLayout(cover_group)
        cover_layout.setSpacing(12)

        # 封面标题
        self.cover_title = SubtitleLabel(tr("music_manager.fields.cover"))
        cover_layout.addWidget(self.cover_title)

        # 封面显示区域
        self.cover_label = ImageLabel()
        self.cover_label.setFixedSize(200, 200)
        self.cover_label.scaledToWidth(200)
        self._set_default_cover()

        # 设置封面交互效果
        self._setup_cover_interaction()
        
        cover_layout.addWidget(self.cover_label)

        # 封面更换按钮
        cover_btn_layout = QHBoxLayout()
        cover_btn_layout.setSpacing(8)

        self.from_file_btn = PushButton(FIF.PHOTO, tr("music_manager.from_file"))
        self.from_file_btn.setFixedHeight(32)
        self.from_file_btn.clicked.connect(self._on_change_cover_from_file)
        cover_btn_layout.addWidget(self.from_file_btn)

        self.from_url_btn = PushButton(FIF.LINK, tr("music_manager.from_url"))
        self.from_url_btn.setFixedHeight(32)
        self.from_url_btn.clicked.connect(self._on_change_cover_from_url)
        cover_btn_layout.addWidget(self.from_url_btn)

        cover_btn_layout.addStretch()
        cover_layout.addLayout(cover_btn_layout)

        layout.addWidget(cover_group)
        layout.addStretch()

    def _setup_lyrics_tab(self) -> None:
        """
        构建歌词标签页

        创建歌词提供商选择、歌词预览和操作按钮区域。
        """
        layout = QVBoxLayout(self.lyrics_tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        # === 歌词提供商选择 ===
        provider_layout = QHBoxLayout()
        provider_layout.setSpacing(12)

        self.provider_label = BodyLabel(tr("lyrics.lyric_provider"))
        provider_layout.addWidget(self.provider_label)

        self.provider_combo = ComboBox()
        # 添加所有支持的歌词提供商
        from auto_tag.lyric import list_providers
        self._provider_list = list_providers()  # 保存提供商列表用于后续查询
        for idx, provider_name in enumerate(self._provider_list):
            self.provider_combo.addItem(tr(f'lyrics.providers.{provider_name}'))
        # 默认选中网易云音乐
        if 'netease' in self._provider_list:
            default_index = self._provider_list.index('netease')
            self.provider_combo.setCurrentIndex(default_index)
        self.provider_combo.setFixedHeight(36)
        self.provider_combo.setFixedWidth(150)
        provider_layout.addWidget(self.provider_combo)

        # === 歌词嵌入模式选择器 ===
        self.embed_mode_combo = ComboBox()
        self.embed_mode_combo.addItem(tr("lyrics.embed_only"))
        self.embed_mode_combo.addItem(tr("lyrics.embed_and_lrc"))
        self.embed_mode_combo.setFixedHeight(36)
        self.embed_mode_combo.setFixedWidth(180)
        self.embed_mode_combo.setToolTip(tr("lyrics.embed_only_desc") + " / " + tr("lyrics.embed_and_lrc_desc"))
        provider_layout.addWidget(self.embed_mode_combo)

        provider_layout.addStretch()
        layout.addLayout(provider_layout)

        # === 进度条 ===
        self.lyric_progress = ProgressBar()
        self.lyric_progress.setFixedHeight(4)
        self.lyric_progress.setValue(0)
        layout.addWidget(self.lyric_progress)

        # === 歌词预览区域 ===
        self.lyric_title = SubtitleLabel(tr("music_manager.fields.lyrics"))
        layout.addWidget(self.lyric_title)

        self.lyric_text = TextEdit()
        self.lyric_text.setPlaceholderText(tr("lyrics.no_lyrics_found"))
        self.lyric_text.setMinimumHeight(300)
        layout.addWidget(self.lyric_text)

        # === 操作按钮区域 ===
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.get_lyric_btn = PushButton(FIF.DOWNLOAD, tr("lyrics.get_lyrics"))
        self.get_lyric_btn.setFixedHeight(36)
        self.get_lyric_btn.clicked.connect(self._on_get_lyrics)
        btn_layout.addWidget(self.get_lyric_btn)

        self.embed_lyric_btn = PushButton(FIF.TAG, tr("lyrics.embed_lyrics"))
        self.embed_lyric_btn.setFixedHeight(36)
        self.embed_lyric_btn.clicked.connect(self._on_embed_lyrics)
        btn_layout.addWidget(self.embed_lyric_btn)

        self.save_lyric_btn = PushButton(FIF.SAVE, tr("lyrics.save_lyrics_to_file"))
        self.save_lyric_btn.setFixedHeight(36)
        self.save_lyric_btn.clicked.connect(self._on_save_lyrics)
        btn_layout.addWidget(self.save_lyric_btn)

        self.batch_get_lyric_btn = PushButton(FIF.SYNC, tr("lyrics.batch_get_lyrics"))
        self.batch_get_lyric_btn.setFixedHeight(36)
        self.batch_get_lyric_btn.clicked.connect(self._on_batch_get_lyrics)
        btn_layout.addWidget(self.batch_get_lyric_btn)

        layout.addLayout(btn_layout)

    def _set_default_cover(self) -> None:
        """
        设置默认封面图片

        当没有封面时显示占位图，并清除封面数据缓存。
        """
        # 创建一个灰色的默认封面
        default_pixmap = QPixmap(200, 200)
        default_pixmap.fill(Qt.GlobalColor.lightGray)
        self.cover_label.setPixmap(default_pixmap)

        # 清除封面数据缓存（禁用预览功能）
        self._current_cover_data = None

    def _setup_cover_interaction(self) -> None:
        """
        设置封面交互效果

        为封面标签添加点击事件和悬停效果，
        支持打开放大预览窗口。
        """
        # 设置鼠标悬停为手型
        self.cover_label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        # 启用鼠标追踪（用于 hover 效果）
        self.cover_label.setMouseTracking(True)

        # 连接点击事件
        self.cover_label.mousePressEvent = self._on_cover_clicked

    def _on_cover_clicked(self, event) -> None:
        """
        封面点击事件处理

        当用户点击封面且存在封面数据时，打开放大预览窗口。

        Args:
            event (QMouseEvent): 鼠标事件对象
        """
        # 只响应左键点击
        if event.button() != Qt.MouseButton.LeftButton:
            return

        # 检查是否有封面数据
        if not self._current_cover_data:
            return

        # 检查预览对话框是否有效（可能已被关闭并删除）
        if self._preview_dialog is not None:
            try:
                # 检查 C++ 对象是否已被删除
                if isDeleted(self._preview_dialog):
                    self._preview_dialog = CoverPreviewDialog(self)
            except (RuntimeError, AttributeError, TypeError):
                # 对象已无效，重新创建
                self._preview_dialog = CoverPreviewDialog(self)
        else:
            # 首次使用，创建新对话框
            self._preview_dialog = CoverPreviewDialog(self)

        # 显示预览
        self._preview_dialog.show_preview(self._current_cover_data)

    def _switch_tab(self, tab_key: str) -> None:
        """
        切换标签页

        Args:
            tab_key (str): 标签页标识（'metadata' 或 'lyrics'）
        """
        if tab_key == "metadata":
            self.metadata_tab.show()
            self.lyrics_tab.hide()
        else:
            self.metadata_tab.hide()
            self.lyrics_tab.show()

    def _on_browse_directory(self) -> None:
        """
        浏览目录按钮点击处理

        打开文件夹选择对话框，选择后扫描音频文件并填充表格。
        """
        try:
            directory = QFileDialog.getExistingDirectory(
                self,
                tr("select_directory"),
                "",
                QFileDialog.Option.ShowDirsOnly
            )

            if directory:
                self._scan_audio_files(directory)
        except Exception as e:
            self.logger.exception(f"Error in _on_browse_directory: {e}")
            MessageBox(tr("errors_occurred"), str(e), self).exec()

    def _on_clear_data(self) -> None:
        """
        清除数据按钮点击处理

        清除所有文件列表和缓存数据，释放文件句柄，
        解决 Windows 下文件被占用的问题。
        """
        try:
            # 清空文件列表数据
            self.files.clear()
            self.selected_files.clear()
            self.current_file = None

            # 清空表格
            self.file_table.setRowCount(0)

            # 清除搜索状态
            self._clear_search()

            # 清空歌词缓存
            self.lyrics_cache.clear()
            self.current_lyrics = None

            # 清空封面缓存
            self._current_cover_data = None

            # 重置表单为占位符状态
            self.title_edit.clear()
            self.artist_edit.clear()
            self.album_edit.clear()
            self.year_edit.clear()
            self.genre_edit.clear()

            # 重置封面预览（复用已有方法，确保行为一致）
            self._set_default_cover()

            # 重置歌词编辑区
            self.lyric_text.clear()

            # 停止可能正在运行的工作线程
            if hasattr(self, 'lyric_worker') and self.lyric_worker and self.lyric_worker.isRunning():
                self.lyric_worker.terminate()
                self.lyric_worker.wait()
                self.lyric_worker = None

            if hasattr(self, 'embed_worker') and self.embed_worker and self.embed_worker.isRunning():
                self.embed_worker.terminate()
                self.embed_worker.wait()
                self.embed_worker = None

            # 强制垃圾回收，释放文件句柄
            import gc
            gc.collect()

            self.logger.info("[MusicManagerPage] Data cleared, file handles released")
        except Exception as e:
            self.logger.exception(f"Error in _on_clear_data: {e}")

    def _scan_audio_files(self, directory: str) -> None:
        """
        扫描目录中的音频文件

        遍历目录查找所有支持的音频文件，并批量填充到文件表格中。
        扫描前会清理旧目录的歌词缓存，避免缓存污染。

        优化：使用 setUpdatesEnabled + setRowCount 批量更新，避免逐行插入触发重绘。

        Args:
            directory (str): 要扫描的目录路径
        """
        try:
            # 支持的音频格式（与 CustomFormatManager 内置格式保持一致）
            supported_formats = [
                '.mp3', '.flac', '.ogg', '.wav', '.m4a', '.aac',
                '.wma', '.opus'
            ]

            # 清空文件列表
            self.files.clear()

            # 清理旧目录的歌词缓存，避免缓存污染
            self.lyrics_cache.clear()
            self.current_lyrics = None
            self.lyric_text.clear()

            # 清除搜索状态（恢复显示所有文件）
            self._clear_search()

            # 遍历目录收集所有文件
            audio_files = []
            for root, dirs, filenames in os.walk(directory):
                # 跳过 test 目录
                if 'test' in dirs:
                    dirs.remove('test')

                for filename in filenames:
                    ext = os.path.splitext(filename)[1].lower()
                    if ext in supported_formats:
                        file_path = os.path.join(root, filename)
                        audio_files.append((filename, ext, file_path))

            # 批量更新表格（禁用 UI 更新以提升性能）
            self.file_table.setUpdatesEnabled(False)
            try:
                self.file_table.setRowCount(0)
                self.file_table.setRowCount(len(audio_files))

                for row, (filename, ext, file_path) in enumerate(audio_files):
                    self.files.append(file_path)

                    # 勾选框列
                    checkbox_item = QTableWidgetItem()
                    checkbox_item.setFlags(
                        Qt.ItemFlag.ItemIsEnabled |
                        Qt.ItemFlag.ItemIsUserCheckable
                    )
                    checkbox_item.setCheckState(Qt.CheckState.Unchecked)
                    self.file_table.setItem(row, 0, checkbox_item)

                    # 文件名列
                    filename_item = QTableWidgetItem(filename)
                    filename_item.setFlags(
                        filename_item.flags() & ~Qt.ItemFlag.ItemIsEditable
                    )
                    filename_item.setData(Qt.ItemDataRole.UserRole, file_path)
                    filename_item.setToolTip(file_path)
                    self.file_table.setItem(row, 1, filename_item)

                    # 格式列
                    format_item = QTableWidgetItem(ext.upper().lstrip('.'))
                    format_item.setFlags(
                        format_item.flags() & ~Qt.ItemFlag.ItemIsEditable
                    )
                    self.file_table.setItem(row, 2, format_item)

                    # 大小列
                    try:
                        size = os.path.getsize(file_path)
                        size_str = self._format_file_size(size)
                    except OSError:
                        size_str = "N/A"
                    size_item = QTableWidgetItem(size_str)
                    size_item.setFlags(
                        size_item.flags() & ~Qt.ItemFlag.ItemIsEditable
                    )
                    self.file_table.setItem(row, 3, size_item)
            finally:
                self.file_table.setUpdatesEnabled(True)
        except Exception as e:
            self.logger.exception(f"Error in _scan_audio_files: {e}")
            MessageBox(tr("errors_occurred"), str(e), self).exec()

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

    def _on_file_clicked(self, item: QTableWidgetItem) -> None:
        """
        文件表格行点击处理

        加载选中文件的元信息和歌词。

        Args:
            item (QTableWidgetItem): 被点击的表格项
        """
        row = item.row()
        filename_item = self.file_table.item(row, 1)
        if filename_item:
            file_path = filename_item.data(Qt.ItemDataRole.UserRole)
            self._load_file_info(file_path)

    def _on_file_check_changed(self, item: QTableWidgetItem) -> None:
        """
        文件勾选状态变更处理

        更新选中文件列表。

        Args:
            item (QTableWidgetItem): 状态变更的表格项
        """
        if item.column() == 0:
            self._update_selected_files()

    def _update_selected_files(self) -> None:
        """
        更新选中文件列表

        遍历表格收集所有勾选的文件路径。
        """
        self.selected_files.clear()

        for row in range(self.file_table.rowCount()):
            checkbox_item = self.file_table.item(row, 0)
            if checkbox_item and checkbox_item.checkState() == Qt.CheckState.Checked:
                filename_item = self.file_table.item(row, 1)
                if filename_item:
                    file_path = filename_item.data(Qt.ItemDataRole.UserRole)
                    self.selected_files.append(file_path)

    def _load_file_info(self, file_path: str) -> None:
        """
        加载文件信息

        读取文件的元数据和封面，并显示在界面上。
        优先从歌词缓存加载，缓存未命中时再尝试从文件嵌入式标签提取。

        Args:
            file_path (str): 要加载的文件路径
        """
        self.current_file = file_path

        try:
            # 读取元数据
            metadata = self.metadata_manager.read_metadata(file_path)

            # 填充表单
            self.title_edit.setText(metadata.get('title', ''))
            self.artist_edit.setText(metadata.get('artist', ''))
            self.album_edit.setText(metadata.get('album', ''))
            self.year_edit.setText(metadata.get('year', ''))
            self.genre_edit.setText(metadata.get('genre', ''))

            # 显示封面
            cover_data = metadata.get('cover')
            if cover_data:
                self._display_cover(cover_data)
            else:
                self._set_default_cover()
                self._current_cover_data = None

            # 优先从缓存加载歌词（避免重复提取或重复请求）
            if file_path in self.lyrics_cache:
                self.current_lyrics = self.lyrics_cache[file_path]
                synced = self.current_lyrics.get('synced_lyrics', '')
                plain = self.current_lyrics.get('plain_lyrics', '')
                self.lyric_text.setText(synced or plain)
            else:
                # 缓存未命中，尝试从文件嵌入式标签提取
                lyrics = self.lyric_manager.extract_lyrics(file_path)
                if lyrics:
                    self.current_lyrics = lyrics
                    self.lyrics_cache[file_path] = lyrics  # 回写缓存
                    synced = lyrics.get('synced_lyrics', '')
                    plain = lyrics.get('plain_lyrics', '')
                    self.lyric_text.setText(synced or plain)
                else:
                    self.current_lyrics = None
                    self.lyric_text.clear()

        except Exception as e:
            MessageBox(tr("errors_occurred"), str(e), self).exec()

    def _display_cover(self, cover_data: bytes) -> None:
        """
        显示封面图片

        将二进制封面数据显示在 ImageLabel 中，并缓存原始数据用于预览。

        Args:
            cover_data (bytes): 封面图片的二进制数据
        """
        try:
            # 缓存原始数据（用于高分辨率预览）
            self._current_cover_data = cover_data

            image = QImage()
            image.loadFromData(cover_data)
            if not image.isNull():
                pixmap = QPixmap.fromImage(image)
                self.cover_label.setPixmap(pixmap.scaled(
                    200, 200,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                ))
            else:
                self._set_default_cover()
                self._current_cover_data = None
        except Exception:
            self._set_default_cover()
            self._current_cover_data = None

    def _on_check_all(self) -> None:
        """全选：将所有文件的勾选状态设为选中"""
        for row in range(self.file_table.rowCount()):
            item = self.file_table.item(row, 0)
            if item:
                item.setCheckState(Qt.CheckState.Checked)
        self._update_selected_files()

    def _on_uncheck_all(self) -> None:
        """取消全选：将所有文件的勾选状态设为未选中"""
        for row in range(self.file_table.rowCount()):
            item = self.file_table.item(row, 0)
            if item:
                item.setCheckState(Qt.CheckState.Unchecked)
        self._update_selected_files()

    def _on_search_text_changed(self, text: str) -> None:
        """
        搜索文本变更处理

        当用户在搜索框中输入文本时触发，重启防抖定时器以延迟执行搜索。

        Args:
            text (str): 当前搜索框中的文本
        """
        self._search_timer.start(300)

    def _perform_search(self) -> None:
        """
        执行文件列表搜索过滤

        从搜索框获取关键词并调用过滤方法，
        使用防抖机制避免频繁更新导致的性能问题。
        """
        keyword = self.search_edit.text().strip().lower()
        self._filter_files(keyword)

    def _filter_files(self, keyword: str) -> None:
        """
        根据关键词过滤文件列表

        遍历表格所有行，根据文件名是否包含关键词来决定显示或隐藏该行。
        支持大小写不敏感的模糊匹配。

        Args:
            keyword (str): 搜索关键词（已转小写），空字符串表示显示所有文件
        """
        self.file_table.setUpdatesEnabled(False)
        try:
            for row in range(self.file_table.rowCount()):
                filename_item = self.file_table.item(row, 1)
                if filename_item:
                    filename = filename_item.text().lower()
                    should_show = (keyword in filename) if keyword else True
                    self.file_table.setRowHidden(row, not should_show)
        finally:
            self.file_table.setUpdatesEnabled(True)

    def _clear_search(self) -> None:
        """
        清除搜索状态

        清空搜索框内容并恢复显示所有文件行。
        在切换目录或清除数据时调用此方法。
        """
        self.search_edit.clear()
        self._filter_files("")

    def _on_save_metadata(self) -> None:
        """
        保存元数据按钮点击处理

        将当前编辑的元数据保存到文件中。
        如果选中了多个文件，则进行批量编辑。
        包含文件占用重试机制，自动重试最多 3 次。
        """
        try:
            if not self.current_file and not self.selected_files:
                MessageBox(tr("no_file_selected"), tr("select_files"), self).exec()
                return

            # 收集元数据
            metadata = {
                'title': self.title_edit.text(),
                'artist': self.artist_edit.text(),
                'album': self.album_edit.text(),
                'year': self.year_edit.text(),
                'genre': self.genre_edit.text(),
            }

            if self.selected_files:
                # 批量编辑 — 每个文件独立处理，一个失败不影响其他
                success_list = []
                fail_list = []
                for file_path in self.selected_files:
                    try:
                        ok = self.metadata_manager.write_metadata(file_path, metadata)
                        if ok:
                            success_list.append(file_path)
                        else:
                            fail_list.append(file_path)
                    except Exception as item_exc:
                        self.logger.exception(f"保存元数据失败: {file_path}: {item_exc}")
                        fail_list.append(file_path)

                if success_list:
                    msg = f"{tr('metadata_save_success')}\n{tr('success_count').format(count=len(success_list))}"
                    if fail_list:
                        msg += f"\n{tr('fail_count').format(count=len(fail_list))}"
                    MessageBox(tr("success"), msg, self).exec()
                else:
                    MessageBox(tr("errors_occurred"), tr("metadata_save_failed"), self).exec()
            elif self.current_file:
                # 单文件编辑 - 包含文件占用重试机制
                max_retries = 3
                retry_delay = 0.5
                success = False
                for attempt in range(max_retries + 1):
                    try:
                        success = self.metadata_manager.write_metadata(
                            self.current_file, metadata
                        )
                        if success:
                            break
                        raise RuntimeError(tr("metadata_save_failed"))
                    except Exception as save_exc:
                        if is_file_in_use_error(save_exc) and attempt < max_retries:
                            wait_time = retry_delay * (attempt + 1)
                            logging.warning(
                                f"[MusicManagerPage] 文件被占用，将在 {wait_time:.1f} 秒后重试 "
                                f"({attempt + 1}/{max_retries}): {save_exc}"
                            )
                            time.sleep(wait_time)
                            continue
                        raise

                if success:
                    MessageBox(tr("success"), tr("metadata_save_success"), self).exec()
                else:
                    MessageBox(tr("errors_occurred"), tr("metadata_save_failed"), self).exec()
        except Exception as e:
            self.logger.exception(f"Error in _on_save_metadata: {e}")
            MessageBox(tr("errors_occurred"), str(e), self).exec()

    def _on_change_cover_from_file(self) -> None:
        """
        从文件更换封面按钮点击处理

        打开文件选择对话框，选择图片文件作为封面。
        """
        try:
            if not self.current_file:
                MessageBox(tr("no_file_selected"), tr("select_files"), self).exec()
                return

            file_path, _ = QFileDialog.getOpenFileName(
                self,
                tr("select_image_file"),
                "",
                "Images (*.png *.jpg *.jpeg *.bmp);;All Files (*)"
            )

            if file_path:
                try:
                    with open(file_path, 'rb') as f:
                        cover_data = f.read()

                    success = self.metadata_manager.set_cover(
                        self.current_file, cover_data
                    )

                    if success:
                        self._display_cover(cover_data)
                        MessageBox(tr("success"), tr("cover_updated"), self).exec()
                    else:
                        MessageBox(tr("errors_occurred"), tr("cover_update_failed"), self).exec()
                except Exception as e:
                    self.logger.exception(f"Error in _on_change_cover_from_file (inner): {e}")
                    MessageBox(tr("errors_occurred"), str(e), self).exec()
        except Exception as e:
            self.logger.exception(f"Error in _on_change_cover_from_file: {e}")
            MessageBox(tr("errors_occurred"), str(e), self).exec()

    def _on_change_cover_from_url(self) -> None:
        """
        从 URL 更换封面按钮点击处理

        弹出输入对话框，输入图片 URL 下载作为封面。
        """
        try:
            if not self.current_file:
                MessageBox(tr("no_file_selected"), tr("select_files"), self).exec()
                return

            url, ok = QInputDialog.getText(
                self,
                tr("from_url"),
                tr("enter_image_url")
            )

            if ok and url:
                try:
                    import requests
                    response = requests.get(url, timeout=10)
                    response.raise_for_status()

                    cover_data = response.content
                    success = self.metadata_manager.set_cover(
                        self.current_file, cover_data
                    )

                    if success:
                        self._display_cover(cover_data)
                        MessageBox(tr("success"), tr("cover_updated"), self).exec()
                    else:
                        MessageBox(tr("errors_occurred"), tr("cover_update_failed"), self).exec()
                except Exception as e:
                    self.logger.exception(f"Error in _on_change_cover_from_url (inner): {e}")
                    MessageBox(tr("errors_occurred"), str(e), self).exec()
        except Exception as e:
            self.logger.exception(f"Error in _on_change_cover_from_url: {e}")
            MessageBox(tr("errors_occurred"), str(e), self).exec()

    def _on_get_lyrics(self) -> None:
        """
        获取歌词按钮点击处理

        从选中的提供商获取当前文件的歌词。
        使用单首模式，弹出搜索结果选择对话框。
        """
        try:
            if not self.current_file:
                MessageBox(tr("no_file_selected"), tr("select_files"), self).exec()
                return

            # 通过当前索引获取提供商名称
            current_index = self.provider_combo.currentIndex()
            provider = self._provider_list[current_index] if 0 <= current_index < len(self._provider_list) else 'netease'
            # 单首模式：batch_mode=False（弹出选择对话框）
            self._start_lyric_fetch([self.current_file], provider, batch_mode=False)
        except Exception as e:
            self.logger.exception(f"Error in _on_get_lyrics: {e}")
            MessageBox(tr("errors_occurred"), str(e), self).exec()

    def _on_batch_get_lyrics(self) -> None:
        """
        批量获取歌词按钮点击处理

        从选中的提供商批量获取所有选中文件的歌词。
        对于网易云和酷狗音乐，自动选择匹配度最高的结果。
        """
        if not self.selected_files:
            MessageBox(tr("no_file_selected"), tr("select_files"), self).exec()
            return

        # 通过当前索引获取提供商名称
        current_index = self.provider_combo.currentIndex()
        provider = self._provider_list[current_index] if 0 <= current_index < len(self._provider_list) else 'netease'
        # 使用 batch_mode=True 启用自动选择最佳匹配
        self._start_lyric_fetch(self.selected_files, provider, batch_mode=True)

    def _start_lyric_fetch(self, file_paths: list[str], provider: str, batch_mode: bool = False) -> None:
        """
        启动歌词获取任务

        创建工作线程并在后台获取歌词。
        对于网易云和酷狗音乐：
        - 单首模式（batch_mode=False）：弹出搜索结果选择对话框
        - 批量模式（batch_mode=True）：自动选择匹配度最高的结果

        Args:
            file_paths (list[str]): 要获取歌词的文件路径列表
            provider (str): 歌词提供商名称
            batch_mode (bool): 是否为批量模式（默认 False）
        """
        try:
            # 重置进度
            self.lyric_progress.setValue(0)
            self.get_lyric_btn.setEnabled(False)
            self.batch_get_lyric_btn.setEnabled(False)

            # 对于网易云和酷狗，需要先选择歌曲
            if provider in ['netease', 'kugou'] and len(file_paths) > 0:
                self._pending_file_paths = file_paths
                self._pending_provider = provider
                self._batch_mode = batch_mode

                if batch_mode:
                    self._batch_current_index = 0
                    self._batch_results = {}
                    self._process_current_batch_file()
                else:
                    self._start_search_and_show_dialog(file_paths[0], provider)
                return

            # 其他提供商直接获取歌词
            self.lyric_worker = LyricWorker(
                file_paths=file_paths,
                provider=provider
            )

            # 连接信号
            self.lyric_worker.progress_updated.connect(self._on_lyric_progress)
            self.lyric_worker.lyric_fetched.connect(self._on_lyric_fetched)
            self.lyric_worker.finished_all.connect(self._on_lyric_finished)
            self.lyric_worker.error_occurred.connect(self._on_lyric_error)

            # 启动线程
            self.lyric_worker.start()
        except Exception as e:
            self.logger.exception(f"Error in _start_lyric_fetch: {e}")
            self.get_lyric_btn.setEnabled(True)
            self.batch_get_lyric_btn.setEnabled(True)
            MessageBox(tr("errors_occurred"), str(e), self).exec()

    def _process_current_batch_file(self) -> None:
        """
        处理批量模式下的当前文件

        根据 _batch_current_index 获取当前要处理的文件路径，
        启动搜索流程。如果所有文件都已处理完毕，则显示最终结果。
        """
        if self._batch_current_index >= len(self._pending_file_paths):
            self._on_batch_all_finished()
            return

        current_file = self._pending_file_paths[self._batch_current_index]
        self._start_search_and_show_dialog(current_file, self._pending_provider)

    def _on_batch_all_finished(self) -> None:
        """
        批量处理全部完成后的回调

        统计成功/失败数量，显示结果对话框，恢复按钮状态。
        """
        self.get_lyric_btn.setEnabled(True)
        self.batch_get_lyric_btn.setEnabled(True)
        self.lyric_progress.setValue(100)

        success_count = sum(1 for v in self._batch_results.values() if v is not None)
        fail_count = len(self._batch_results) - success_count

        MessageBox(
            tr("success"),
            f"{tr('batch_lyric_fetch_complete')}\n"
            f"{tr('success_count').format(count=success_count)}\n"
            f"{tr('fail_count').format(count=fail_count)}",
            self
        ).exec()

    def _start_search_and_show_dialog(
        self,
        file_path: str,
        provider: str,
    ) -> None:
        """
        启动后台搜索并显示加载动画

        在后台线程中执行搜索，同时显示非阻塞加载对话框，
        搜索完成后自动弹出搜索结果选择对话框。

        注意：使用 show() 而非 exec()，避免嵌套事件循环导致 UI 未响应。

        Args:
            file_path: 音频文件路径
            provider: 歌词提供商名称
        """
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QMovie
        from qfluentwidgets import IndeterminateProgressBar

        # 创建加载对话框（非模态，使用 show() 而非 exec()）
        self._loading_dialog = QDialog(self)
        self._loading_dialog.setWindowTitle(tr("searching"))
        self._loading_dialog.setFixedSize(320, 160)
        self._loading_dialog.setWindowModality(Qt.WindowModality.NonModal)
        self._loading_dialog.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

        layout = QVBoxLayout(self._loading_dialog)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        # 顶部：加载动画图标
        loading_icon_label = QLabel()
        loading_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading_icon_label.setFixedSize(48, 48)
        layout.addWidget(loading_icon_label)

        # 中间：提示文字
        loading_label = QLabel(tr("searching_please_wait"))
        loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading_label.setWordWrap(True)
        layout.addWidget(loading_label)

        # 进度条
        progress_bar = IndeterminateProgressBar()
        layout.addWidget(progress_bar)

        # 底部：取消按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedWidth(80)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 加载动画（Fluent SYNC 图标）
        from qfluentwidgets import FluentIcon
        loading_icon_label.setPixmap(FluentIcon.SYNC.icon().pixmap(48, 48))

        # 创建搜索工作线程
        self.search_worker = SongSearchWorker(
            file_path=file_path,
            provider=provider,
        )

        # 取消搜索标志
        self._search_cancelled = False

        def on_cancel_clicked() -> None:
            """取消按钮点击回调"""
            self._search_cancelled = True
            self.search_worker.terminate()
            self.search_worker.wait()
            self._loading_dialog.close()
            self.get_lyric_btn.setEnabled(True)
            self.batch_get_lyric_btn.setEnabled(True)

        cancel_btn.clicked.connect(on_cancel_clicked)

        def on_search_finished(songs: list[dict]) -> None:
            """搜索完成回调：关闭加载对话框，根据模式处理结果"""
            try:
                if self._loading_dialog:
                    self._loading_dialog.close()

                if not songs:
                    if getattr(self, '_batch_mode', False):
                        current_file = self._pending_file_paths[self._batch_current_index]
                        self._batch_results[current_file] = None
                        self.logger.warning(f"[批量模式] 文件搜索无结果: {current_file}")
                        self._batch_current_index += 1
                        self._process_current_batch_file()
                    else:
                        MessageBox(
                            tr("no_search_results"),
                            tr("search_failed"),
                            self
                        ).show()
                        self.get_lyric_btn.setEnabled(True)
                        self.batch_get_lyric_btn.setEnabled(True)
                    return

                # 批量模式下自动选择最佳匹配结果
                if getattr(self, '_batch_mode', False):
                    best_match = self.lyric_manager.select_best_match(
                        songs=songs,
                        file_path=file_path,
                        provider=provider
                    )
                    if best_match:
                        self.logger.info(f"[批量模式] ({self._batch_current_index + 1}/{len(self._pending_file_paths)}) 自动选择最佳匹配: {best_match.get('name', '')} - {best_match.get('artist', '')}")
                        self._continue_fetch_for_single(file_path, best_match.get('id'))
                    else:
                        current_file = self._pending_file_paths[self._batch_current_index]
                        self._batch_results[current_file] = None
                        self.logger.warning(f"[批量模式] 无法选择最佳匹配: {current_file}")
                        self._batch_current_index += 1
                        self._process_current_batch_file()
                    return

                # 如果只有一个结果，直接进入歌词获取
                if len(songs) == 1:
                    self._continue_fetch(songs[0].get('id'))
                    return

                # 多个结果时显示选择对话框（单首模式）
                self._show_result_dialog(songs)
            except Exception as e:
                self.logger.error(f"[批量模式] 搜索完成回调异常: {e}", exc_info=True)
                if self._loading_dialog:
                    self._loading_dialog.close()
                self.get_lyric_btn.setEnabled(True)
                self.batch_get_lyric_btn.setEnabled(True)
                MessageBox(
                    tr("search_error"),
                    str(e),
                    self
                ).show()

        def on_search_error(error_msg: str) -> None:
            """搜索错误回调"""
            if self._loading_dialog:
                self._loading_dialog.close()
            MessageBox(
                tr("search_error"),
                error_msg,
                self
            ).show()
            self.get_lyric_btn.setEnabled(True)
            self.batch_get_lyric_btn.setEnabled(True)

        self.search_worker.search_finished.connect(on_search_finished)
        self.search_worker.search_error.connect(on_search_error)

        # 启动搜索线程并显示加载对话框（非阻塞）
        self._search_cancelled = False
        self.search_worker.start()
        self._loading_dialog.show()

    def _continue_fetch(self, selected_song_id: int | None) -> None:
        """
        继续歌词获取流程（用户选择歌曲后调用）

        Args:
            selected_song_id: 选中的歌曲 ID
        """
        if selected_song_id is None:
            self.get_lyric_btn.setEnabled(True)
            self.batch_get_lyric_btn.setEnabled(True)
            return

        # 创建工作线程，传入选中的歌曲 ID
        self.lyric_worker = LyricWorker(
            file_paths=self._pending_file_paths,
            provider=self._pending_provider,
            song_id=selected_song_id
        )

        # 连接信号
        self.lyric_worker.progress_updated.connect(self._on_lyric_progress)
        self.lyric_worker.lyric_fetched.connect(self._on_lyric_fetched)
        self.lyric_worker.finished_all.connect(self._on_lyric_finished)
        self.lyric_worker.error_occurred.connect(self._on_lyric_error)

        # 启动线程
        self.lyric_worker.start()

    def _continue_fetch_for_single(self, file_path: str, selected_song_id: int | None) -> None:
        """
        批量模式下为单个文件继续歌词获取流程

        只处理当前这一个文件，获取完成后自动触发下一个文件的处理。

        Args:
            file_path: 当前正在处理的文件路径
            selected_song_id: 搜索结果中选中的歌曲 ID
        """
        if selected_song_id is None:
            current_file = self._pending_file_paths[self._batch_current_index]
            self._batch_results[current_file] = None
            self._batch_current_index += 1
            self._process_current_batch_file()
            return

        # 创建工作线程，只传入当前单个文件
        self.lyric_worker = LyricWorker(
            file_paths=[file_path],
            provider=self._pending_provider,
            song_id=selected_song_id
        )

        # 连接信号
        self.lyric_worker.progress_updated.connect(self._on_lyric_progress)
        self.lyric_worker.lyric_fetched.connect(self._on_lyric_fetched)
        self.lyric_worker.finished_all.connect(self._on_batch_single_finished)
        self.lyric_worker.error_occurred.connect(self._on_lyric_error)

        # 启动线程
        self.lyric_worker.start()

    def _on_batch_single_finished(self, results: dict) -> None:
        """
        批量模式下单个文件歌词获取完成回调

        保存当前文件的结果，更新进度，然后自动处理下一个文件。
        如果所有文件都已处理完毕，则显示最终统计结果。

        Args:
            results (dict): 当前文件的获取结果 {file_path: lyrics_data}
        """
        current_file = self._pending_file_paths[self._batch_current_index]
        lyrics = results.get(current_file)
        self._batch_results[current_file] = lyrics

        if lyrics:
            self.logger.info(f"[批量模式] ({self._batch_current_index + 1}/{len(self._pending_file_paths)}) 歌词获取成功: {current_file}")
        else:
            self.logger.warning(f"[批量模式] ({self._batch_current_index + 1}/{len(self._pending_file_paths)}) 歌词获取失败: {current_file}")

        # 更新进度
        progress = int((self._batch_current_index + 1) / len(self._pending_file_paths) * 100)
        self.lyric_progress.setValue(progress)

        # 处理下一个文件
        self._batch_current_index += 1
        self._process_current_batch_file()

    def _show_result_dialog(self, songs: list[dict]) -> None:
        """
        显示搜索结果选择对话框

        当搜索返回多个结果时，显示 SongSearchResultDialog 让用户选择，
        选择后继续歌词获取流程。

        Args:
            songs: 搜索结果歌曲列表
        """
        dialog = SongSearchResultDialog(self)
        dialog.set_search_results(songs, provider=self._pending_provider)

        def on_dialog_finished(result: int) -> None:
            """对话框关闭回调"""
            if result == QDialog.DialogCode.Accepted:
                self._continue_fetch(dialog.selected_song_id)
            else:
                # 用户取消选择
                self.get_lyric_btn.setEnabled(True)
                self.batch_get_lyric_btn.setEnabled(True)

        dialog.finished.connect(on_dialog_finished)
        dialog.show()

    def _show_search_dialog(
        self,
        file_path: str,
        provider: str
    ) -> int | None:
        """
        显示搜索结果选择对话框（已弃用，保留兼容性）

        注意：此方法会在主线程同步阻塞约 15 秒，
        请使用 _start_search_and_show_dialog() 替代。

        Args:
            file_path (str): 音频文件路径
            provider (str): 提供商名称

        Returns:
            int | None: 选中的歌曲 ID，用户取消返回 None
        """
        try:
            manager = LyricManager()
            songs = manager.search_songs(file_path, provider)

            if not songs:
                MessageBox(
                    tr("no_search_results"),
                    tr("search_failed"),
                    self
                ).exec()
                return None

            # 如果只有一个结果，直接返回
            if len(songs) == 1:
                return songs[0].get('id')

            # 多个结果时显示选择对话框
            dialog = SongSearchResultDialog(self)
            dialog.set_search_results(songs, provider=provider)

            if dialog.exec():
                return dialog.selected_song_id

            return None

        except Exception as e:
            MessageBox(
                tr("search_error") + f": {str(e)}",
                tr("error"),
                self
            ).exec()
            return None

    def _on_lyric_progress(self, done: int, total: int, remaining: int) -> None:
        """
        歌词获取进度更新回调

        Args:
            done (int): 已完成数量
            total (int): 总数量
            remaining (int): 剩余时间（秒）
        """
        if total > 0:
            value = int(done / total * 100)
            self.lyric_progress.setValue(value)

    def _on_lyric_fetched(self, file_path: str, lyrics: dict | None) -> None:
        """
        单个文件歌词获取完成回调

        检查文件路径是否仍在当前文件列表中，
        防止用户切换目录后异步回调污染界面显示。

        Args:
            file_path (str): 文件路径
            lyrics (dict | None): 歌词数据，失败则为 None
        """
        # 缓存歌词（始终缓存，不依赖文件是否仍在列表中）
        if lyrics:
            self.lyrics_cache[file_path] = lyrics

        # 显示歌词：需同时满足 3 个条件
        # 1. 文件路径仍在当前文件列表中（防止用户已切换目录）
        # 2. 文件为当前选中文件
        # 3. 歌词数据有效
        if file_path in self.files and file_path == self.current_file and lyrics:
            self.current_lyrics = lyrics
            synced = lyrics.get('synced_lyrics', '')
            plain = lyrics.get('plain_lyrics', '')
            self.lyric_text.setText(synced or plain)

    def _on_lyric_finished(self, results: dict) -> None:
        """
        所有歌词获取完成回调

        Args:
            results (dict): 所有文件的获取结果
        """
        self.lyric_progress.setValue(100)
        self.get_lyric_btn.setEnabled(True)
        self.batch_get_lyric_btn.setEnabled(True)

        # 统计结果
        success_count = sum(1 for v in results.values() if v is not None)
        fail_count = len(results) - success_count

        MessageBox(
            tr("success"),
            f"{tr('batch_lyric_fetch_complete')}\n"
            f"{tr('success_count').format(count=success_count)}\n"
            f"{tr('fail_count').format(count=fail_count)}",
            self
        ).exec()

    def _on_lyric_error(self, error_msg: str) -> None:
        """
        歌词获取错误回调

        Args:
            error_msg (str): 错误信息
        """
        self.get_lyric_btn.setEnabled(True)
        self.batch_get_lyric_btn.setEnabled(True)
        MessageBox(tr("errors_occurred"), error_msg, self).exec()

    def _on_embed_lyrics(self) -> None:
        """
        嵌入歌词按钮点击处理

        将当前歌词编辑器中的歌词嵌入到当前文件。
        根据嵌入模式选择器决定仅嵌入文件或同时生成 LRC 文件。
        """
        try:
            if not self.current_file:
                MessageBox(tr("no_file_selected"), tr("select_files"), self).exec()
                return

            lyrics_text = self.lyric_text.toPlainText()
            if not lyrics_text:
                MessageBox(tr("no_lyrics_found"), tr("get_lyrics"), self).exec()
                return

            # 获取嵌入模式
            mode_index = self.embed_mode_combo.currentIndex()
            mode = 'embed_and_lrc' if mode_index == 1 else 'embed_only'

            try:
                success = self.lyric_manager.embed_lyrics(
                    self.current_file,
                    lyrics_text,
                    'lrc',
                    mode=mode
                )

                if success:
                    self.lyrics_cache.pop(self.current_file, None)
                    verified = self.lyric_manager.extract_lyrics(self.current_file)
                    if verified:
                        verified_text = verified.get('synced_lyrics', '') or verified.get('plain_lyrics', '')
                        if lyrics_text.strip() != verified_text.strip():
                            self.logger.warning(f"嵌入验证失败: 文件中的歌词与预期不一致")
                            self.current_lyrics = verified
                            self.lyrics_cache[self.current_file] = verified
                            synced = verified.get('synced_lyrics', '')
                            plain = verified.get('plain_lyrics', '')
                            self.lyric_text.setText(synced or plain)
                            MessageBox(
                                tr("errors_occurred"),
                                tr("lyric_embed_verify_failed"),
                                self
                            ).exec()
                            return
                    self.current_lyrics = {
                        'synced_lyrics': lyrics_text,
                        'plain_lyrics': lyrics_text,
                    }
                    if mode == 'embed_and_lrc':
                        MessageBox(tr("success"), tr("lyric_embed_success") + "\n" + tr("embed_and_lrc_desc"), self).exec()
                    else:
                        MessageBox(tr("success"), tr("lyric_embed_success"), self).exec()
                else:
                    MessageBox(tr("errors_occurred"), tr("lyric_embed_failed"), self).exec()
            except Exception as e:
                self.logger.exception(f"Error in _on_embed_lyrics (inner): {e}")
                MessageBox(tr("errors_occurred"), str(e), self).exec()
        except Exception as e:
            self.logger.exception(f"Error in _on_embed_lyrics: {e}")
            MessageBox(tr("errors_occurred"), str(e), self).exec()

    def _on_save_lyrics(self) -> None:
        """
        保存歌词按钮点击处理

        将当前歌词编辑器中的歌词保存为 .lrc 文件。
        用户可以选择保存位置，默认与 MP3 文件同目录。
        """
        if not self.current_file:
            MessageBox(tr("no_file_selected"), tr("select_files"), self).exec()
            return

        lyrics_text = self.lyric_text.toPlainText()
        if not lyrics_text:
            MessageBox(tr("no_lyrics_found"), tr("get_lyrics"), self).exec()
            return

        # 获取默认保存路径（与 MP3 文件同目录）
        default_dir = os.path.dirname(self.current_file)
        default_name = os.path.splitext(os.path.basename(self.current_file))[0] + '.lrc'
        default_path = os.path.join(default_dir, default_name)

        # 弹出文件保存对话框
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            tr("save_lyrics_to_file"),
            default_path,
            tr("lrc_file_filter")
        )

        if not file_path:
            return  # 用户取消

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(lyrics_text)

            MessageBox(
                tr("success"),
                tr("lyric_saved") + f"\n{file_path}",
                self
            ).exec()
        except Exception as e:
            MessageBox(tr("errors_occurred"), str(e), self).exec()

    def refresh_texts(self) -> None:
        """
        刷新页面文本

        当语言切换时调用此方法，更新所有 UI 文本为当前语言的翻译。
        """
        # 更新文件列表区域
        self.file_list_title.setText(tr("music_manager.file_list"))
        self.browse_btn.setText(tr("converter.browse"))
        self.search_edit.setPlaceholderText(tr("music_manager.search_placeholder"))
        self.check_all_btn.setText(tr("converter.check_all"))
        self.uncheck_all_btn.setText(tr("converter.uncheck_all"))
        self.clear_data_btn.setText(tr("search.clear_data"))

        self.file_table.setHorizontalHeaderLabels([
            tr("music_manager.check"), tr("music_manager.file_name"), tr("music_manager.format"), tr("music_manager.size")
        ])

        self.segmented_widget.setItemText(
            routeKey="metadata",
            text=tr("lyrics.metadata_tab")
        )
        self.segmented_widget.setItemText(
            routeKey="lyrics",
            text=tr("lyrics.lyrics_tab")
        )

        self.title_label.setText(tr("music_manager.fields.title"))
        self.artist_label.setText(tr("music_manager.fields.artist"))
        self.album_label.setText(tr("music_manager.fields.album"))
        self.year_label.setText(tr("music_manager.fields.year"))
        self.genre_label.setText(tr("music_manager.fields.genre"))

        self.title_edit.setPlaceholderText(tr("music_manager.fields.title"))
        self.artist_edit.setPlaceholderText(tr("music_manager.fields.artist"))
        self.album_edit.setPlaceholderText(tr("music_manager.fields.album"))
        self.year_edit.setPlaceholderText(tr("music_manager.fields.year"))
        self.genre_edit.setPlaceholderText(tr("music_manager.fields.genre"))

        self.save_metadata_btn.setText(tr("music_manager.save"))

        self.cover_title.setText(tr("music_manager.fields.cover"))
        self.from_file_btn.setText(tr("music_manager.from_file"))
        self.from_url_btn.setText(tr("music_manager.from_url"))

        self.provider_label.setText(tr("lyrics.lyric_provider"))
        self.lyric_title.setText(tr("music_manager.fields.lyrics"))
        self.lyric_text.setPlaceholderText(tr("lyrics.no_lyrics_found"))
        self.get_lyric_btn.setText(tr("lyrics.get_lyrics"))
        self.embed_lyric_btn.setText(tr("lyrics.embed_lyrics"))
        self.save_lyric_btn.setText(tr("lyrics.save_lyrics_to_file"))
        self.batch_get_lyric_btn.setText(tr("lyrics.batch_get_lyrics"))

        self.embed_mode_combo.setItemText(0, tr("lyrics.embed_only"))
        self.embed_mode_combo.setItemText(1, tr("lyrics.embed_and_lrc"))
        self.embed_mode_combo.setToolTip(tr("lyrics.embed_only_desc") + " / " + tr("lyrics.embed_and_lrc_desc"))

        # 更新提供商下拉框
        from auto_tag.lyric import list_providers
        self._provider_list = list_providers()
        for idx, provider_name in enumerate(self._provider_list):
            if idx < self.provider_combo.count():
                self.provider_combo.setItemText(idx, tr(f'lyrics.providers.{provider_name}'))
