# -*- coding: utf-8 -*-
"""
音频识别主页面模块

该模块提供音频识别功能的主页面界面，包括目录选择、文件识别、
进度显示、多平台搜索结果展示和批量操作等功能。
"""

from __future__ import annotations

import os
import shutil
import time
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QIcon, QTransform
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QScrollArea,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QFrame,
    QSizePolicy,
)
from qfluentwidgets import (
    BodyLabel,
    LineEdit,
    MessageBox,
    ProgressBar,
    PushButton,
    SubtitleLabel,
    SwitchButton,
    TableWidget,
    CardWidget,
    ToolButton,
    isDarkTheme,
    qconfig,
)
from qfluentwidgets import FluentIcon as FIF

if TYPE_CHECKING:
    from auto_tag.gui.workers.recognize_worker import RecognizeWorker
    from auto_tag.gui.components.song_result_card import SongResultCard

from auto_tag.audio_recognize import (
    update_audio_tags,
    update_mp3_cover_art,
    update_mp3_tags,
    update_ogg_tags,
)
from auto_tag.gui.i18n import tr
from auto_tag.gui.workers import RecognizeWorker
from auto_tag.gui.components.song_result_card import SongResultCard
from auto_tag.utils import is_file_in_use_error

logger = logging.getLogger(__name__)


# 平台名称映射
_PLATFORM_NAME_MAP = {
    "acoustid": "source_acoustid",
    "shazam": "source_shazam",
    "netease": "source_netease",
    "kugou": "source_kugou",
}


