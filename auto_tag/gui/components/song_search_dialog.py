# -*- coding: utf-8 -*-
"""
搜索结果选择对话框模块（UI 优化版）

该模块提供音乐搜索结果的选择功能，采用 Fluent Design 设计语言，
支持展示歌曲列表、预览详细信息、选择目标歌曲等操作。
包含动画效果、响应式布局和优化的视觉层次。

@module song_search_dialog
@version 2.0.0
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import (
    Qt,
    Signal,
    QPropertyAnimation,
    QEasingCurve,
    QRect,
    QThread,
)
from PySide6.QtWidgets import (
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QHeaderView,
    QLabel,
    QAbstractItemView,
    QGraphicsDropShadowEffect,
    QApplication,
)
from PySide6.QtGui import QColor, QFont, QCursor

from qfluentwidgets import (
    MessageBoxBase,
    SubtitleLabel,
    BodyLabel,
    PrimaryPushButton,
    PushButton,
    FluentIcon as FIF,
    SingleDirectionScrollArea,
    isDarkTheme,
    IconWidget,
)

from auto_tag.gui.i18n import tr


class LyricCheckWorker(QThread):
    """
    异步检查歌词是否存在的后台线程

    逐行检查每首歌是否有歌词，并通过信号通知 UI 更新。
    """

    lyric_status_updated = Signal(int, bool)  # 行号, 是否有歌词

    def __init__(self, songs: list[dict[str, Any]], provider: str = 'netease', parent=None) -> None:
        """
        初始化歌词检查线程

        Args:
            songs: 搜索结果歌曲列表
            provider: 歌词提供商
            parent: 父对象
        """
        super().__init__(parent)
        self._songs = songs
        self._provider = provider
        self._cancelled = False

    def run(self) -> None:
        """执行歌词检查任务"""
        from auto_tag.lyric.manager import LyricManager

        manager = LyricManager()

        for row, song in enumerate(self._songs):
            if self._cancelled:
                break

            song_id = song.get('id')
            if song_id:
                has_lyric = manager.check_lyric_exists(song_id, self._provider)
                self.lyric_status_updated.emit(row, has_lyric)

    def cancel(self) -> None:
        """取消检查"""
        self._cancelled = True


class SongSearchResultDialog(MessageBoxBase):
    """
    搜索结果选择对话框（Fluent Design 风格）

    展示音乐平台搜索结果，允许用户选择目标歌曲。
    采用现代化的视觉设计，包含动画效果和优化的交互体验。

    Features:
        - Fluent Design 视觉风格
        - 平滑的入场/悬停动画
        - 响应式布局适配不同屏幕
        - 优化的表格展示效果
        - 键盘快捷键支持（Enter/Escape）

    Attributes:
        song_selected (Signal): 歌曲选择信号，参数为 (song_id, song_info)

    Example:
        >>> dialog = SongSearchResultDialog(parent)
        >>> dialog.set_search_results(songs, keyword="周杰伦 晴天")
        >>> if dialog.exec():
        ...     song_id, info = dialog.selected_song
    """

    song_selected = Signal(dict)  # 选中的歌曲信息

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        初始化搜索结果对话框

        Args:
            parent (QWidget | None): 父窗口组件
        """
        super().__init__(parent)

        # 状态变量
        self._songs: list[dict[str, Any]] = []
        self._selected_song: Optional[dict[str, Any]] = None
        self._keyword: str = ""
        self._provider: str = "netease"
        self._animation_group = None
        self._lyric_check_worker: Optional[LyricCheckWorker] = None

        # 创建 UI 组件
        self._create_components()

        # 构建布局
        self._setup_layout()

        # 应用样式
        self._apply_styles()

        # 连接信号
        self._connect_signals()

        # 设置对话框尺寸（基于屏幕动态计算）
        self._setup_responsive_size()

        # 隐藏 MessageBoxBase 自带的默认按钮组（OK/Cancel）
        # 因为我们使用自定义的按钮区域
        self.hideYesButton()
        self.hideCancelButton()

    def _create_components(self) -> None:
        """
        创建所有 UI 组件

        初始化标题、标签、表格和按钮等组件实例。
        """
        # 标题区域组件
        self.titleLabel = SubtitleLabel(tr("search.results_title"))
        self.titleLabel.setObjectName("dialogTitle")

        # 结果计数标签（右侧显示）
        self.resultCountLabel = BodyLabel()
        self.resultCountLabel.setObjectName("resultCount")

        # 搜索关键词图标 + 标签
        self._keyword_icon = IconWidget(FIF.SEARCH)
        self._keyword_icon.setFixedSize(16, 16)
        self.keywordLabel = BodyLabel()
        self.keywordLabel.setObjectName("keywordLabel")

        # 创建搜索结果表格
        self.song_table = self._create_table()

        # 创建按钮区域
        self.confirm_button = PrimaryPushButton(
            FIF.ACCEPT, tr("search.select_song"), self
        )
        self.confirm_button.setObjectName("confirmButton")
        self.confirm_button.setFixedHeight(36)
        self.confirm_button.setMinimumWidth(120)

        self.cancel_button = PushButton(FIF.CANCEL, tr("search.cancel"), self)
        self.cancel_button.setObjectName("cancelButton")
        self.cancel_button.setFixedHeight(36)
        self.cancel_button.setMinimumWidth(100)

    def _create_table(self) -> QTableWidget:
        """
        创建搜索结果表格（优化版）

        Returns:
            QTableWidget: 配置完成的表格组件，具有现代化的视觉效果
        """
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels([
            tr("search.song_name"),
            tr("search.song_detail.artist"),
            tr("search.song_detail.album"),
            tr("search.duration"),
            tr("lyrics"),
            tr("search.song_detail.id")
        ])

        # 设置表格属性
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)  # 隐藏网格线，更现代

        # 启用鼠标追踪以支持悬停效果
        table.setMouseTracking(True)

        # 设置列宽模式（优化比例：歌名40% | 艺术25% | 专辑25% | 时长10% | 歌词5%）
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(3, 70)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(4, 60)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(5, 80)

        # 设置表头样式
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setHighlightSections(False)
        header.setStretchLastSection(True)

        # 隐藏 ID 列（用于内部使用）
        table.setColumnHidden(5, True)

        # 设置行高（舒适的阅读高度）
        table.verticalHeader().setDefaultSectionSize(40)

        # 设置焦点策略
        table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        return table

    def _setup_layout(self) -> None:
        """
        构建对话框布局（Fluent Design 层次结构）

        使用 MessageBoxBase 提供的 viewLayout 来添加自定义内容，
        遵循清晰的视觉层次：标题 → 关键词 → 内容 → 操作按钮。
        """
        layout = self.viewLayout
        layout.setSpacing(16)  # 统一间距系统
        layout.setContentsMargins(0, 8, 0, 8)

        # === 标题区域（第一层）===
        title_container = QWidget()
        title_container.setObjectName("titleContainer")
        title_layout = QHBoxLayout(title_container)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(12)

        # 左侧：图标 + 标题
        icon_label = QLabel()
        icon_label.setObjectName("titleIcon")
        icon_label.setFixedSize(24, 24)
        title_layout.addWidget(icon_label)
        title_layout.addWidget(self.titleLabel)

        title_layout.addStretch()

        # 右侧：结果计数
        title_layout.addWidget(self.resultCountLabel)
        layout.addWidget(title_container)

        # === 搜索关键词区域（第二层：Fluent 图标 + 标签）===
        keyword_row = QHBoxLayout()
        keyword_row.setSpacing(6)
        keyword_row.addWidget(self._keyword_icon)
        keyword_row.addWidget(self.keywordLabel)
        layout.addLayout(keyword_row)

        # === 表格内容区域（第三层 - 主要内容）===
        scroll_area = SingleDirectionScrollArea()
        scroll_area.setObjectName("tableScrollArea")
        scroll_area.setWidget(self.song_table)
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setMinimumHeight(220)  # 确保能显示至少 5 行
        layout.addWidget(scroll_area, stretch=1)

        # === 按钮操作区域（第四层）===
        button_container = QWidget()
        button_container.setObjectName("buttonContainer")
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 12, 0, 0)
        button_layout.setSpacing(12)

        button_layout.addStretch()
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.confirm_button)
        button_layout.addStretch()

        layout.addWidget(button_container)

    def _apply_styles(self) -> None:
        """
        应用 Fluent Design 样式表

        为所有组件设置符合设计规范的视觉效果，
        包括色彩、字体、间距、圆角和阴影等。
        """
        # 检测当前主题（亮色/暗色）
        is_dark = isDarkTheme()

        if is_dark:
            self._apply_dark_theme_styles()
        else:
            self._apply_light_theme_styles()

    def _apply_light_theme_styles(self) -> None:
        """
        应用于亮色主题的特定样式
        """
        self.keywordLabel.setStyleSheet("""
            BodyLabel#keywordLabel {
                color: #00897B;
                font-size: 13px;
                font-weight: 500;
                padding: 6px 12px;
                background-color: rgba(0, 191, 165, 0.08);
                border-radius: 16px;
                border-left: 3px solid #00bfa5;
            }
        """)

        self.resultCountLabel.setStyleSheet("""
            BodyLabel#resultCount {
                color: rgba(0, 0, 0, 0.45);
                font-size: 14px;
                font-weight: 600;
                background-color: rgba(0, 191, 165, 0.1);
                padding: 4px 12px;
                border-radius: 12px;
            }
        """)

        self.titleLabel.setStyleSheet("""
            SubtitleLabel#dialogTitle {
                font-size: 18px;
                font-weight: 700;
                color: rgba(0, 0, 0, 0.9);
                letter-spacing: -0.2px;
            }
        """)

        # 亮色主题表格样式
        self.song_table.setStyleSheet("""
            QTableWidget {
                border: none;
                border-radius: 8px;
                background-color: transparent;
                alternate-background-color: rgba(0, 0, 0, 0.02);
                selection-background-color: transparent;
                selection-color: rgba(0, 0, 0, 0.87);
                outline: none;
            }

            QTableWidget::item {
                padding: 10px 12px;
                border-bottom: 1px solid rgba(0, 0, 0, 0.05);
                border-radius: 4px;
                margin: 1px 8px;
            }

            QTableWidget::item:hover {
                background-color: rgba(0, 191, 165, 0.08);
                border-left: 3px solid #00bfa5;
                border-radius: 0 4px 4px 0;
            }

            QTableWidget::item:selected {
                background-color: rgba(0, 191, 165, 0.15);
                border-left: 3px solid #00bfa5;
                border-radius: 0 4px 4px 0;
                color: rgba(0, 0, 0, 0.95);
                padding-left: 8px;
            }

            QTableWidget::item:selected:hover {
                background-color: rgba(0, 191, 165, 0.22);
            }

            QHeaderView::section {
                background-color: transparent;
                color: rgba(0, 0, 0, 0.55);
                font-size: 13px;
                font-weight: 500;
                padding: 10px 12px;
                border: none;
                border-bottom: 2px solid rgba(0, 0, 0, 0.08);
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }

            QScrollBar:vertical {
                width: 8px;
                background: transparent;
                border-radius: 4px;
                margin: 0;
            }

            QScrollBar::handle:vertical {
                background-color: rgba(0, 0, 0, 0.15);
                border-radius: 4px;
                min-height: 30px;
            }

            QScrollBar::handle:vertical:hover {
                background-color: rgba(0, 0, 0, 0.25);
            }

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)

        # 亮色滚动区域样式
        self.findChild(SingleDirectionScrollArea).setStyleSheet("""
            SingleDirectionScrollArea {
                border: 1px solid rgba(0, 0, 0, 0.08);
                border-radius: 10px;
                background-color: rgba(255, 255, 255, 0.7);
                padding: 4px;
            }
        """)

    def _apply_dark_theme_styles(self) -> None:
        """
        应用于暗色主题的特定样式
        """
        self.keywordLabel.setStyleSheet("""
            BodyLabel#keywordLabel {
                color: #4DB6AC;
                font-size: 13px;
                font-weight: 500;
                padding: 6px 12px;
                background-color: rgba(77, 182, 172, 0.12);
                border-radius: 16px;
                border-left: 3px solid #4DB6AC;
            }
        """)

        self.resultCountLabel.setStyleSheet("""
            BodyLabel#resultCount {
                color: rgba(255, 255, 255, 0.55);
                font-size: 14px;
                font-weight: 600;
                background-color: rgba(77, 182, 172, 0.15);
                padding: 4px 12px;
                border-radius: 12px;
            }
        """)

        self.titleLabel.setStyleSheet("""
            SubtitleLabel#dialogTitle {
                font-size: 18px;
                font-weight: 700;
                color: rgba(255, 255, 255, 0.92);
                letter-spacing: -0.2px;
            }
        """)

        # 暗色主题下的表格特殊处理（与亮色主题保持一致的视觉效果）
        dark_table_style = """
            QTableWidget {
                border: none;
                border-radius: 8px;
                background-color: rgba(30, 30, 30, 0.95);
                alternate-background-color: rgba(255, 255, 255, 0.03);
                selection-background-color: transparent;
                selection-color: rgba(255, 255, 255, 0.95);
                outline: none;
            }

            QTableWidget::item {
                padding: 10px 12px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 4px;
                margin: 1px 8px;
                color: rgba(255, 255, 255, 0.87);
            }

            QTableWidget::item:hover {
                background-color: rgba(77, 182, 172, 0.12);
                border-left: 3px solid #4DB6AC;
                border-radius: 0 4px 4px 0;
            }

            QTableWidget::item:selected {
                background-color: rgba(77, 182, 172, 0.22);
                border-left: 3px solid #4DB6AC;
                border-radius: 0 4px 4px 0;
                color: rgba(255, 255, 255, 0.95);
                padding-left: 8px;
            }

            QTableWidget::item:selected:hover {
                background-color: rgba(77, 182, 172, 0.30);
            }

            QHeaderView::section {
                background-color: rgba(45, 45, 45, 0.98);
                color: rgba(255, 255, 255, 0.65);
                font-size: 13px;
                font-weight: 500;
                padding: 10px 12px;
                border: none;
                border-bottom: 2px solid rgba(255, 255, 255, 0.08);
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }

            QScrollBar:vertical {
                width: 8px;
                background: rgba(30, 30, 30, 0.5);
                border-radius: 4px;
                margin: 0;
            }

            QScrollBar::handle:vertical {
                background-color: rgba(255, 255, 255, 0.15);
                border-radius: 4px;
                min-height: 30px;
            }

            QScrollBar::handle:vertical:hover {
                background-color: rgba(255, 255, 255, 0.25);
            }

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
            }
        """
        self.song_table.setStyleSheet(dark_table_style)

        # 暗色滚动区域
        self.findChild(SingleDirectionScrollArea).setStyleSheet("""
            SingleDirectionScrollArea {
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 10px;
                background-color: rgba(30, 30, 30, 0.98);
                padding: 4px;
            }
        """)

    def _setup_responsive_size(self) -> None:
        """
        设置响应式尺寸（基于屏幕动态计算）

        根据屏幕尺寸和 DPI 缩放因子动态调整对话框大小，
        确保在不同设备上都有良好的显示效果。
        """
        screen = QApplication.primaryScreen()
        if not screen:
            return

        screen_geometry = screen.availableGeometry()
        screen_width = screen_geometry.width()
        screen_height = screen_geometry.height()

        # 计算合适的对话框尺寸（最大不超过屏幕的 70%，最小不低于阈值）
        max_width = int(screen_width * 0.65)
        max_height = int(screen_height * 0.7)

        min_width = min(450, int(screen_width * 0.4))
        min_height = min(380, int(screen_height * 0.5))

        # 固定初始尺寸为适中值
        initial_width = min(max_width, max(min_width + 50, 520))
        initial_height = min(max_height, max(min_height + 20, 430))

        # 应用尺寸约束
        self.widget.setMinimumSize(min_width, min_height)
        self.widget.setMaximumSize(max_width, max_height)
        self.widget.setFixedSize(initial_width, initial_height)

    def _connect_signals(self) -> None:
        """
        连接信号和槽函数

        绑定用户交互事件到对应的处理方法，
        包括按钮点击、双击行、键盘快捷键等。
        """
        self.confirm_button.clicked.connect(self._on_confirm)
        self.cancel_button.clicked.connect(self.reject)
        self.song_table.cellDoubleClicked.connect(self._on_double_click)
        self.song_table.currentCellChanged.connect(self._on_selection_changed)

        # 键盘快捷键支持
        self.song_table.keyPressEvent = self._on_table_key_press

    def showEvent(self, event) -> None:
        """
        显示事件处理

        当对话框显示时触发入场动画效果。

        Args:
            event (QShowEvent): 显示事件对象
        """
        super().showEvent(event)
        self._play_enter_animation()

    def _play_enter_animation(self) -> None:
        """
        播放入场动画

        实现淡入+轻微上移的组合动画效果，
        创造流畅自然的视觉过渡体验。
        """
        try:
            from PySide6.QtCore import QParallelAnimationGroup, QEasingCurve

            animation_group = QParallelAnimationGroup(self)

            # 不透明度动画（从 0 到 1）
            opacity_animation = QPropertyAnimation(
                self, b"windowOpacity"
            )
            opacity_animation.setDuration(250)
            opacity_animation.setStartValue(0.0)
            opacity_animation.setEndValue(1.0)
            opacity_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            animation_group.addAnimation(opacity_animation)

            # 启动动画组
            self._animation_group = animation_group
            animation_group.start(
                QPropertyAnimation.DeletionPolicy.DeleteWhenStopped
            )

        except Exception:
            pass  # 动画失败不影响功能

    def set_search_results(
        self,
        songs: list[dict[str, Any]],
        keyword: str = "",
        provider: str = "netease"
    ) -> None:
        """
        设置搜索结果数据

        Args:
            songs (list[dict]): 搜索结果列表，每个字典包含：
                - id: 歌曲 ID
                - name: 歌曲名称
                - artist: 艺术家名称
                - album: 专辑名称
                - duration: 时长（秒）
            keyword (str): 搜索关键词
            provider (str): 歌词提供商
        """
        self._songs = songs
        self._keyword = keyword
        self._provider = provider

        # 更新标签文本（Fluent 图标 + 关键词）
        if keyword:
            self._keyword_icon.show()
            self.keywordLabel.show()
            self.keywordLabel.setText(
                f"{tr('search.keyword')}: {keyword}"
            )
        else:
            self._keyword_icon.hide()
            self.keywordLabel.hide()

        count_text = f"{len(songs)} {tr('search.results_found')}"
        self.resultCountLabel.setText(count_text)

        # 填充表格数据
        self.song_table.setRowCount(len(songs))

        for row, song in enumerate(songs):
            # 歌曲名（加粗显示，主要信息）
            name_item = QTableWidgetItem(song.get('name', ''))
            name_item.setData(Qt.ItemDataRole.UserRole, song)
            font = name_item.font()
            font.setWeight(QFont.Weight.Medium)
            name_item.setFont(font)
            self.song_table.setItem(row, 0, name_item)

            # 艺术家
            artist_item = QTableWidgetItem(song.get('artist', ''))
            artist_item.setForeground(QColor(128, 128, 128))  # 灰色次要信息
            self.song_table.setItem(row, 1, artist_item)

            # 专辑
            album_item = QTableWidgetItem(song.get('album', ''))
            album_item.setForeground(QColor(128, 128, 128))  # 灰色次要信息
            self.song_table.setItem(row, 2, album_item)

            # 时长（右对齐，使用等宽风格）
            duration = song.get('duration', 0)
            duration_str = self._format_duration(duration)
            duration_item = QTableWidgetItem(duration_str)
            duration_item.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter |
                Qt.AlignmentFlag.AlignVCenter
            )
            duration_font = duration_item.font()
            duration_font.setFamily("Consolas")  # 等宽字体
            duration_font.setPointSize(11)
            duration_item.setFont(duration_font)
            duration_item.setForeground(QColor(100, 100, 100))
            self.song_table.setItem(row, 3, duration_item)

            # 歌词状态（初始为加载中，Fluent SYNC 图标）
            lyric_item = QTableWidgetItem()
            lyric_item.setIcon(FIF.SYNC.icon())
            lyric_item.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter |
                Qt.AlignmentFlag.AlignVCenter
            )
            lyric_item.setForeground(QColor(150, 150, 150))
            self.song_table.setItem(row, 4, lyric_item)

            # ID（隐藏，内部使用）
            id_item = QTableWidgetItem(str(song.get('id', '')))
            self.song_table.setItem(row, 5, id_item)

        # 默认选中第一行（CSS 样式会自动处理选中效果）
        if len(songs) > 0:
            self.song_table.selectRow(0)
            self._selected_song = songs[0]

        # 启动异步歌词检查
        self._start_lyric_check()

    def _start_lyric_check(self) -> None:
        """
        启动异步歌词检查线程

        在后台逐行检查每首歌是否有歌词，并通过信号更新表格。
        """
        if not self._songs:
            return

        # 清理旧的 worker
        if self._lyric_check_worker is not None:
            self._lyric_check_worker.terminate()
            self._lyric_check_worker.wait()

        self._lyric_check_worker = LyricCheckWorker(
            songs=self._songs,
            provider=self._provider,
            parent=self,
        )
        self._lyric_check_worker.lyric_status_updated.connect(self._on_lyric_status_updated)
        self._lyric_check_worker.start()

    def _on_lyric_status_updated(self, row: int, has_lyric: bool) -> None:
        """
        歌词检查结果回调

        根据结果更新表格中的歌词列图标。

        Args:
            row: 表格行号
            has_lyric: 是否有歌词
        """
        lyric_item = self.song_table.item(row, 4)
        if lyric_item:
            if has_lyric:
                lyric_item.setIcon(FIF.ACCEPT.icon())
                lyric_item.setToolTip("有歌词")
            else:
                lyric_item.setIcon(FIF.CANCEL.icon())
                lyric_item.setToolTip("无歌词")

    def _on_selection_changed(
        self,
        current_row: int,
        current_col: int,
        previous_row: int,
        previous_col: int
    ) -> None:
        """
        选择变更回调

        当用户在表格中选择不同行时更新选中状态。

        Args:
            current_row (int): 当前行索引
            current_col (int): 当前列索引
            previous_row (int): 前一行索引
            previous_col (int): 前一列索引
        """
        if 0 <= current_row < len(self._songs):
            self._selected_song = self._songs[current_row]

    def _on_table_key_press(self, event) -> None:
        """
        表格键盘按键事件处理

        支持键盘快捷键：
        - Enter/Return：确认选择
        - Escape：关闭对话框

        Args:
            event (QKeyEvent): 键盘事件对象
        """
        from PySide6.QtGui import QKeyEvent

        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            self._on_confirm()
        elif event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            # 默认处理其他按键（方向键导航等）
            QTableWidget.keyPressEvent(self.song_table, event)

    def _format_duration(self, seconds: int) -> str:
        """
        格式化时长显示

        Args:
            seconds (int): 时长（秒）

        Returns:
            str: 格式化的时长字符串 (mm:ss)
        """
        if not seconds or seconds <= 0:
            return "--:--"
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes:02d}:{secs:02d}"

    def _on_confirm(self) -> None:
        """
        确认按钮点击处理

        获取当前选中的歌曲并触发确认动画后关闭对话框。
        """
        current_row = self.song_table.currentRow()
        if current_row < 0 or current_row >= len(self._songs):
            return

        self._selected_song = self._songs[current_row]

        # 播放点击反馈动画
        self._play_click_feedback()
        self.accept()

    def _play_click_feedback(self) -> None:
        """
        播放按钮点击反馈动画

        实现轻微的缩放效果提供触觉反馈感。
        """
        try:
            from PySide6.QtCore import QPropertyAnimation, QEasingCurve

            scale_animation = QPropertyAnimation(
                self.confirm_button, b"geometry"
            )
            geometry = self.confirm_button.geometry()
            scale_animation.setDuration(100)
            scale_animation.setStartValue(geometry)
            scale_animation.setEndValue(geometry.adjusted(2, 2, -2, -2))
            scale_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
            scale_animation.start(
                QPropertyAnimation.DeletionPolicy.DeleteWhenStopped
            )

        except Exception:
            pass  # 动画失败不影响功能

    def _on_double_click(self, row: int, column: int) -> None:
        """
        双击单元格事件处理

        双击任意位置选中该行并确认选择。

        Args:
            row (int): 行索引
            column (int): 列索引
        """
        if 0 <= row < len(self._songs):
            self._selected_song = self._songs[row]
            self.accept()

    @property
    def selected_song(self) -> Optional[dict[str, Any]]:
        """
        获取选中的歌曲信息

        Returns:
            dict | None: 选中的歌曲字典，未选择返回 None
        """
        return self._selected_song

    @property
    def selected_song_id(self) -> Optional[int]:
        """
        获取选中歌曲的 ID

        Returns:
            int | None: 歌曲 ID，未选择返回 None
        """
        if self._selected_song:
            return self._selected_song.get('id')
        return None
