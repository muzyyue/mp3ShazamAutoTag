# -*- coding: utf-8 -*-
"""
ID3 版本 Windows 兼容性回归测试

背景: Windows 资源管理器/Media Foundation 的 MP3 封面缩略图只解析 ID3v2.3 的 APIC 帧,
而 eyed3 0.9.9 默认写 ID3v2.4, 导致"先转换后嵌元数据"的 mp3 在资源管理器中无法预览封面。

本测试锁定所有 MP3 标签写入路径必须产出 ID3v2.3。
"""

import logging
import shutil

import eyed3
import pytest
from mutagen.id3 import ID3

from auto_tag.audio_recognize._tags import update_mp3_tags
from auto_tag.converter.metadata_manager import MetadataManager
from auto_tag.lyric.lyric_embedder import LyricEmbedder

# 复用项目内现有测试音频作为样本
FIXTURE_MP3 = "tests/fixtures/song/Lush_Meadows - Cloud_Catcher - Mountain_Morning.mp3"

JPEG_HEADER = b"\xff\xd8\xff\xe0" + b"\x00" * 64


@pytest.fixture
def mp3_copy(tmp_path):
    """将 fixture mp3 复制到临时目录并返回路径"""
    target = tmp_path / "sample.mp3"
    shutil.copy(FIXTURE_MP3, target)
    return str(target)


def _read_id3_version(path):
    """读取文件实际写入的 ID3 版本"""
    return ID3(path).version


def test_update_mp3_tags_writes_v23(mp3_copy):
    """eyed3 写文本标签后必须是 ID3v2.3 (Windows 兼容)"""
    update_mp3_tags(
        mp3_copy, "标题", "艺术家", "专辑", year="2024", genre="Pop"
    )
    assert _read_id3_version(mp3_copy) == (2, 3, 0)


def test_metadata_manager_write_mp3_writes_v23(mp3_copy):
    """MetadataManager 写 MP3 元数据后必须是 ID3v2.3"""
    mgr = MetadataManager()
    ok = mgr.write_metadata(
        mp3_copy, {"title": "T", "artist": "A", "album": "B", "year": 2024}
    )
    assert ok
    assert _read_id3_version(mp3_copy) == (2, 3, 0)


def test_metadata_manager_set_mp3_cover_writes_v23(mp3_copy):
    """MetadataManager 设置 MP3 封面后必须是 ID3v2.3 (Windows 预览关键路径)"""
    mgr = MetadataManager()
    ok = mgr.set_cover(mp3_copy, JPEG_HEADER)
    assert ok
    version = _read_id3_version(mp3_copy)
    assert version == (2, 3, 0)
    # 封面帧必须存在
    tags = ID3(mp3_copy)
    apic = [k for k in tags.keys() if k.startswith("APIC")]
    assert apic, "APIC 封面帧缺失"


def test_lyric_embedder_mp3_keeps_v23(mp3_copy):
    """歌词嵌入后文件仍保持 ID3v2.3 (mutagen 不得把标签升级为 v2.4)"""
    # 先以 v2.3 写入基础标签, 再嵌歌词
    audio = eyed3.load(mp3_copy)
    if audio.tag is None:
        audio.initTag()
    audio.tag.title = "T"
    audio.tag.save(version=eyed3.id3.ID3_V2_3)
    assert _read_id3_version(mp3_copy) == (2, 3, 0)

    embedder = LyricEmbedder(logging.getLogger("test"))
    ok = embedder.embed_lyrics(mp3_copy, "[00:00.00]第一行\n[00:05.00]第二行", "lrc")
    assert ok
    assert _read_id3_version(mp3_copy) == (2, 3, 0)
