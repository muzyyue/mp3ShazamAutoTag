# -*- coding: utf-8 -*-
"""
音频编辑工作线程模块

提供基于 QThread 的异步音频编辑任务执行，
通过信号机制与主线程通信，实现进度更新和结果传递。

使用示例：
>>> from auto_tag.editor.workers import EditorWorker
>>> from auto_tag.editor.config import EditorConfig
>>> worker = EditorWorker(files=["song1.mp3"], output_dir="output/", config=EditorConfig())
>>> worker.progress_updated.connect(on_progress)
>>> worker.file_edited.connect(on_file_done)
>>> worker.start()
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QThread, Signal

from auto_tag.editor.audio_editor import AudioEditor
from auto_tag.editor.config import EditorConfig

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class EditorWorker(QThread):
    """音频编辑工作线程类"""

    progress_updated = Signal(int, int, str)
    file_edited = Signal(str, bool, str)
    finished_all = Signal(list)
    error_occurred = Signal(str)

    def __init__(
        self,
        files: list[str],
        output_dir: str,
        config: EditorConfig,
        parent=None,
    ) -> None:
        """
        初始化编辑工作线程

        Args:
            files: 要编辑的文件路径列表
            output_dir: 输出目录路径
            config: 编辑配置对象
            parent: 父对象，用于 Qt 对象树管理
        """
        super().__init__(parent)

        self.files = files
        self.output_dir = output_dir
        self.config = config

        self._is_running = True
        self._results: list[dict] = []

        logger.info(f"初始化编辑工作线程，文件数: {len(files)}, 输出目录: {output_dir}")

    def run(self) -> None:
        """主循环：遍历文件列表并逐个处理"""
        logger.info("开始执行音频编辑任务")

        try:
            editor = AudioEditor()
            total_files = len(self.files)

            for index, input_file in enumerate(self.files, start=1):
                if not self._is_running:
                    logger.info("收到停止信号，终止处理")
                    break

                result = self._process_single_file(editor, index, input_file, total_files)
                if result is not None:
                    self._results.append(result)

            logger.info(f"音频编辑任务完成，共处理 {len(self._results)} 个文件")
            self.finished_all.emit(self._results)

        except Exception as e:
            error_msg = f"工作线程发生严重错误: {str(e)}"
            logger.exception(error_msg)
            self.error_occurred.emit(error_msg)

    def _process_single_file(self, editor: AudioEditor, index: int, input_file: str, total_files: int) -> dict | None:
        """处理单个文件的编辑任务"""
        try:
            if not os.path.exists(input_file):
                logger.warning(f"文件不存在，跳过: {input_file}")
                result = {
                    "input_file": input_file,
                    "success": False,
                    "error": "文件不存在",
                    "skipped": True,
                }
                self.file_edited.emit(input_file, False, "文件不存在")
                self.progress_updated.emit(index, total_files, os.path.basename(input_file))
                return result

            filename = Path(input_file).stem
            extension = self._get_output_extension()

            if self.config.overwrite_original:
                temp_dir = os.path.dirname(input_file) or "."
                temp_filename = f".{filename}_editing_temp_{int(time.time())}{extension}"
                output_path = os.path.join(temp_dir, temp_filename)
                is_overwrite_mode = True
            else:
                output_filename = f"{filename}_edited{extension}"
                output_path = os.path.join(self.output_dir, output_filename)
                is_overwrite_mode = False

            logger.info(f"正在处理 [{index}/{total_files}]: {os.path.basename(input_file)}")

            start_time = time.time()
            edit_result = editor.apply_preset(input_file, output_path, self.config)
            processing_time = time.time() - start_time

            success = edit_result.get("success", False)
            error_msg = edit_result.get("error", "") or (
                "" if success else "未知错误"
            )

            if is_overwrite_mode and success:
                try:
                    os.replace(output_path, input_file)
                    output_path = input_file
                    logger.info(f"已覆盖原文件: {input_file}")
                except Exception as replace_error:
                    error_msg = f"替换原文件失败: {str(replace_error)}"
                    success = False
                    if os.path.exists(output_path):
                        os.remove(output_path)
                        logger.warning(f"已清理临时文件: {output_path}")

            result = {
                "input_file": input_file,
                "output_file": output_path,
                "success": success,
                "error": error_msg,
                "processing_time": processing_time,
                "steps_completed": edit_result.get("steps_completed", []),
                "skipped": False,
            }

            self.file_edited.emit(
                input_file,
                success,
                error_msg or ("成功" if success else "处理失败"),
            )
            self.progress_updated.emit(index, total_files, os.path.basename(input_file))

            status = "✓ 成功" if success else "✗ 失败"
            logger.info(
                f"{status} [{index}/{total_files}] "
                f"{os.path.basename(input_file)} ({processing_time:.2f}秒)"
            )

            return result

        except Exception as e:
            error_msg = f"处理异常: {str(e)}"
            logger.exception(f"处理文件异常: {input_file}")

            result = {
                "input_file": input_file,
                "success": False,
                "error": error_msg,
                "skipped": False,
            }
            self.file_edited.emit(input_file, False, error_msg)
            self.progress_updated.emit(index, total_files, os.path.basename(input_file))
            return result

    def stop(self) -> None:
        """设置停止标志，线程会在当前文件处理完成后退出"""
        logger.info("请求停止编辑工作线程")
        self._is_running = False

    def _get_output_extension(self) -> str:
        """根据配置获取输出文件扩展名"""
        format_ext_map = {
            "mp3": ".mp3",
            "flac": ".flac",
            "aac": ".aac",
            "ogg": ".ogg",
            "wav": ".wav",
            "m4a": ".m4a",
        }
        return format_ext_map.get(self.config.output_format.value, ".mp3")