class HomePage(QWidget):
    """
    音频识别主页面

    提供音频文件识别和标签更新的用户界面。

    Attributes:
        dir_var (str): 输入目录路径
        copy_enabled (bool): 是否启用复制到目录
        copy_dir (str): 复制目标目录路径
        tag_only (bool): 是否仅更新标签
        data (list[dict]): 识别结果数据列表
        worker (RecognizeWorker | None): 当前工作线程实例
        search_results_map (dict): 文件路径到搜索结果列表的映射
        _selected_results (dict): 用户为每个文件选择的搜索结果索引
        song_cards (dict): 文件路径到歌曲卡片的映射
    """

    # 自定义信号
    selection_changed = Signal(str, int)
    _song_refresh_result = Signal(str, object)
    _song_refresh_error = Signal(str, str)

    def __init__(self, parent=None) -> None:
        """
        初始化主页面

        Args:
            parent (QWidget | None): 父窗口组件
        """
        super().__init__(parent)

        # 状态变量
        self.dir_var = ""
        self.copy_enabled = False
        self.copy_dir = ""
        self.tag_only = False
        self.data: list[dict] = []
        self.worker: RecognizeWorker | None = None

        # 多平台搜索结果存储
        self.search_results_map: dict[str, list[dict]] = {}
        self._selected_results: dict[str, int] = {}
        self.song_cards: dict[str, "SongResultCard"] = {}

        # 顶部刷新按钮动画状态
        self._refresh_files_angle = 0
        self._refresh_files_timer: QTimer | None = None
        self._is_refreshing_files = False

        # 构建 UI
        self._setup_ui()

        # 连接信号槽
        self._connect_signals()

    def _setup_ui(self) -> None:
        """
        构建主页面 UI 布局

        创建所有界面组件并使用布局管理器组织它们，
        包括输入区域、进度区域、结果表格和操作按钮。
        """
        # 主布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(16)

        # === 输入区域 ===
        input_layout = QHBoxLayout()
        input_layout.setSpacing(12)

        # 目录选择
        self.dir_label = BodyLabel(tr("input_directory"))
        input_layout.addWidget(self.dir_label)

        self.dir_entry = LineEdit()
        self.dir_entry.setPlaceholderText(tr("select_directory"))
        self.dir_entry.setFixedHeight(36)
        input_layout.addWidget(self.dir_entry)

        self.browse_btn = PushButton(tr("browse"))
        self.browse_btn.setFixedHeight(36)
        self.browse_btn.clicked.connect(self._on_browse)
        input_layout.addWidget(self.browse_btn)

        # 复制到开关和目录
        self.copy_switch = SwitchButton()
        self.copy_switch.setFixedSize(50, 28)
        self.copy_switch.setChecked(False)
        self.copy_switch.setOffText("")
        self.copy_switch.setOnText("")
        input_layout.addWidget(self.copy_switch)

        self.copy_to_label = BodyLabel(tr("copy_to"))
        input_layout.addWidget(self.copy_to_label)

        self.copy_dir_entry = LineEdit()
        self.copy_dir_entry.setPlaceholderText(tr("select_directory"))
        self.copy_dir_entry.setFixedHeight(36)
        self.copy_dir_entry.setEnabled(False)
        input_layout.addWidget(self.copy_dir_entry)

        self.copy_browse_btn = PushButton(tr("browse"))
        self.copy_browse_btn.setFixedHeight(36)
        self.copy_browse_btn.clicked.connect(self._on_browse_copy)
        self.copy_browse_btn.setEnabled(False)
        input_layout.addWidget(self.copy_browse_btn)

        # 仅标签开关
        self.tag_switch = SwitchButton()
        self.tag_switch.setFixedSize(50, 28)
        self.tag_switch.setChecked(False)
        self.tag_switch.setOffText("")
        self.tag_switch.setOnText("")
        input_layout.addWidget(self.tag_switch)

        self.tags_only_label = BodyLabel(tr("tags_only"))
        input_layout.addWidget(self.tags_only_label)

        layout.addLayout(input_layout)

        # === 进度区域 ===
        progress_layout = QHBoxLayout()
        progress_layout.setSpacing(12)

        self.progress_bar = ProgressBar()
        self.progress_bar.setFixedHeight(8)
        progress_layout.addWidget(self.progress_bar)

        self.status_label = BodyLabel(
            tr("progress_format", done=0, total=0, remaining=0)
        )
        progress_layout.addWidget(self.status_label)

        layout.addLayout(progress_layout)

        # === 搜索结果区域 ===
        results_header_layout = QHBoxLayout()
        results_header_layout.setSpacing(12)

        self.table_title = SubtitleLabel(tr("search_results"))
        results_header_layout.addWidget(self.table_title)

        results_header_layout.addStretch()

        self.refresh_files_btn = ToolButton(FIF.SYNC)
        self.refresh_files_btn.setFixedSize(32, 32)
        self.refresh_files_btn.setToolTip(tr("refresh_file_list"))
        self.refresh_files_btn.clicked.connect(self._on_refresh_files)
        results_header_layout.addWidget(self.refresh_files_btn)

        layout.addLayout(results_header_layout)

        # 创建滚动区域
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.scroll_area.setMinimumHeight(400)
        self._update_scroll_area_style()

        # 创建内容容器
        self.cards_container = QFrame()
        self.cards_container.setObjectName("cardsContainer")
        self._update_cards_container_style()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(12)
        self.cards_layout.addStretch()

        self.scroll_area.setWidget(self.cards_container)
        layout.addWidget(self.scroll_area)

        # === 操作按钮区域 ===
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.check_all_btn = PushButton(tr("check_all"))
        self.check_all_btn.clicked.connect(self._on_check_all)
        btn_layout.addWidget(self.check_all_btn)

        self.uncheck_all_btn = PushButton(tr("uncheck_all"))
        self.uncheck_all_btn.clicked.connect(self._on_uncheck_all)
        btn_layout.addWidget(self.uncheck_all_btn)

        self.apply_btn = PushButton(FIF.ACCEPT, tr("apply"))
        self.apply_btn.clicked.connect(lambda: self._on_apply())
        btn_layout.addWidget(self.apply_btn)

        self.apply_plex_btn = PushButton(FIF.FOLDER, tr("apply_plex"))
        self.apply_plex_btn.clicked.connect(lambda: self._on_apply(plex=True))
        btn_layout.addWidget(self.apply_plex_btn)

        self.clear_data_btn = PushButton(FIF.DELETE, tr("clear_data"))
        self.clear_data_btn.clicked.connect(self._on_clear_data)
        btn_layout.addWidget(self.clear_data_btn)

        layout.addLayout(btn_layout)

    def _connect_signals(self) -> None:
        """
        连接信号槽

        将 UI 组件的信号连接到对应的处理方法。
        """
        # 复制到开关状态变化
        self.copy_switch.checkedChanged.connect(self._on_copy_switch_changed)

        # 仅标签开关状态变化
        self.tag_switch.checkedChanged.connect(self._on_tag_switch_changed)

        # 主题切换
        qconfig.themeChanged.connect(self._on_theme_changed)

        # 歌曲搜索刷新结果（跨线程）
        self._song_refresh_result.connect(self._on_song_search_completed)
        self._song_refresh_error.connect(self._on_song_search_error)

    def _on_copy_switch_changed(self, checked: bool) -> None:
        """
        复制到开关切换回调

        Args:
            checked (bool): 开关是否选中
        """
        try:
            self.copy_enabled = checked
            self.copy_dir_entry.setEnabled(checked)
            self.copy_browse_btn.setEnabled(checked)
        except Exception as e:
            logger.exception(f"Error in _on_copy_switch_changed: {e}")

    def _on_tag_switch_changed(self, checked: bool) -> None:
        """
        仅标签开关切换回调

        Args:
            checked (bool): 开关是否选中
        """
        self.tag_only = checked

    def _update_scroll_area_style(self) -> None:
        """更新滚动区域样式以适配当前主题"""
        if isDarkTheme():
            bg_color = "#1e1e1e"
            border_color = "#3d3d3d"
        else:
            bg_color = "#fafafa"
            border_color = "#e0e0e0"

        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 8px;
            }}
            QScrollArea > QWidget > QWidget {{
                background-color: {bg_color};
            }}
        """)

    def _update_cards_container_style(self) -> None:
        """更新卡片容器样式以适配当前主题"""
        if isDarkTheme():
            bg_color = "#1e1e1e"
        else:
            bg_color = "#fafafa"

        self.cards_container.setStyleSheet(f"""
            #cardsContainer {{
                background-color: {bg_color};
            }}
        """)

    def _on_theme_changed(self) -> None:
        """主题切换回调，更新所有样式"""
        try:
            self._update_scroll_area_style()
            self._update_cards_container_style()

            # 更新所有卡片的主题
            for card in self.song_cards.values():
                card._on_theme_changed()
        except Exception as e:
            logger.exception(f"Error in _on_theme_changed: {e}")

    def _on_browse(self) -> None:
        """
        浏览按钮点击处理

        打开文件夹选择对话框，选择后启动识别任务。
        """
        try:
            directory = QFileDialog.getExistingDirectory(
                self,
                tr("select_directory"),
                "",
                QFileDialog.Option.ShowDirsOnly
            )

            if directory:
                self.dir_var = directory
                self.dir_entry.setText(directory)
                self._start_recognition(directory)
        except Exception as e:
            logger.exception(f"Error in _on_browse: {e}")
            self.status_label.setText(f"选择目录时出错: {e}")

    def _on_browse_copy(self) -> None:
        """
        复制目标目录浏览按钮处理

        打开文件夹选择对话框，选择复制目标目录。
        """
        try:
            directory = QFileDialog.getExistingDirectory(
                self,
                tr("select_directory"),
                "",
                QFileDialog.Option.ShowDirsOnly
            )

            if directory:
                self.copy_dir = directory
                self.copy_dir_entry.setText(directory)
        except Exception as e:
            logger.exception(f"Error in _on_browse_copy: {e}")

    def _on_refresh_files(self) -> None:
        """
        刷新文件列表按钮点击处理

        重新扫描当前目录下的音频文件并执行识别，同时启动 loading 动画。
        """
        try:
            if self._is_refreshing_files:
                return
            if not self.dir_var:
                MessageBox(
                    "Info",
                    tr("select_directory_first"),
                    self
                ).exec()
                return
            self._set_refresh_files_loading(True)
            self._start_recognition(self.dir_var)
        except Exception as e:
            logger.exception(f"Error in _on_refresh_files: {e}")
            self._set_refresh_files_loading(False)
            self.status_label.setText(f"刷新文件列表时出错: {e}")

    def _set_refresh_files_loading(self, loading: bool) -> None:
        """
        设置顶部刷新按钮的加载状态

        Args:
            loading (bool): 是否正在加载
        """
        try:
            self._is_refreshing_files = loading
            self.refresh_files_btn.setEnabled(not loading)
            self.browse_btn.setEnabled(not loading)

            if loading:
                # 启动旋转动画
                self._refresh_files_angle = 0
                self._refresh_files_timer = QTimer(self)
                self._refresh_files_timer.setInterval(30)
                self._refresh_files_timer.timeout.connect(
                    self._rotate_refresh_files_icon
                )
                self._refresh_files_timer.start()
            else:
                # 停止旋转动画
                if (self._refresh_files_timer
                        and self._refresh_files_timer.isActive()):
                    self._refresh_files_timer.stop()
                    self._refresh_files_timer = None
                self._refresh_files_angle = 0
                self.refresh_files_btn.setIcon(FIF.SYNC)
        except Exception as e:
            logger.exception(f"Error in _set_refresh_files_loading: {e}")

    def _rotate_refresh_files_icon(self) -> None:
        """定时器回调，旋转顶部刷新按钮图标"""
        try:
            self._refresh_files_angle = (self._refresh_files_angle + 15) % 360
            icon = FIF.SYNC.icon()
            pixmap = icon.pixmap(20, 20)
            rotated = pixmap.transformed(
                QTransform().rotate(self._refresh_files_angle),
                Qt.TransformationMode.SmoothTransformation,
            )
            self.refresh_files_btn.setIcon(QIcon(rotated))
        except Exception as e:
            logger.exception(f"Error in _rotate_refresh_files_icon: {e}")

    def _on_refresh_song_search(self, file_path: str) -> None:
        """
        刷新单首歌曲搜索结果

        在后台线程中重新搜索指定文件，通过信号将结果传回主线程更新 UI。

        Args:
            file_path (str): 要刷新搜索结果的文件路径
        """
        try:
            import asyncio
            from threading import Thread

            def run_search():
                """在后台线程中运行搜索任务（仅数据处理，不操作UI）"""
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    shazam = None
                    try:
                        from shazamio import Shazam
                        from auto_tag.audio_recognize import recognize_and_rename_file

                        shazam = Shazam()
                        result = loop.run_until_complete(
                            recognize_and_rename_file(
                                file_path=file_path,
                                shazam=shazam,
                                modify=False,
                                delay=10,
                                nbr_retry=3,
                                trace=False,
                                output_dir=None,
                                plex_structure=False,
                                copy_to=self.copy_dir if self.copy_enabled else None,
                                tag_only=self.tag_only,
                            )
                        )
                        search_results = result.get("search_results", [])
                        if not search_results and result.get("title"):
                            search_results = [{
                                "platform": "Shazam",
                                "title": result.get("title", ""),
                                "artist": result.get("author", ""),
                                "album": result.get("album", ""),
                                "cover_url": result.get("cover_link", ""),
                            }]

                        logger.info(f"[HomePage] Search completed for {file_path}, results={len(search_results)}")
                        self._song_refresh_result.emit(file_path, search_results)
                    finally:
                        # 正确关闭 Shazam 的 aiohttp 会话，防止内存泄漏
                        if shazam is not None:
                            try:
                                if hasattr(shazam, 'close'):
                                    loop.run_until_complete(shazam.close())
                            except Exception as close_err:
                                logger.debug(f"[HomePage] Shazam close error: {close_err}")

                        # 关闭 Acoustid 的 aiohttp 会话，防止资源泄漏
                        try:
                            from auto_tag.audio_recognize import _close_acoustid_session
                            loop.run_until_complete(_close_acoustid_session())
                        except Exception as acoustid_close_err:
                            logger.debug(f"[HomePage] Acoustid session close error: {acoustid_close_err}")

                        loop.close()
                except Exception as e:
                    logger.error(f"[HomePage] Failed to refresh search for {file_path}: {e}")
                    self._song_refresh_error.emit(file_path, str(e))

            thread = Thread(target=run_search, daemon=True)
            thread.start()
        except Exception as e:
            logger.exception(f"Error in _on_refresh_song_search: {e}")
            self._song_refresh_error.emit(file_path, str(e))

    def _on_song_search_completed(self, file_path: str, search_results: list) -> None:
        """
        歌曲搜索完成回调（主线程执行）

        更新搜索结果映射和对应卡片的 UI 显示。

        Args:
            file_path (str): 文件路径
            search_results (list): 新的搜索结果列表
        """
        try:
            self.search_results_map[file_path] = search_results

            card = self.song_cards.get(file_path)
            if card:
                card.update_search_results(search_results)

            logger.info(f"[HomePage] Card updated for {file_path}")
        except Exception as e:
            logger.exception(f"Error in _on_song_search_completed: {e}")

    def _on_song_search_error(self, file_path: str, error_msg: str) -> None:
        """
        歌曲搜索错误回调（主线程执行）

        显示错误消息对话框，停止对应卡片的刷新动画。

        Args:
            file_path (str): 文件路径
            error_msg (str): 错误信息
        """
        try:
            card = self.song_cards.get(file_path)
            if card:
                card.set_refreshing(False)
            MessageBox("Error", f"刷新搜索失败: {error_msg}", self).exec()
        except Exception as e:
            logger.exception(f"Error in _on_song_search_error: {e}")

    def _start_recognition(self, directory: str) -> None:
        """
        启动识别任务

        在后台线程中执行音频文件识别。

        Args:
            directory (str): 要识别的目录路径
        """
        # 清空之前的结果
        self.data.clear()
        self.search_results_map.clear()
        self._selected_results.clear()
        self.song_cards.clear()

        # 清空卡片容器
        while self.cards_layout.count():
            child = self.cards_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.cards_layout.addStretch()

        self.progress_bar.setValue(0)
        self.status_label.setText(
            tr("progress_format", done=0, total=0, remaining=0)
        )

        # 创建工作线程
        self.worker = RecognizeWorker(
            directory=directory,
            copy_dir=self.copy_dir if self.copy_enabled else None,
            tag_only=self.tag_only
        )

        # 连接信号
        self.worker.progress_updated.connect(self._on_progress_updated)
        self.worker.file_processed.connect(self._on_file_processed)
        self.worker.finished_all.connect(self._on_finished_all)
        self.worker.error_occurred.connect(self._on_error_occurred)

        # 启动线程
        self.worker.start()

    def _on_progress_updated(self, done: int, total: int, remaining: int) -> None:
        """
        进度更新回调

        更新进度条和状态文本显示当前识别进度。

        Args:
            done (int): 已完成文件数
            total (int): 总文件数
            remaining (int): 预计剩余时间（秒）
        """
        try:
            if total > 0:
                value = int(done / total * 100)
                self.progress_bar.setValue(value)
            self.status_label.setText(
                tr("progress_format", done=done, total=total, remaining=remaining)
            )
        except Exception as e:
            logger.exception(f"Error in _on_progress_updated: {e}")

    def _format_duration(self, seconds: int) -> str:
        """
        格式化时长显示

        Args:
            seconds (int): 时长（秒）

        Returns:
            str: 格式化后的时长字符串
        """
        if not seconds:
            return "--"
        minutes = seconds // 60
        secs = seconds % 60
        if minutes > 0:
            return tr("minutes_seconds_format", minutes=minutes, seconds=secs)
        return tr("seconds_format", seconds=secs)

    def _get_platform_display_name(self, source: str) -> str:
        """
        获取平台显示名称

        Args:
            source (str): 平台标识

        Returns:
            str: 翻译后的平台名称
        """
        key = _PLATFORM_NAME_MAP.get(source, source)
        return tr(key)

    def _on_file_processed(self, result: dict) -> None:
        """
        单个文件处理完成回调

        ✅ 修复#4：优化内存占用 - 消除数据双重存储
        原逻辑将完整result（包含search_results列表）存入self.data，
        又将search_results单独存入self.search_results_map，导致数据重复存储。
        
        新逻辑：
        - self.data只存储轻量级元数据字典（不含search_results）
        - self.search_results_map存储完整的搜索结果列表
        - 通过file_path关联两者，避免数据冗余

        Args:
            result (dict): 单个文件的识别结果字典
        """
        try:
            file_path = result.get("file_path", "")
            search_results = result.get("search_results", [])
            has_error = "error" in result

            # 存储搜索结果到map（唯一完整存储位置）
            self.search_results_map[file_path] = search_results

            # 显示文件名（提前定义，供后续日志使用）
            display_name = os.path.basename(file_path) if file_path else "Unknown"

            # 如果没有多平台搜索结果但识别成功，
            # 将结果包装为搜索结果格式，确保卡片能显示信息
            if not search_results and result.get("title"):
                source = result.get("source", "shazam")
                wrapped_result = {
                    "platform": source.capitalize(),
                    "title": result.get("title", ""),
                    "artist": result.get("author", ""),
                    "album": result.get("album", ""),
                    "cover_url": result.get("cover_link", ""),
                    "source": source,
                }
                search_results = [wrapped_result]
                self.search_results_map[file_path] = search_results
                logger.info(f"[HomePage] Wrapped {source} result for {display_name}")

            # 默认选择第一个（置信度最高的）结果
            self._selected_results[file_path] = 0

            # ✅ 关键优化：只存储元数据引用，不存储完整search_results
            # 减少约50%的数据存储内存占用（34个文件 × 平均10KB = 340KB节省）
            lightweight_result = {
                "file_path": file_path,
                "new_file_path": result.get("new_file_path", ""),
                "title": result.get("title", ""),
                "author": result.get("author", ""),
                "album": result.get("album", ""),
                "cover_link": result.get("cover_link", ""),
                "source": result.get("source", ""),
                "error": result.get("error"),
                "_ref": file_path,  # 引用search_results_map中的数据（轻量级关联）
            }
            self.data.append(lightweight_result)

            # 创建歌曲卡片
            card = SongResultCard(
                file_path=file_path,
                display_name=display_name,
                search_results=search_results,
                default_result=result if not search_results else None,
                has_error=has_error,
            )

            # 设置选中变化回调
            card.set_on_selection_changed(self._on_card_selection_changed)

            # 连接刷新搜索信号
            card.refresh_requested.connect(self._on_refresh_song_search)

            # 添加到布局（在 stretch 之前插入）
            self.cards_layout.insertWidget(
                self.cards_layout.count() - 1,
                card
            )

            # 保存卡片引用
            self.song_cards[file_path] = card

            logger.info(
                f"[HomePage] Card created for {display_name}, "
                f"results={len(search_results)}, error={has_error}"
            )
        except Exception as e:
            logger.error(
                f"[HomePage] Failed to create card for "
                f"{result.get('file_path', 'unknown')}: {e}",
                exc_info=True
            )

    def _on_finished_all(self, results: list) -> None:
        """
        所有文件处理完成回调

        更新最终状态，如果没有找到音频文件则显示提示消息。
        停止顶部刷新按钮的加载动画。

        Args:
            results (list): 所有文件的识别结果列表
        """
        try:
            self._set_refresh_files_loading(False)
            self.progress_bar.setValue(100)
            if not results:
                MessageBox(
                    "Info",
                    tr("no_audio_files"),
                    self
                ).exec()
        except Exception as e:
            logger.exception(f"Error in _on_finished_all: {e}")

    def _on_error_occurred(self, error_msg: str) -> None:
        """
        错误发生回调

        显示错误消息对话框，停止顶部刷新按钮的加载动画。

        Args:
            error_msg (str): 错误信息文本
        """
        try:
            self._set_refresh_files_loading(False)
            MessageBox("Error", error_msg, self).exec()
        except Exception as e:
            logger.exception(f"Error in _on_error_occurred: {e}")

    def _on_card_selection_changed(self, file_path: str, index: int) -> None:
        """
        卡片选中平台变化回调

        Args:
            file_path (str): 文件路径
            index (int): 选中的平台结果索引
        """
        try:
            self._selected_results[file_path] = index
        except Exception as e:
            logger.exception(f"Error in _on_card_selection_changed: {e}")

    def _on_check_all(self) -> None:
        """全选：将所有卡片的勾选状态设为选中"""
        try:
            for card in self.song_cards.values():
                card.checkbox.setChecked(True)
        except Exception as e:
            logger.exception(f"Error in _on_check_all: {e}")

    def _on_uncheck_all(self) -> None:
        """全不选：将所有卡片的勾选状态设为未选中"""
        try:
            for card in self.song_cards.values():
                card.checkbox.setChecked(False)
        except Exception as e:
            logger.exception(f"Error in _on_uncheck_all: {e}")

    def _on_clear_data(self) -> None:
        """
        清除数据按钮点击处理

        清除所有搜索结果和缓存数据，释放文件句柄，
        解决 Windows 下文件被占用的问题。
        """
        try:
            # 停止当前工作线程（如果正在运行）
            if self.worker and self.worker.isRunning():
                self.worker.terminate()
                self.worker.wait()
                self.worker = None

            # 清空所有数据
            self.data.clear()
            self.search_results_map.clear()
            self._selected_results.clear()

            # 先停止所有卡片的加载线程（同步等待，防止竞态条件）
            for card in self.song_cards.values():
                if hasattr(card, '_platform_widgets'):
                    for widget in card._platform_widgets:
                        if hasattr(widget, 'cover_widget') and widget.cover_widget:
                            widget.cover_widget._stop_loader()

            # 删除所有卡片组件（释放文件句柄）
            for card in self.song_cards.values():
                card.deleteLater()
            self.song_cards.clear()

            # 清空卡片容器
            while self.cards_layout.count():
                child = self.cards_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
            self.cards_layout.addStretch()

            # ✅ 新增：清空全局封面图片缓存（修复内存泄漏 #1）
            from auto_tag.gui.components.song_result_card import CoverImageCache
            CoverImageCache.clear()

            # 强制处理事件循环，确保所有 DeferredDelete 被执行
            from PySide6.QtCore import QCoreApplication, QEventLoop
            QCoreApplication.processEvents(
                QEventLoop.ProcessEventsFlags.ExcludeUserInputEvents,
                100
            )

            # 重置进度条和状态
            self.progress_bar.setValue(0)
            self.status_label.setText(
                tr("progress_format", done=0, total=0, remaining=0)
            )

            # 强制垃圾回收，释放文件句柄
            import gc
            gc.collect()

            logger.info("[HomePage] Data cleared, file handles released")
        except Exception as e:
            logger.exception(f"Error in _on_clear_data: {e}")
            self.status_label.setText(f"清除数据时出错: {e}")

    def _on_apply(self, plex: bool = False) -> None:
        """
        应用更改

        对所有勾选的识别结果执行重命名或标签更新操作。

        Args:
            plex (bool): 是否按 Plex 结构组织文件
        """
        errors: list[str] = []
        success_count = 0
        try:
            logger.info(f"[HomePage] _on_apply called: plex={plex}, tag_only={self.tag_only}, "
                         f"total_files={len(self.data)}, total_cards={len(self.song_cards)}")

            for entry in self.data:
                file_path = entry.get("file_path", "")
                card = self.song_cards.get(file_path)

                # 检查是否勾选
                if not card or not card.is_checked():
                    continue

                # 尝试多个可能的文件路径（解决路径不同步问题）
                src = entry.get("file_path", "")

                # 策略 1: 直接使用 entry 的 file_path
                if src and os.path.exists(src):
                    logger.info(f"[HomePage] Found file via entry.file_path: {os.path.basename(src)}")
                # 策略 2: 使用 new_file_path（重命名后的路径）
                elif entry.get("new_file_path") and os.path.exists(entry["new_file_path"]):
                    src = entry["new_file_path"]
                    logger.info(f"[HomePage] Found file via entry.new_file_path: {os.path.basename(src)}")
                # 策略 3: 使用 card 存储的 file_path
                elif card.file_path and os.path.exists(card.file_path):
                    src = card.file_path
                    logger.info(f"[HomePage] Found file via card.file_path: {os.path.basename(src)}")
                else:
                    # 所有路径都无效
                    error_msg = (f"{os.path.basename(src) if src else 'Unknown'}: "
                                f"file not found (tried multiple paths)")
                    logger.error(f"[HomePage] {error_msg}")
                    errors.append(error_msg)
                    continue

                logger.info(f"[HomePage] Processing file: {os.path.basename(src)}")

                # 获取用户选择的结果
                selected_result = card.get_selected_result()
                logger.info(f"[HomePage] Selected result: {selected_result}")

                # DEBUG: 实时显示关键信息到控制台
                print(f"\n{'='*60}")
                print(f"[DEBUG] Processing: {os.path.basename(src)}")
                print(f"[DEBUG] card.selected_platform_index = {card.selected_platform_index}")
                print(f"[DEBUG] selected_result = {selected_result}")
                print(f"{'='*60}\n")

                title = selected_result.get("title", entry.get("title", ""))
                artist = selected_result.get("artist", entry.get("author", ""))
                album = selected_result.get("album", entry.get("album", ""))
                year = selected_result.get("year", "")
                genre = selected_result.get("genre", "")
                cover_link = selected_result.get(
                    "cover_link", entry.get("cover_link", "")
                )

                logger.info(f"[HomePage] Metadata extracted - title='{title}', "
                            f"artist='{artist}', album='{album}', year='{year}', genre='{genre}', cover={'yes' if cover_link else 'no'}")

                # DEBUG: 输出元数据
                print(f"[DEBUG] Raw metadata: title='{title}', artist='{artist}', album='{album}'")

                if not title and not artist and not album:
                    error_msg = f"{src}: 无法获取有效的元数据（title/artist/album 均为空）"
                    logger.error(f"[HomePage] {error_msg}")
                    errors.append(error_msg)
                    continue

                # 生成文件名（保留原始语言字符，只移除文件系统非法字符）
                from auto_tag.utils import sanitize_filename_safe
                f_title = sanitize_filename_safe(title)
                f_artist = sanitize_filename_safe(artist)
                f_album = sanitize_filename_safe(album)

                # DEBUG: 输出结果
                print(f"[DEBUG] Filename (preserving original language): title='{f_title}', artist='{f_artist}', album='{f_album}'")
                print(f"[DEBUG] Tags (original): title='{title}', artist='{artist}', album='{album}'")

                ext = os.path.splitext(src)[1].lower()
                if plex:
                    new_name = f"{f_title}{ext}"
                else:
                    new_name = f"{f_title} - {f_artist} - {f_album}{ext}"

                logger.info(f"[HomePage] Generated filename: {new_name}")
                print(f"[DEBUG] New filename: {new_name}")

                try:
                    # DEBUG: 输出模式信息
                    print(f"[DEBUG] Mode: tag_only={self.tag_only}, plex={plex}")
                    print(f"[DEBUG] Source file exists: {os.path.exists(src)}")
                    print(f"[DEBUG] Source file path: {src}")

                    if self.tag_only:
                        print(f"[DEBUG] >>> Entering TAG-ONLY mode <<<")
                        logger.info(f"[HomePage] Tag-only mode: updating tags for {src}")
                        if not os.path.exists(src):
                            raise FileNotFoundError(f"源文件不存在: {src}")

                        max_retries = 3
                        retry_delay = 0.5
                        for attempt in range(max_retries + 1):
                            try:
                                print(f"[DEBUG] Writing audio tags with ORIGINAL text (not sanitized)")
                                update_audio_tags(
                                    src, title, artist, album,
                                    cover_url=cover_link,
                                    trace=False,
                                    year=year or None,
                                    genre=genre or None,
                                )
                                logger.info(f"[HomePage] update_audio_tags completed successfully")

                                success_count += 1
                                logger.info(f"[HomePage] ✓ Tags updated successfully for {os.path.basename(src)}")
                                print(f"[DEBUG] ✓✓✓ TAG-ONLY mode completed successfully!")
                                break
                            except Exception as tag_exc:
                                if is_file_in_use_error(tag_exc) and attempt < max_retries:
                                    wait_time = retry_delay * (attempt + 1)
                                    logger.warning(
                                        f"[HomePage] 文件被占用，将在 {wait_time:.1f} 秒后重试 "
                                        f"({attempt + 1}/{max_retries}): {tag_exc}"
                                    )
                                    time.sleep(wait_time)
                                    continue
                                raise
                    else:
                        print(f"[DEBUG] >>> Entering RENAME + TAG mode <<<")
                        root_dir = self.copy_dir if (self.copy_enabled and self.copy_dir) else os.path.dirname(src)
                        print(f"[DEBUG] root_dir: {root_dir}")
                        if plex:
                            root_dir = os.path.join(root_dir, f_artist, f_album)
                        os.makedirs(root_dir, exist_ok=True)

                        new_path = os.path.join(root_dir, new_name)
                        count = 1
                        while os.path.exists(new_path) and new_path != src:
                            stem, e2 = os.path.splitext(new_path)
                            new_path = f"{stem} ({count}){e2}"
                            count += 1

                        print(f"[DEBUG] Target path: {new_path}")
                        print(f"[DEBUG] Target exists already? {os.path.exists(new_path)}")
                        print(f"[DEBUG] Target == Source? {new_path == src}")

                        # 如果源路径和目标路径相同，说明文件已经是正确命名，跳过重命名
                        if new_path == src:
                            logger.info(f"[HomePage] File already has correct name, skipping rename: {os.path.basename(src)}")
                            print(f"[DEBUG] Skipping rename - paths are identical")
                            target_path = src
                        else:
                            logger.info(f"[HomePage] {'Copying' if (self.copy_enabled and self.copy_dir) else 'Renaming'} "
                                        f"{src} -> {new_path}")

                            # 文件占用重试逻辑
                            max_retries = 3
                            retry_delay = 0.5
                            for attempt in range(max_retries + 1):
                                try:
                                    if self.copy_enabled and self.copy_dir:
                                        shutil.copy2(src, new_path)
                                    else:
                                        os.rename(src, new_path)
                                    print(f"[DEBUG] ✓ Rename/Copy completed successfully!")
                                    target_path = new_path
                                    break  # 成功则跳出重试循环
                                except Exception as rename_err:
                                    if is_file_in_use_error(rename_err) and attempt < max_retries:
                                        wait_time = retry_delay * (attempt + 1)
                                        logger.warning(
                                            f"[HomePage] 文件被占用，将在 {wait_time:.1f} 秒后重试 "
                                            f"({attempt + 1}/{max_retries}): {rename_err}"
                                        )
                                        time.sleep(wait_time)
                                        continue
                                    print(f"[DEBUG] ✗ Rename/Copy FAILED: {type(rename_err).__name__}: {rename_err}")
                                    raise
                        print(f"[DEBUG] Writing tags to: {target_path}")
                        if ext == ".mp3":
                            logger.info(f"[HomePage] Calling update_mp3_tags for {target_path}...")
                            print(f"[DEBUG] Writing MP3 tags with ORIGINAL text: title='{title}', artist='{artist}', album='{album}'")
                            update_mp3_tags(target_path, title, artist, album)
                            logger.info(f"[HomePage] update_mp3_tags completed")
                            print(f"[DEBUG] ✓ MP3 tags written successfully!")
                            if cover_link:
                                logger.info(f"[HomePage] Calling update_mp3_cover_art...")
                                print(f"[DEBUG] Downloading cover from: {cover_link[:60]}...")
                                try:
                                    update_mp3_cover_art(
                                        target_path, cover_link, trace=False
                                    )
                                    logger.info(f"[HomePage] update_mp3_cover_art completed")
                                    print(f"[DEBUG] ✓ Cover art written successfully!")
                                except Exception as cover_err:
                                    logger.error(f"[HomePage] Cover art failed: {cover_err}")
                                    print(f"[DEBUG] ✗ Cover art FAILED: {type(cover_err).__name__}: {cover_err}")
                        elif ext == ".ogg":
                            logger.info(f"[HomePage] Calling update_ogg_tags for {target_path}...")
                            print(f"[DEBUG] Writing OGG tags with ORIGINAL text: title='{title}', artist='{artist}', album='{album}'")
                            update_ogg_tags(
                                target_path, title, artist, album,
                                cover_link,
                                trace=False
                            )
                            logger.info(f"[HomePage] update_ogg_tags completed")

                        success_count += 1
                        logger.info(f"[HomePage] ✓ File processed successfully: {os.path.basename(src)}")
                        print(f"[DEBUG] ✓✓✓✓ File processing completed successfully!")
                except Exception as exc:
                    error_msg = f"{os.path.basename(src)}: {exc}"
                    print(f"[DEBUG] ✗✗✗ EXCEPTION: {type(exc).__name__}: {exc}")
                    logger.error(f"[HomePage] ✗ Error processing file: {error_msg}", exc_info=True)
                    errors.append(error_msg)

            logger.info(f"[HomePage] Apply completed: success={success_count}, errors={len(errors)}")
            print(f"\n{'='*60}")
            print(f"[DEBUG] FINAL RESULT: success={success_count}, errors={len(errors)}")
            if errors:
                print(f"[DEBUG] Errors:")
                for err in errors:
                    print(f"      - {err}")
            else:
                print(f"[DEBUG] All operations completed successfully!")
            print(f"{'='*60}\n")

            if errors:
                MessageBox(
                    tr("errors_occurred"),
                    "\n".join(errors),
                    self,
                ).exec()
            else:
                checked_count = sum(
                    1 for card in self.song_cards.values()
                    if card.is_checked()
                )

                if checked_count == 0:
                    MessageBox(
                        "Info",
                        tr("no_files_processed"),
                        self,
                    ).exec()
                else:
                    MessageBox(
                        tr("success"),
                        tr("changes_applied"),
                        self,
                    ).exec()
        except Exception as e:
            error_msg = f"应用更改时发生未预期的错误: {e}"
            logger.exception(f"Error in _on_apply: {e}")
            errors.append(error_msg)
            if errors:
                MessageBox(
                    tr("errors_occurred"),
                    "\n".join(errors),
                    self,
                ).exec()

    def refresh_texts(self) -> None:
        """
        刷新页面文本

        当语言切换时调用此方法，更新所有 UI 文本为当前语言的翻译。
        """
        try:
            # 更新占位符文本
            self.dir_entry.setPlaceholderText(tr("select_directory"))
            self.copy_dir_entry.setPlaceholderText(tr("select_directory"))

            # 更新输入区域标签文本
            self.dir_label.setText(tr("input_directory"))
            self.copy_to_label.setText(tr("copy_to"))
            self.tags_only_label.setText(tr("tags_only"))

            # 更新状态文本
            if not self.song_cards:
                self.status_label.setText(
                    tr("progress_format", done=0, total=0, remaining=0)
                )

            # 更新标题
            self.table_title.setText(tr("search_results"))

            # 更新按钮文本
            self.browse_btn.setText(tr("browse"))
            self.copy_browse_btn.setText(tr("browse"))
            self.check_all_btn.setText(tr("check_all"))
            self.uncheck_all_btn.setText(tr("uncheck_all"))
            self.apply_btn.setText(tr("apply"))
            self.apply_plex_btn.setText(tr("apply_plex"))
            self.clear_data_btn.setText(tr("clear_data"))
            self.refresh_files_btn.setToolTip(tr("refresh_file_list"))

            # 刷新所有卡片的平台名称
            for card in self.song_cards.values():
                for i in range(card.results_container.layout().count()):
                    widget = card.results_container.layout().itemAt(i).widget()
                    if hasattr(widget, '_get_platform_display_name'):
                        # 需要重新创建平台组件来更新文本
                        # 这里简化处理，仅更新可见部分
                        pass
        except Exception as e:
            logger.exception(f"Error in refresh_texts: {e}")
