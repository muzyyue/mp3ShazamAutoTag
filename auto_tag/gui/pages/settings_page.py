# -*- coding: utf-8 -*-
"""
设置页面模块

该模块提供应用程序的设置界面，包括语言、主题、**搜索源配置**等选项。
使用 QFluentWidgets 库实现现代化的 Fluent Design 风格界面。

功能：
    - 语言切换
    - 主题切换（浅色/深色/跟随系统）
    - **搜索源选择与配置**
    - 设置持久化存储

依赖：
    - PyQt6: GUI 框架
    - qfluentwidgets: Fluent Design 风格组件库
    - auto_tag.gui.config: 配置管理
    - auto_tag.gui.i18n: 国际化支持

Example:
    >>> from auto_tag.gui.pages.settings_page import SettingsPage
    >>> page = SettingsPage()
    >>> page.show()
"""

import logging
from typing import Optional

from PySide6.QtCore import Qt, Signal, QEvent, QObject
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
)

from qfluentwidgets import (
    ComboBox,
    BodyLabel,
    SubtitleLabel,
    SwitchButton,
    setTheme,
    Theme,
    isDarkTheme,
    CheckBox,
    PlainTextEdit,
    InfoBarIcon,
    InfoBar,
    PushButton,
    FluentIcon,
    IconWidget,
)

from auto_tag.gui.config import config, AppConfig
from auto_tag.gui.i18n import tr
from auto_tag.gui.dialogs.cookie_expired_dialog import show_cookie_expired_dialog


logger = logging.getLogger(__name__)


