# -*- coding: utf-8 -*-
"""
关于页面模块

该模块提供应用程序的关于界面，展示项目相关信息。
使用 QFluentWidgets 库实现现代化的 Fluent Design 风格界面。

功能：
    - 应用信息展示（名称、版本号）
    - 检查更新按钮
    - 更新设置（自动检查更新开关）
    - 反馈链接（报告错误、建议功能、讨论区）
    - 其他链接（GitHub 仓库、许可证）

依赖：
    - PySide6: GUI 框架
    - qfluentwidgets: Fluent Design 风格组件库
    - auto_tag.gui.i18n: 国际化支持

Example:
    >>> from auto_tag.gui.pages.about_page import AboutPage
    >>> page = AboutPage()
    >>> page.show()
"""

import logging
import os
import sys
import urllib.request
from typing import Optional

from PySide6.QtCore import Qt, QUrl, QEvent, QPointF
from PySide6.QtGui import (
    QFont,
    QDesktopServices,
    QCursor,
    QPainter,
    QColor,
    QPen,
    QPaintEvent,
    QMouseEvent,
)
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
)

from qfluentwidgets import (
    BodyLabel,
    SubtitleLabel,
    PushButton,
    SwitchButton,
    CardWidget,
    FluentIcon as FIF,
    IconWidget,
    InfoBar,
    InfoBarPosition,
    isDarkTheme,
    qconfig,
)

from auto_tag.gui.i18n import tr
from auto_tag.gui.config import config


logger = logging.getLogger(__name__)


def _base_dir() -> str:
    """
    获取项目根目录或 PyInstaller 临时目录

    Returns:
        str: 项目根目录路径
    """
    if getattr(sys, "frozen", False):
        return sys._MEIPASS  # type: ignore[attr-defined]
    here = os.path.abspath(os.path.dirname(__file__))
    return os.path.abspath(os.path.join(here, os.pardir, os.pardir, os.pardir))


def _get_version() -> str:
    """
    获取应用版本号（优先从 auto_tag.version 模块导入）

    Returns:
        str: 版本号字符串，读取失败时返回 "unknown"
    """
    try:
        from auto_tag.version import __version__

        return __version__
    except Exception:
        pass

    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            return "unknown"

    pyproject_path = os.path.join(_base_dir(), "pyproject.toml")
    if not os.path.exists(pyproject_path):
        return "unknown"

    try:
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
        return data.get("project", {}).get("version", "unknown")
    except Exception:
        return "unknown"


class LinkRowWidget(QWidget):
    """
    可点击的链接行组件

    布局：左侧 Fluent 图标 + 文本 + 右侧 chevron 指示符。
    悬停时显示圆角高亮背景，颜色随主题自动适配（浅色/深色）。
    点击后通过 QDesktopServices 打开外部链接。
    """

    def __init__(self, icon: FIF, text: str, url: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._url = url
        self._hover = False
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 5, 20, 5)
        layout.setSpacing(12)

        icon_widget = IconWidget(icon)
        icon_widget.setFixedSize(20, 20)
        layout.addWidget(icon_widget)

        self._text_label = BodyLabel(text)
        layout.addWidget(self._text_label)
        layout.addStretch()

        self.setMinimumHeight(40)

        qconfig.themeChangedFinished.connect(self._on_theme_changed)

    def set_text(self, text: str) -> None:
        """设置行文本（供语言切换时刷新）"""
        self._text_label.setText(text)

    def enterEvent(self, event: QEvent) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        """绘制悬停圆角高亮背景与右侧 chevron 指示符"""
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._hover:
            hover_color = QColor(255, 255, 255, 24) if isDarkTheme() else QColor(0, 0, 0, 13)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(hover_color)
            painter.drawRoundedRect(self.rect().adjusted(2, 2, -2, -2), 8, 8)

        self._draw_chevron(painter)

    def _draw_chevron(self, painter: QPainter) -> None:
        """在右侧绘制 chevron 指示符，颜色随主题适配"""
        color = QColor(255, 255, 255, 110) if isDarkTheme() else QColor(0, 0, 0, 96)
        pen = QPen(color)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        cx = self.width() - 13
        cy = self.height() // 2
        points = [QPointF(cx - 3, cy - 4), QPointF(cx + 3, cy), QPointF(cx - 3, cy + 4)]
        painter.drawPolyline(points)

    def _on_theme_changed(self) -> None:
        """主题切换时刷新行内图标与 chevron"""
        for icon_widget in self.findChildren(IconWidget):
            icon_widget.update()
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            QDesktopServices.openUrl(QUrl(self._url))
        super().mousePressEvent(event)


