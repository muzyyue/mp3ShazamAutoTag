# -*- coding: utf-8 -*-
"""
QQ音乐Cookie失效引导对话框模块

当QQ音乐的Cookie失效或过期时，显示此对话框引导用户重新获取Cookie。
提供清晰的步骤说明和一键跳转功能。

功能特性：
- 友好的视觉提示（图标+文字说明）
- 详细的操作步骤指引
- 一键打开浏览器获取Cookie
- 支持中英文国际化
- 自适应窗口大小

使用示例：
    >>> from auto_tag.gui.dialogs.cookie_expired_dialog import show_cookie_expired_dialog
    >>> show_cookie_expired_dialog(parent=main_window)
"""

import webbrowser
from typing import Optional

from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
)
from qfluentwidgets import (
    MessageBoxBase,
    SubtitleLabel,
    BodyLabel,
    PrimaryPushButton,
    PushButton,
    IconWidget,
    FluentIcon as FIcon,
    setFont,
    isDarkTheme,
)

from auto_tag.gui.i18n import tr


class CookieExpiredDialog(MessageBoxBase):
    """
    QQ音乐Cookie失效引导对话框

    当系统检测到QQ音乐Cookie已过期或失效时显示，
    引导用户前往 y.qq.com 重新获取Cookie。

    UI布局（Fluent 图标 + 文本）：
    ┌─────────────────────────────────────────────┐
    │ [CERTIFICATE] Cookie已过期                  │ 标题
    ├─────────────────────────────────────────────┤
    │                                             │
    │ 您的QQ音乐登录凭证已失效，需要重新获取。     │ 说明文字
    │                                             │
    │ [SCROLL] 获取步骤：                          │ 步骤标题
    │ 1. 点击下方按钮打开 QQ音乐                  │ 步骤列表
    │ 2. 登录您的 QQ 账号                         │
    │ 3. 按 F12 打开开发者工具                    │
    │ 4. 切换到 Application → Cookies             │
    │ 5. 复制所有 Cookie 值                        │
    │ 6. 粘贴到设置页面的 Cookie 输入框            │
    │                                             │
    │ [LINK] 前往 QQ音乐 获取   [ACCEPT] 我知道了 │ 按钮
    └─────────────────────────────────────────────┘
    
    Attributes:
        parent (QWidget): 父窗口
        
    Example:
        >>> dialog = CookieExpiredDialog(parent=window)
        >>> dialog.exec()
    """

    # QQ音乐官网URL
    QQ_MUSIC_URL = "https://y.qq.com"

    def __init__(self, parent: Optional[QWidget] = None):
        """
        初始化Cookie失效引导对话框
        
        Args:
            parent: 父窗口组件，用于居中显示和模态控制
        """
        # MessageBoxBase 签名: (parent)，与 SongSearchResultDialog 保持一致
        super().__init__(parent)

        self._setup_ui()
        self._setup_style()
        self._setup_signals()

    def _setup_ui(self) -> None:
        """
        设置UI组件布局
        
        创建所有子控件并按照设计稿排列
        """
        # 主容器布局（复用 MessageBoxBase 提供的 viewLayout）
        self.widgetLayout = self.viewLayout
        self.widgetLayout.setContentsMargins(20, 15, 20, 10)
        self.widgetLayout.setSpacing(12)

        # ===== 警告图标 + 主标题 =====
        title_layout = QHBoxLayout()
        title_layout.setSpacing(10)
        
        self._warning_icon = IconWidget(FIcon.CERTIFICATE)
        self._warning_icon.setFixedSize(28, 28)
        title_layout.addWidget(self._warning_icon)
        
        self._title_label = SubtitleLabel(tr("settings_page.cookie_dialog.title"))
        title_layout.addWidget(self._title_label)
        title_layout.addStretch()
        
        self.widgetLayout.addLayout(title_layout)

        # ===== 说明文字 =====
        self._description_label = BodyLabel(tr("settings_page.cookie_dialog.description"))
        self._description_label.setWordWrap(True)
        self.widgetLayout.addWidget(self._description_label)

        # 分隔线
        separator = QLabel("─" * 50)
        separator.setStyleSheet("color: gray; margin: 5px 0;")
        self.widgetLayout.addWidget(separator)

        # ===== 操作步骤标题（Fluent 图标 + 文本）=====
        steps_title_layout = QHBoxLayout()
        steps_title_layout.setSpacing(6)
        self._steps_icon = IconWidget(FIcon.SCROLL)
        self._steps_icon.setFixedSize(16, 16)
        steps_title_layout.addWidget(self._steps_icon)
        self._steps_title = BodyLabel(tr("settings_page.cookie_dialog.steps_title"))
        setFont(self._steps_title, 13)
        self._steps_title.setStyleSheet("font-weight: bold; margin-top: 8px;")
        steps_title_layout.addWidget(self._steps_title)
        self.widgetLayout.addLayout(steps_title_layout)

        # ===== 步骤列表（使用只读文本框）=====
        steps_text = tr("settings_page.cookie_dialog.steps_content")
        self._steps_text_edit = QTextEdit()
        self._steps_text_edit.setPlainText(steps_text)
        self._steps_text_edit.setReadOnly(True)
        self._steps_text_edit.setMaximumHeight(140)
        self._steps_text_edit.setStyleSheet("""
            QTextEdit {
                background-color: transparent;
                border: 1px solid rgba(0, 0, 0, 30);
                border-radius: 5px;
                padding: 8px;
                font-size: 13px;
                line-height: 1.5;
            }
        """)
        self.widgetLayout.addWidget(self._steps_text_edit)

        # ===== 链接提示（Fluent 图标 + 文本）=====
        link_hint_layout = QHBoxLayout()
        link_hint_layout.setSpacing(6)
        hint_icon = IconWidget(FIcon.INFO)
        hint_icon.setFixedSize(16, 16)
        link_hint_layout.addWidget(hint_icon)
        link_hint = BodyLabel(tr("settings_page.cookie_dialog.link_hint"))
        link_hint.setStyleSheet("color: #00a1d6; font-style: italic;")
        link_hint_layout.addWidget(link_hint)
        self.widgetLayout.addLayout(link_hint_layout)

        # 添加弹性空间
        self.widgetLayout.addStretch()

        # ===== 底部按钮区域 =====
        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)

        # 主按钮：前往QQ音乐
        self._goto_button = PrimaryPushButton(FIcon.LINK, tr("settings_page.cookie_dialog.goto_button"))
        self._goto_button.setFixedWidth(180)
        self._goto_button.setCursor(Qt.PointingHandCursor)
        button_layout.addWidget(self._goto_button)

        # 次要按钮：关闭/我知道了
        self._close_button = PushButton(FIcon.ACCEPT, tr("settings_page.cookie_dialog.close_button"))
        self._close_button.setFixedWidth(120)
        self._close_button.setCursor(Qt.PointingHandCursor)
        button_layout.addWidget(self._close_button)

        self.widgetLayout.addLayout(button_layout)

        # 隐藏 MessageBoxBase 自带的默认按钮组（OK/Cancel），使用自定义按钮区域
        self.hideYesButton()
        self.hideCancelButton()

    def _setup_style(self) -> None:
        """
        设置样式和外观
        
        根据当前主题（深色/浅色）调整颜色
        """
        if isDarkTheme():
            self._steps_text_edit.setStyleSheet("""
                QTextEdit {
                    background-color: rgba(255, 255, 255, 10);
                    border: 1px solid rgba(255, 255, 255, 50);
                    border-radius: 5px;
                    padding: 8px;
                    color: white;
                    font-size: 13px;
                }
            """)
        else:
            self._steps_text_edit.setStyleSheet("""
                QTextEdit {
                    background-color: rgba(0, 0, 0, 3);
                    border: 1px solid rgba(0, 0, 0, 30);
                    border-radius: 5px;
                    padding: 8px;
                    font-size: 13px;
                }
            """)

        # 设置对话框固定宽度
        self.setFixedWidth(520)

    def _setup_signals(self) -> None:
        """
        连接信号槽
        
        绑定按钮点击事件到对应的处理函数
        """
        self._goto_button.clicked.connect(self._on_goto_clicked)
        self._close_button.clicked.connect(self._on_close_clicked)

    def _on_goto_clicked(self) -> None:
        """
        "前往QQ音乐"按钮点击处理
        
        打开浏览器访问QQ音乐官网，然后关闭对话框
        """
        try:
            webbrowser.open(self.QQ_MUSIC_URL)
            print(f"[CookieExpiredDialog] 已打开浏览器: {self.QQ_MUSIC_URL}")
        except Exception as e:
            print(f"[CookieExpiredDialog] 打开浏览器失败: {e}")
        
        self.accept()

    def _on_close_clicked(self) -> None:
        """
        "我知道了"/关闭按钮点击处理
        
        直接关闭对话框
        """
        self.accept()


def show_cookie_expired_dialog(parent: Optional[QWidget] = None) -> int:
    """
    显示Cookie失效引导对话框的便捷函数
    
    这是外部调用的主要接口，封装了对话框的创建和执行。
    
    Args:
        parent: 父窗口组件
        
    Returns:
        int: QDialog返回值 (Accepted=1, Rejected=0)
    
    Example:
        >>> from auto_tag.gui.dialogs.cookie_expired_dialog import show_cookie_expired_dialog
        >>> result = show_cookie_expired_dialog(parent=self.window())
        >>> if result == Dialog.Accepted:
        ...     print("用户已查看引导信息")
    """
    dialog = CookieExpiredDialog(parent=parent)
    return dialog.exec()
