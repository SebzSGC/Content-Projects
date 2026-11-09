"""Encoder chain per platform: Windows/Linux keep NVENC -> libx264; macOS uses VideoToolbox -> libx264."""

from __future__ import annotations

import sys

import pytest
import clipsrender.runner as runner
from clipsrender import LocalFfmpegRenderBackend, libx264_encoder_args, nvenc_encoder_args, videotoolbox_encoder_args


@pytest.mark.parametrize("quality", ["draft", "final"])
def test_windows_and_linux_chain_is_unchanged(monkeypatch, quality) -> None:
    monkeypatch.setattr(runner, "videotoolbox_available", lambda: False)
    backend = LocalFfmpegRenderBackend(use_nvenc=True)
    assert backend.encoder_chain(quality) == [nvenc_encoder_args(quality), libx264_encoder_args(quality)]
    assert LocalFfmpegRenderBackend(use_nvenc=False).encoder_chain(quality) == [libx264_encoder_args(quality)]


@pytest.mark.parametrize("quality", ["draft", "final"])
def test_macos_chain_uses_videotoolbox_before_libx264(monkeypatch, quality) -> None:
    monkeypatch.setattr(runner, "videotoolbox_available", lambda: True)
    assert LocalFfmpegRenderBackend(use_nvenc=False).encoder_chain(quality) == [
        videotoolbox_encoder_args(quality),
        libx264_encoder_args(quality),
    ]
    # NVENC enabled on a Mac (default .env): it fails and the chain continues to VideoToolbox
    assert LocalFfmpegRenderBackend(use_nvenc=True).encoder_chain(quality)[1:] == [
        videotoolbox_encoder_args(quality),
        libx264_encoder_args(quality),
    ]
    # CLIPS_VIDEOTOOLBOX=false keeps libx264
    assert LocalFfmpegRenderBackend(use_nvenc=False, use_videotoolbox=False).encoder_chain(quality) == [
        libx264_encoder_args(quality)
    ]


def test_videotoolbox_is_never_used_outside_macos(monkeypatch) -> None:
    runner.videotoolbox_available.cache_clear()
    monkeypatch.setattr(runner.sys, "platform", "win32")
    try:
        assert runner.videotoolbox_available() is False
    finally:
        runner.videotoolbox_available.cache_clear()


@pytest.mark.skipif(sys.platform != "darwin", reason="VideoToolbox solo existe en macOS")
def test_videotoolbox_detected_on_this_mac() -> None:
    runner.videotoolbox_available.cache_clear()
    assert runner.videotoolbox_available() is True