class AboutPage(QWidget):
    """
    关于页面类

    提供应用程序关于界面，展示项目相关信息和外部链接。
    使用 CardWidget 实现卡片式布局。

    Example:
        >>> page = AboutPage()
        >>> page.show()
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._version = _get_version()
        self._github_url = "https://github.com/muzyyue/Imusic"
        self._issues_url = "https://github.com/muzyyue/Imusic/issues/new"
        self._suggest_feature_url = "https://github.com/muzyyue/Imusic/issues/new?labels=enhancement"
        self._discussions_url = "https://github.com/muzyyue/Imusic/discussions"
        self._license_url = "https://github.com/muzyyue/Imusic/blob/main/LICENSE"

        self._setup_ui()
        qconfig.themeChangedFinished.connect(self._on_theme_changed)

    def _add_section_header(self, parent_layout: QVBoxLayout, icon: FIF, text: str) -> SubtitleLabel:
        """
        创建带前导 Fluent 图标的卡片标题行并加入指定布局

        Args:
            parent_layout: 目标布局
            icon: 标题前导的 Fluent 图标
            text: 标题文本

        Returns:
            SubtitleLabel: 标题标签（供语言切换时刷新）
        """
        header = QWidget()
        layout = QHBoxLayout(header)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(8)

        icon_widget = IconWidget(icon)
        icon_widget.setFixedSize(16, 16)
        layout.addWidget(icon_widget)

        label = SubtitleLabel(text)
        font = QFont()
        font.setPointSize(14)
        label.setFont(font)
        layout.addWidget(label)
        layout.addStretch()

        parent_layout.addWidget(header)
        return label

    def _on_theme_changed(self) -> None:
        """主题切换时刷新页面内所有 Fluent 图标"""
        for icon_widget in self.findChildren(IconWidget):
            icon_widget.update()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(40, 30, 40, 30)
        main_layout.setSpacing(20)

        # 页面标题
        self._title_label = SubtitleLabel(tr("about_page.title"))
        font = QFont()
        font.setPointSize(18)
        font.setBold(True)
        self._title_label.setFont(font)
        main_layout.addWidget(self._title_label)

        # 应用信息行：图标 + 名称 + 版本
        app_info_layout = QHBoxLayout()
        app_info_layout.setSpacing(16)

        self._app_icon_label = QLabel()
        self._app_icon_label.setFixedSize(48, 48)
        self._load_app_icon()
        app_info_layout.addWidget(self._app_icon_label)

        app_text_layout = QVBoxLayout()
        app_text_layout.setSpacing(4)

        self._app_name_label = BodyLabel("Imusic")
        name_font = QFont()
        name_font.setPointSize(16)
        name_font.setBold(True)
        self._app_name_label.setFont(name_font)
        app_text_layout.addWidget(self._app_name_label)

        self._version_label = BodyLabel(
            f"{tr('about_page.version_prefix')} {self._version}"
        )
        app_text_layout.addWidget(self._version_label)

        app_info_layout.addLayout(app_text_layout)
        app_info_layout.addStretch()
        main_layout.addLayout(app_info_layout)

        # 检查更新按钮
        self._check_update_button = PushButton(tr("about_page.check_update"))
        self._check_update_button.setFixedHeight(36)
        self._check_update_button.setFixedWidth(120)
        self._check_update_button.clicked.connect(self._on_check_update_clicked)
        main_layout.addWidget(self._check_update_button)

        # 更新设置卡片
        update_card = CardWidget(self)
        update_card_layout = QVBoxLayout(update_card)
        update_card_layout.setContentsMargins(16, 16, 16, 16)
        update_card_layout.setSpacing(0)

        self._update_settings_section = self._add_section_header(
            update_card_layout, FIF.CLOUD_DOWNLOAD, tr("about_page.update_settings")
        )

        auto_update_row = QWidget()
        auto_update_layout = QHBoxLayout(auto_update_row)
        auto_update_layout.setContentsMargins(4, 5, 4, 5)
        auto_update_layout.setSpacing(12)

        auto_update_icon = IconWidget(FIF.UPDATE)
        auto_update_icon.setFixedSize(20, 20)
        auto_update_layout.addWidget(auto_update_icon)

        self._auto_update_label = BodyLabel(tr("about_page.auto_check_update"))
        auto_update_layout.addWidget(self._auto_update_label)
        auto_update_layout.addStretch()

        self._auto_update_switch = SwitchButton()
        self._auto_update_switch.setChecked(config.auto_check_update)
        self._auto_update_switch.checkedChanged.connect(self._on_auto_update_changed)
        auto_update_layout.addWidget(self._auto_update_switch)

        auto_update_row.setMinimumHeight(40)

        update_card_layout.addWidget(auto_update_row)
        main_layout.addWidget(update_card)

        # 反馈卡片
        feedback_card = CardWidget(self)
        feedback_card_layout = QVBoxLayout(feedback_card)
        feedback_card_layout.setContentsMargins(16, 16, 16, 16)
        feedback_card_layout.setSpacing(2)

        self._feedback_section = self._add_section_header(
            feedback_card_layout, FIF.FEEDBACK, tr("about_page.feedback")
        )

        self._report_bug_row = LinkRowWidget(
            FIF.HELP, tr("about_page.report_bug"), self._issues_url
        )
        feedback_card_layout.addWidget(self._report_bug_row)

        self._suggest_feature_row = LinkRowWidget(
            FIF.QUICK_NOTE, tr("about_page.suggest_feature"), self._suggest_feature_url
        )
        feedback_card_layout.addWidget(self._suggest_feature_row)

        self._discussions_row = LinkRowWidget(
            FIF.CHAT, tr("about_page.discussions"), self._discussions_url
        )
        feedback_card_layout.addWidget(self._discussions_row)

        main_layout.addWidget(feedback_card)

        # 其他链接卡片
        links_card = CardWidget(self)
        links_card_layout = QVBoxLayout(links_card)
        links_card_layout.setContentsMargins(16, 16, 16, 16)
        links_card_layout.setSpacing(2)

        self._other_links_section = self._add_section_header(
            links_card_layout, FIF.LINK, tr("about_page.other_links")
        )

        self._github_repo_row = LinkRowWidget(
            FIF.GITHUB, tr("about_page.github_repo"), self._github_url
        )
        links_card_layout.addWidget(self._github_repo_row)

        self._license_row = LinkRowWidget(
            FIF.DOCUMENT, tr("about_page.license"), self._license_url
        )
        links_card_layout.addWidget(self._license_row)

        main_layout.addWidget(links_card)

        # 弹性空间
        main_layout.addStretch()

    def _load_app_icon(self) -> None:
        try:
            from PySide6.QtGui import QPixmap

            icon_path = os.path.join(_base_dir(), "assets", "imusic.ico")
            if os.path.exists(icon_path):
                pixmap = QPixmap(icon_path)
                if not pixmap.isNull():
                    scaled = pixmap.scaled(
                        48, 48,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
                    self._app_icon_label.setPixmap(scaled)
        except Exception:
            pass

    def _open_url(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))

    def _on_check_update_clicked(self) -> None:
        self.check_for_updates()

    def _on_auto_update_changed(self, checked: bool) -> None:
        config.set_auto_check_update(checked)
        if checked:
            self.check_for_updates()

    def check_for_updates(self) -> None:
        """调用 GitHub API 获取最新版本信息"""
        try:
            api_url = "https://api.github.com/repos/muzyyue/Imusic/releases/latest"
            req = urllib.request.Request(api_url, headers={"User-Agent": "Imusic"})
            with urllib.request.urlopen(req, timeout=10) as response:
                data = __import__("json").loads(response.read().decode())
                latest_version = data.get("tag_name", "").lstrip("v")

                if latest_version and latest_version != self._version:
                    InfoBar.info(
                        title=tr("about_page.new_version_available"),
                        content=tr("about_page.latest_version").format(version=latest_version),
                        parent=self.window(),
                        position=InfoBarPosition.TOP,
                        duration=5000,
                    )
                else:
                    InfoBar.success(
                        title=tr("about_page.up_to_date"),
                        content="",
                        parent=self.window(),
                        position=InfoBarPosition.TOP,
                        duration=3000,
                    )
        except Exception as e:
            logger.warning(f"检查更新失败: {e}")

    def refresh_texts(self) -> None:
        self._title_label.setText(tr("about_page.title"))
        self._version_label.setText(
            f"{tr('about_page.version_prefix')} {self._version}"
        )
        self._check_update_button.setText(tr("about_page.check_update"))
        self._update_settings_section.setText(tr("about_page.update_settings"))
        self._auto_update_label.setText(tr("about_page.auto_check_update"))
        self._feedback_section.setText(tr("about_page.feedback"))
        self._other_links_section.setText(tr("about_page.other_links"))

        self._report_bug_row.set_text(tr("about_page.report_bug"))
        self._suggest_feature_row.set_text(tr("about_page.suggest_feature"))
        self._discussions_row.set_text(tr("about_page.discussions"))
        self._github_repo_row.set_text(tr("about_page.github_repo"))
        self._license_row.set_text(tr("about_page.license"))