class SettingsPage(QWidget):
    """
    设置页面类

    提供应用程序设置界面，支持语言、主题和**搜索源**切换。

    Signals:
        language_changed (str): 语言变更信号，参数为语言代码
        theme_changed (str): 主题变更信号，参数为主题名称
        search_config_changed: 搜索配置变更信号（无参数）

    Example:
        >>> page = SettingsPage()
        >>> page.language_changed.connect(lambda lang: print(f"Language changed to {lang}"))
        >>> page.search_config_changed.connect(on_search_settings_updated)
    """

    # 定义信号
    language_changed = Signal(str)
    theme_changed = Signal(str)
    search_config_changed = Signal()  # 新增：搜索配置变更信号

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        初始化设置页面

        Args:
            parent: 父窗口，默认为 None
        """
        super().__init__(parent)

        # 创建主布局
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(40, 30, 40, 30)
        self._layout.setSpacing(20)

        # 页面标题
        self._title_label = SubtitleLabel(tr("settings_page.title"))
        font = QFont()
        font.setPointSize(18)
        font.setBold(True)
        self._title_label.setFont(font)
        self._layout.addWidget(self._title_label)

        # 常规设置分组标题
        self._general_section = SubtitleLabel(tr("settings_page.general_section"))
        font_general = QFont()
        font_general.setPointSize(14)
        self._general_section.setFont(font_general)
        self._layout.addWidget(self._general_section)

        # 语言设置
        language_layout = QHBoxLayout()
        self._language_label = BodyLabel(tr("settings_page.language_label"))
        self._language_combo = ComboBox()
        self._language_combo.addItems([tr("settings_page.languages.zh"), tr("settings_page.languages.en")])
        self._language_combo.setMinimumWidth(200)
        
        # 设置当前语言
        current_lang_index = 0 if config.language == "zh" else 1
        self._language_combo.setCurrentIndex(current_lang_index)
        
        # 连接信号
        self._language_combo.currentIndexChanged.connect(self._on_language_changed)
        
        language_layout.addWidget(self._language_label)
        language_layout.addStretch()
        language_layout.addWidget(self._language_combo)
        self._layout.addLayout(language_layout)

        # 主题设置
        theme_layout = QHBoxLayout()
        self._theme_label = BodyLabel(tr("settings_page.theme_label"))
        self._theme_combo = ComboBox()
        self._theme_combo.addItems([
            tr("settings_page.themes.light"),
            tr("settings_page.themes.dark"),
            tr("settings_page.themes.auto")
        ])
        self._theme_combo.setMinimumWidth(200)
        
        # 设置当前主题
        current_theme_index = {"light": 0, "dark": 1, "auto": 2}.get(config.theme, 2)
        self._theme_combo.setCurrentIndex(current_theme_index)
        
        # 连接信号
        self._theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        
        theme_layout.addWidget(self._theme_label)
        theme_layout.addStretch()
        theme_layout.addWidget(self._theme_combo)
        self._layout.addLayout(theme_layout)

        # ===== 新增：文件名编码设置 (2026-05-02) =====
        filename_encoding_layout = QHBoxLayout()
        self._filename_encoding_label = BodyLabel(tr("settings_page.filename_encoding_label"))
        self._filename_encoding_switch = SwitchButton()
        self._filename_encoding_switch.setChecked(config.ascii_only_filenames)
        self._filename_encoding_switch.setToolTip(
            tr("settings_page.filename_encoding_tooltip")
        )

        # 连接信号
        self._filename_encoding_switch.checkedChanged.connect(self._on_filename_encoding_toggled)

        filename_encoding_layout.addWidget(self._filename_encoding_label)
        filename_encoding_layout.addStretch()
        filename_encoding_layout.addWidget(self._filename_encoding_switch)
        self._layout.addLayout(filename_encoding_layout)

        # ===== 新增：搜索设置分组 =====
        self._search_section = SubtitleLabel(tr("settings_page.search_settings_section"))
        self._search_section.setFont(font_general)
        self._layout.addWidget(self._search_section)

        # 搜索源多选 - 拆分为两行：识别引擎 + 补充搜索
        # 第一行：音频指纹识别引擎（真正的音频识别）
        engine_layout = QHBoxLayout()
        self._engine_label = BodyLabel(tr("settings_page.engine_label"))
        engine_layout.addWidget(self._engine_label)
        engine_layout.addStretch()

        self._source_checkboxes: dict[str, CheckBox] = {}
        engine_sources = ["acoustid", "shazam"]
        for i, source_key in enumerate(engine_sources):
            cb = CheckBox(tr(f"settings_page.sources.{source_key}"))
            self._source_checkboxes[source_key] = cb
            cb.stateChanged.connect(self._on_search_sources_changed)
            engine_layout.addWidget(cb)
            if i < len(engine_sources) - 1:
                engine_layout.addSpacing(16)

        self._layout.addLayout(engine_layout)

        # 第二行：关键词搜索平台（文本匹配补充）
        supplement_layout = QHBoxLayout()
        self._supplement_label = BodyLabel(tr("settings_page.supplement_label"))
        supplement_layout.addWidget(self._supplement_label)
        supplement_layout.addStretch()

        supplement_sources = ["netease", "kugou", "qqmusic"]
        for i, source_key in enumerate(supplement_sources):
            cb = CheckBox(tr(f"settings_page.sources.{source_key}"))
            self._source_checkboxes[source_key] = cb
            cb.stateChanged.connect(self._on_search_sources_changed)
            supplement_layout.addWidget(cb)
            if i < len(supplement_sources) - 1:
                supplement_layout.addSpacing(16)

        self._layout.addLayout(supplement_layout)

        # 搜索关键词模式（控制传给网易云/QQ音乐等平台的关键词格式）
        keyword_mode_layout = QHBoxLayout()
        self._keyword_mode_label = BodyLabel(tr("settings_page.keyword_mode_label"))
        self._keyword_mode_combo = ComboBox()
        self._keyword_mode_combo.setMinimumWidth(200)

        for mode_value in AppConfig.VALID_KEYWORD_MODES:
            translated_name = tr(f"settings_page.keyword_modes.{mode_value}")
            self._keyword_mode_combo.addItem(translated_name, userData=mode_value)

        current_mode_index = list(AppConfig.VALID_KEYWORD_MODES).index(
            config.search_keyword_mode
        ) if config.search_keyword_mode in AppConfig.VALID_KEYWORD_MODES else 0
        self._keyword_mode_combo.setCurrentIndex(current_mode_index)

        self._keyword_mode_combo.currentIndexChanged.connect(self._on_keyword_mode_changed)

        keyword_mode_layout.addWidget(self._keyword_mode_label)
        keyword_mode_layout.addStretch()
        keyword_mode_layout.addWidget(self._keyword_mode_combo)
        self._layout.addLayout(keyword_mode_layout)

        # 网易云搜索类型（条件显示）
        netease_type_layout = QHBoxLayout()
        self._netease_type_label = BodyLabel(tr("settings_page.netease_type_label"))
        self._netease_type_combo = ComboBox()
        self._netease_type_combo.setMinimumWidth(300)
        
        # 添加网易云支持的搜索类型选项
        for type_value, _type_name in AppConfig.NETEASE_SEARCH_TYPES.items():
            translated_name = tr(f"settings_page.netease_types.{type_value}")
            self._netease_type_combo.addItem(translated_name, userData=type_value)
        
        # 设置当前类型
        current_type_index = list(AppConfig.NETEASE_SEARCH_TYPES.keys()).index(
            config.netease_search_type
        ) if config.netease_search_type in AppConfig.NETEASE_SEARCH_TYPES else 0
        self._netease_type_combo.setCurrentIndex(current_type_index)
        
        # 连接信号
        self._netease_type_combo.currentIndexChanged.connect(self._on_netease_type_changed)
        
        netease_type_layout.addWidget(self._netease_type_label)
        netease_type_layout.addStretch()
        netease_type_layout.addWidget(self._netease_type_combo)
        self._layout.addLayout(netease_type_layout)

        # 包含电台开关（条件显示）
        radio_layout = QHBoxLayout()
        self._radio_label = BodyLabel(tr("settings_page.include_radio_label"))
        self._radio_switch = SwitchButton()
        self._radio_switch.setChecked(config.include_radio)
        
        # 连接信号
        self._radio_switch.checkedChanged.connect(self._on_radio_toggled)
        
        radio_layout.addWidget(self._radio_label)
        radio_layout.addStretch()
        radio_layout.addWidget(self._radio_switch)
        self._layout.addLayout(radio_layout)

        # ===== 新增：QQ音乐Cookie输入 (2026-05-05) =====
        cookie_layout = QHBoxLayout()
        self._qq_music_cookie_label = BodyLabel(tr("settings_page.qq_music_cookie_label"))
        cookie_layout.addWidget(self._qq_music_cookie_label)
        cookie_layout.addStretch()

        # Cookie多行文本输入框
        self._qq_music_cookie_edit = PlainTextEdit()
        self._qq_music_cookie_edit.setPlaceholderText(tr("settings_page.qq_music_cookie_placeholder"))
        self._qq_music_cookie_edit.setToolTip(tr("settings_page.qq_music_cookie_tooltip"))
        self._qq_music_cookie_edit.setFixedHeight(80)
        self._qq_music_cookie_edit.setMinimumWidth(400)

        # 设置当前Cookie值
        current_cookie = config.qq_music_cookie
        if current_cookie:
            self._qq_music_cookie_edit.setPlainText(current_cookie)

        # 连接文本变化信号（用于实时验证）
        self._qq_music_cookie_edit.textChanged.connect(self._on_qq_music_cookie_changed)

        # Cookie输入区域使用垂直布局（标签 + 输入框）
        cookie_container = QVBoxLayout()
        cookie_container.addLayout(cookie_layout)
        cookie_container.addWidget(self._qq_music_cookie_edit)

        # 验证状态提示（Fluent 图标 + 标签）
        validation_hbox = QHBoxLayout()
        validation_hbox.setSpacing(6)
        self._cookie_validation_icon = IconWidget(FluentIcon.CANCEL)
        self._cookie_validation_icon.setFixedSize(16, 16)
        self._cookie_validation_icon.hide()
        self._cookie_validation_label = BodyLabel("")
        self._cookie_validation_label.setWordWrap(True)
        validation_hbox.addWidget(self._cookie_validation_icon)
        validation_hbox.addWidget(self._cookie_validation_label)
        cookie_container.addLayout(validation_hbox)

        # ===== 新增：刷新登录按钮 (2026-05-05) =====
        refresh_button_layout = QHBoxLayout()
        refresh_button_layout.addStretch()

        self._refresh_cookie_button = PushButton(FluentIcon.SYNC, tr("settings_page.refresh_cookie_button"))
        self._refresh_cookie_button.setToolTip(tr("settings_page.refresh_cookie_tooltip"))
        self._refresh_cookie_button.setFixedWidth(120)
        self._refresh_cookie_button.clicked.connect(self._on_refresh_cookie_clicked)

        refresh_button_layout.addWidget(self._refresh_cookie_button)
        cookie_container.addLayout(refresh_button_layout)

        self._layout.addLayout(cookie_container)

        # 弹性空间，将内容推到顶部
        self._layout.addStretch()

        # 设置搜索源选中状态（必须在所有属性创建之后，避免信号回调访问未初始化属性）
        current_sources = config.search_sources
        for source_key, cb in self._source_checkboxes.items():
            cb.blockSignals(True)
            cb.setChecked(source_key in current_sources)
            cb.blockSignals(False)
        self._ensure_at_least_one_engine_checked()

        # 根据初始搜索源状态更新UI可见性（任一选中源包含 netease 则显示）
        self._update_netease_options_visibility("netease" in config.search_sources)

        # 根据初始搜索源状态更新QQ音乐Cookie可见性（2026-05-05 新增）
        self._update_qq_music_cookie_visibility("qqmusic" in config.search_sources)

        logger.debug("Settings page initialized with search source configuration")

    def _on_language_changed(self, index: int) -> None:
        """
        语言切换回调

        Args:
            index: 下拉框选中索引 (0=中文, 1=英文)
        """
        lang_code_map = {0: "zh", 1: "en"}
        lang_code = lang_code_map.get(index, "zh")

        from auto_tag.gui.i18n import translator
        translator.load_language(lang_code)

        config.set_language(lang_code)
        logger.info(f"Language changed to: {lang_code}")

        self.language_changed.emit(lang_code)
        self.refresh_texts()

    def _on_theme_changed(self, index: int) -> None:
        """
        主题切换回调

        Args:
            index: 下拉框选中索引 (0=浅色, 1=深色, 2=跟随系统)
        """
        theme_name_map = {0: "light", 1: "dark", 2: "auto"}
        theme_name = theme_name_map.get(index, "auto")

        theme_enum_map = {
            "light": Theme.LIGHT,
            "dark": Theme.DARK,
            "auto": Theme.AUTO
        }
        theme_enum = theme_enum_map.get(theme_name, Theme.AUTO)

        setTheme(theme_enum)
        config.set_theme(theme_name)
        
        logger.info(f"Theme changed to: {theme_name}")
        self.theme_changed.emit(theme_name)

    def _on_search_sources_changed(self) -> None:
        """
        搜索源多选变更回调

        当用户勾选/取消勾选搜索源时：
        1. 收集所有选中的源
        2. 确保至少有一个源被选中
        3. 更新配置和网易云选项可见性
        4. 记录日志
        """
        selected = [
            key for key, cb in self._source_checkboxes.items()
            if cb.isChecked()
        ]

        if not selected:
            self._ensure_at_least_one_engine_checked()
            return

        try:
            config.set_search_sources(selected)
            logger.info(f"Search sources changed to: {selected}")

            # 更新网易云选项的可见性（选中包含 netease 时显示）
            self._update_netease_options_visibility("netease" in selected)

            # 更新QQ音乐Cookie输入框的可见性（选中包含 qqmusic 时显示）(2026-05-05 新增)
            self._update_qq_music_cookie_visibility("qqmusic" in selected)

            # 发射信号通知其他组件
            self.search_config_changed.emit()

        except Exception as e:
            logger.error(f"Failed to change search sources: {e}")

    def _ensure_at_least_one_engine_checked(self) -> None:
        """
        确保至少有一个音频指纹识别引擎被选中

        如果所有识别引擎 CheckBox 都未选中，默认勾选 Shazam
        """
        engine_keys = ["acoustid", "shazam"]
        has_engine_checked = any(
            self._source_checkboxes[k].isChecked()
            for k in engine_keys
            if k in self._source_checkboxes
        )
        if not has_engine_checked:
            self._source_checkboxes["shazam"].setChecked(True)
            logger.info("Ensured at least one engine (shazam) is checked")
    
    def _on_netease_type_changed(self, index: int) -> None:
        """
        网易云搜索类型变更回调
        
        Args:
            index: 下拉框当前选中索引
        """
        type_value = self._netease_type_combo.itemData(index)
        
        if type_value is not None and isinstance(type_value, int):
            try:
                config.set_netease_search_type(type_value)
                logger.info(f"NetEase search type changed to: {type_value} ({AppConfig.NETEASE_SEARCH_TYPES.get(type_value)})")
                
                # 发射信号
                self.search_config_changed.emit()
                
            except Exception as e:
                logger.error(f"Failed to change NetEase search type: {e}")
    
    def _on_radio_toggled(self, checked: bool) -> None:
        """
        电台开关状态变更回调
        
        Args:
            checked: 开关是否开启
        """
        try:
            config.set_include_radio(checked)
            logger.info(f"Include radio toggle changed to: {checked}")
            
            # 发射信号
            self.search_config_changed.emit()
            
        except Exception as e:
            logger.error(f"Failed to change radio toggle: {e}")

    def _on_filename_encoding_toggled(self, checked: bool) -> None:
        """
        文件名编码模式开关状态变更回调 (2026-05-02 新增)

        Args:
            checked (bool): 是否启用 ASCII-only 模式
                - True: 将非 ASCII 字符（如中文、日文）转换为英文近似音译
                - False: 保留原始 Unicode 字符（默认，推荐）
        """
        try:
            config.set_ascii_only_filenames(checked)
            mode_str = "ASCII-only" if checked else "Unicode"
            logger.info(f"Filename encoding mode changed to: {mode_str}")

        except Exception as e:
            logger.error(f"Failed to change filename encoding mode: {e}")

    def _on_keyword_mode_changed(self, index: int) -> None:
        """
        搜索关键词模式变更回调
        
        Args:
            index: 下拉框当前选中索引
        """
        mode_value = self._keyword_mode_combo.itemData(index)
        
        if mode_value is not None and isinstance(mode_value, str):
            try:
                config.set_search_keyword_mode(mode_value)
                logger.info(f"Keyword mode changed to: {mode_value}")
                
                self.search_config_changed.emit()
                
            except Exception as e:
                logger.error(f"Failed to change keyword mode: {e}")
    
    def _update_netease_options_visibility(self, visible: bool) -> None:
        """
        更新网易云专用选项的可见性
        
        当主搜索源为网易云音乐时显示，否则隐藏。
        
        Args:
            visible: 是否可见
        """
        # 搜索类型选择器及其标签
        self._netease_type_label.setVisible(visible)
        self._netease_type_combo.setVisible(visible)
        
        # 电台开关及其标签
        self._radio_label.setVisible(visible)
        self._radio_switch.setVisible(visible)
        
        logger.debug(f"NetEase options visibility updated: {'visible' if visible else 'hidden'}")

    def _update_qq_music_cookie_visibility(self, visible: bool) -> None:
        """
        更新QQ音乐Cookie输入框和刷新按钮的可见性 (2026-05-05 新增)

        当QQ音乐搜索源被选中时显示，否则隐藏。

        Args:
            visible: 是否可见
        """
        self._qq_music_cookie_label.setVisible(visible)
        self._qq_music_cookie_edit.setVisible(visible)
        self._cookie_validation_label.setVisible(visible)
        # 状态图标仅在有状态文本时显示
        self._cookie_validation_icon.setVisible(
            visible and self._cookie_validation_label.text() != ""
        )
        self._refresh_cookie_button.setVisible(visible)  # 新增：刷新按钮也跟随显示

        logger.debug(f"QQ Music cookie input visibility updated: {'visible' if visible else 'hidden'}")

    def _set_cookie_validation(self, icon: Optional[FluentIcon], text: str, color: Optional[str] = None) -> None:
        """设置Cookie验证状态提示（Fluent 图标 + 文本 + 颜色）

        Args:
            icon: Fluent 图标；None 表示清空提示并隐藏图标
            text: 状态文本
            color: 文本颜色（green/red/orange/blue），None 则不修改颜色
        """
        self._cookie_validation_label.setText(text)
        if icon is None:
            self._cookie_validation_icon.hide()
            return
        self._cookie_validation_icon.setIcon(icon)
        self._cookie_validation_icon.show()
        if color is not None:
            self._cookie_validation_label.setStyleSheet(f"color: {color};")

    def _on_qq_music_cookie_changed(self) -> None:
        """
        QQ音乐Cookie文本变化回调 (2026-05-05 新增)

        当用户在Cookie输入框中输入或修改内容时触发：
        1. 实时验证Cookie格式
        2. 显示验证结果（成功/错误提示）
        3. 验证通过后自动保存到配置
        """
        from auto_tag.utils.validation import validate_qq_music_cookie

        cookie_text = self._qq_music_cookie_edit.toPlainText().strip()

        if not cookie_text:
            # 空内容，清除提示并清空配置
            self._set_cookie_validation(None, "")
            try:
                config.set_qq_music_cookie("")
            except ValueError:
                pass
            return

        # 执行验证
        is_valid, error_msg = validate_qq_music_cookie(cookie_text)

        if is_valid:
            # 验证通过，保存到配置
            self._set_cookie_validation(FluentIcon.ACCEPT, "Cookie格式正确", "green")
            try:
                config.set_qq_music_cookie(cookie_text)
                logger.info("QQ Music cookie validated and saved successfully")
            except ValueError as e:
                self._set_cookie_validation(FluentIcon.CANCEL, f"保存失败: {str(e)}", "red")
                logger.error(f"Failed to save QQ Music cookie: {e}")
        else:
            # 验证失败，显示错误信息
            self._set_cookie_validation(FluentIcon.CANCEL, error_msg, "red")
            logger.debug(f"QQ Music cookie validation failed: {error_msg}")

    def _on_refresh_cookie_clicked(self) -> None:
        """
        刷新QQ音乐Cookie登录状态回调 (2026-05-05 新增)

        当用户点击"刷新登录"按钮时触发：
        1. 检查当前是否已设置Cookie
        2. 调用QQ音乐 /user/refresh API刷新登录状态
        3. 根据返回结果更新Cookie或显示错误
        4. 提供清晰的状态反馈

        该功能可以延长Cookie的有效期，避免频繁手动复制粘贴。
        """
        import http.client
        import json as json_lib
        from auto_tag.utils.validation import mask_cookie_for_logging, validate_qq_music_cookie

        current_cookie = self._qq_music_cookie_edit.toPlainText().strip()

        # 前置条件检查：必须有Cookie才能刷新
        if not current_cookie:
            self._set_cookie_validation(FluentIcon.CANCEL, "请先输入Cookie再刷新", "orange")
            logger.warning("Refresh cookie attempted without any cookie set")
            return

        # 验证当前Cookie格式
        is_valid, validation_error = validate_qq_music_cookie(current_cookie)
        if not is_valid:
            self._set_cookie_validation(FluentIcon.CANCEL, f"当前Cookie格式无效，无法刷新: {validation_error}", "red")
            return

        # 禁用按钮防止重复点击
        self._refresh_cookie_button.setEnabled(False)
        self._refresh_cookie_button.setText(tr("settings_page.refreshing_status"))

        # 显示正在刷新的状态
        self._set_cookie_validation(FluentIcon.SYNC, "正在刷新登录状态...", "blue")

        logger.info(f"[QQMusic] Starting cookie refresh... Cookie: {mask_cookie_for_logging(current_cookie)}")

        try:
            # 调用QQ音乐刷新登录API
            conn = http.client.HTTPSConnection('u.y.qq.com', timeout=15)

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://y.qq.com/',
                'Accept': 'application/json',
                'Cookie': current_cookie,
            }

            refresh_body = json_lib.dumps({
                "comm": {
                    "ct": 24,
                    "cv": 1000000,
                },
                "action": {
                    "method": "RefreshCookie",
                    "module": "music.login.LoginServer",
                    "param": {}
                }
            }, ensure_ascii=False).encode('utf-8')

            conn.request('POST', '/cgi-bin/musicu.fcg', body=refresh_body, headers=headers)
            response = conn.getresponse()
            status = response.status
            raw_data = response.read().decode('utf-8')
            conn.close()

            if status != 200:
                error_msg = f"HTTP请求失败 ({status})"
                self._set_cookie_validation(FluentIcon.CANCEL, error_msg, "red")
                logger.warning(f"[QQMusic] Refresh failed with HTTP {status}")
                return

            try:
                data = json_lib.loads(raw_data)
            except json_lib.JSONDecodeError as e:
                error_msg = f"响应解析失败: {str(e)}"
                self._set_cookie_validation(FluentIcon.CANCEL, error_msg, "red")
                logger.error(f"[QQMusic] Failed to parse refresh response: {e}")
                return

            api_code = data.get('code', -1)

            if api_code == 0:
                success_msg = "登录状态已刷新，有效期延长"
                self._set_cookie_validation(FluentIcon.ACCEPT, success_msg, "green")
                logger.info("[QQMusic] Cookie refreshed successfully")
                
            elif api_code == 301 or api_code == 100020:
                # Cookie已过期或失效 - 显示引导对话框 (2026-05-05 新增)
                error_msg = "Cookie已过期或失效"
                self._set_cookie_validation(FluentIcon.CANCEL, error_msg, "orange")
                logger.warning("[QQMusic] Cookie expired or invalid during refresh")
                
                # 弹出引导对话框，帮助用户重新获取Cookie
                try:
                    show_cookie_expired_dialog(parent=self.window())
                    logger.info("[QQMusic] Cookie expired dialog shown to user")
                except Exception as dialog_error:
                    logger.error(f"[QQMusic] Failed to show cookie expired dialog: {dialog_error}")
                
            else:
                error_detail = data.get('msg', f'未知错误 (code={api_code})')
                error_msg = f"刷新失败: {error_detail}"
                self._set_cookie_validation(FluentIcon.CANCEL, error_msg, "red")
                logger.warning(f"[QQMusic] Refresh API returned error: {api_code} - {error_detail}")

        except Exception as e:
            error_msg = f"网络异常: {type(e).__name__}"
            self._set_cookie_validation(FluentIcon.CANCEL, error_msg, "red")
            logger.error(f"[QQMusic] Exception during cookie refresh: {e}", exc_info=True)

        finally:
            self._refresh_cookie_button.setEnabled(True)
            self._refresh_cookie_button.setText(tr("settings_page.refresh_cookie_button"))

    def refresh_texts(self) -> None:
        """
        刷新页面文本

        当语言切换时调用此方法，更新所有 UI 文本为当前语言的翻译。
        需要重新设置标签和下拉框选项的文本内容，包括搜索源相关组件。
        """
        # 保存当前选中状态
        lang_idx = self._language_combo.currentIndex()
        theme_idx = self._theme_combo.currentIndex()
        current_sources = config.search_sources
        netease_type_idx = self._netease_type_combo.currentIndex()
        keyword_mode_idx = self._keyword_mode_combo.currentIndex()
        radio_checked = self._radio_switch.isChecked()
        qq_music_cookie_text = self._qq_music_cookie_edit.toPlainText()  # 新增 (2026-05-05)

        # 更新标题和分组标题
        self._title_label.setText(tr("settings_page.title"))
        self._general_section.setText(tr("settings_page.general_section"))
        self._search_section.setText(tr("settings_page.search_settings_section"))

        # 更新常规设置标签
        self._language_label.setText(tr("settings_page.language_label"))
        self._theme_label.setText(tr("settings_page.theme_label"))

        # 更新搜索设置标签
        self._engine_label.setText(tr("settings_page.engine_label"))
        self._supplement_label.setText(tr("settings_page.supplement_label"))
        self._keyword_mode_label.setText(tr("settings_page.keyword_mode_label"))
        self._netease_type_label.setText(tr("settings_page.netease_type_label"))
        self._radio_label.setText(tr("settings_page.include_radio_label"))

        # 更新QQ音乐Cookie相关标签 (2026-05-05 新增)
        self._qq_music_cookie_label.setText(tr("settings_page.qq_music_cookie_label"))
        self._qq_music_cookie_edit.setPlaceholderText(tr("settings_page.qq_music_cookie_placeholder"))
        self._qq_music_cookie_edit.setToolTip(tr("settings_page.qq_music_cookie_tooltip"))

        # 更新刷新按钮文本 (2026-05-05 新增)
        self._refresh_cookie_button.setText(tr("settings_page.refresh_cookie_button"))
        self._refresh_cookie_button.setToolTip(tr("settings_page.refresh_cookie_tooltip"))

        # 阻止信号触发
        self._language_combo.blockSignals(True)
        self._theme_combo.blockSignals(True)
        for cb in self._source_checkboxes.values():
            cb.blockSignals(True)
        self._keyword_mode_combo.blockSignals(True)
        self._netease_type_combo.blockSignals(True)
        self._radio_switch.blockSignals(True)

        # 清空并重新填充语言下拉框
        self._language_combo.clear()
        self._language_combo.addItems([tr("settings_page.languages.zh"), tr("settings_page.languages.en")])
        self._language_combo.setCurrentIndex(lang_idx)

        # 清空并重新填充主题下拉框
        self._theme_combo.clear()
        self._theme_combo.addItems([
            tr("settings_page.themes.light"),
            tr("settings_page.themes.dark"),
            tr("settings_page.themes.auto")
        ])
        self._theme_combo.setCurrentIndex(theme_idx)

        # 更新搜索源 CheckBox 文本并恢复选中状态
        all_sources = ["acoustid", "shazam", "netease", "kugou", "qqmusic"]
        for source_key in all_sources:
            cb = self._source_checkboxes[source_key]
            cb.setText(tr(f"settings_page.sources.{source_key}"))
            cb.setChecked(source_key in current_sources)
        
        # 清空并重新填充网易云搜索类型下拉框
        self._netease_type_combo.clear()
        for type_value, _type_name in AppConfig.NETEASE_SEARCH_TYPES.items():
            translated_name = tr(f"settings_page.netease_types.{type_value}")
            self._netease_type_combo.addItem(translated_name, userData=type_value)
        self._netease_type_combo.setCurrentIndex(netease_type_idx)
        
        # 清空并重新填充搜索关键词模式下拉框
        self._keyword_mode_combo.clear()
        for mode_value in AppConfig.VALID_KEYWORD_MODES:
            translated_name = tr(f"settings_page.keyword_modes.{mode_value}")
            self._keyword_mode_combo.addItem(translated_name, userData=mode_value)
        self._keyword_mode_combo.setCurrentIndex(keyword_mode_idx)
        
        # 恢复电台开关状态
        self._radio_switch.setChecked(radio_checked)

        # 恢复QQ音乐Cookie文本 (2026-05-05 新增)
        self._qq_music_cookie_edit.setPlainText(qq_music_cookie_text)

        # 恢复信号连接
        self._language_combo.blockSignals(False)
        self._theme_combo.blockSignals(False)
        for cb in self._source_checkboxes.values():
            cb.blockSignals(False)
        self._netease_type_combo.blockSignals(False)
        self._keyword_mode_combo.blockSignals(False)
        self._radio_switch.blockSignals(False)

        self._ensure_at_least_one_engine_checked()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """
        事件过滤器

        监听 ComboBox 的 Show 事件，在弹出下拉框时修复透明边框问题。
        通过设置弹出窗口为无边框、无阴影来消除额外的边框效果。

        Args:
            obj (QObject): 事件源对象
            event (QEvent): 事件对象

        Returns:
            bool: 是否拦截事件
        """
        if event.type() == QEvent.Type.Show and obj in (
            self._language_combo,
            self._theme_combo,
            self._keyword_mode_combo,
            self._netease_type_combo
        ):
            try:
                popup = obj.view().window()
                if popup and popup != obj:
                    flags = Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
                    popup.setWindowFlags(flags)
                    popup.setAttribute(
                        Qt.WidgetAttribute.WA_TranslucentBackground,
                        True
                    )
            except Exception:
                pass

        return super().eventFilter(obj, event)
