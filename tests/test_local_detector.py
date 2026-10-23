from __future__ import annotations

from pathlib import Path
from urllib.error import URLError

import pytest

from app.detectors import local
from app.detectors.base import DetectorError


def test_existing_model_is_reused(tmp_path: Path) -> None:
    model = tmp_path / "yunet.onnx"
    model.write_bytes(b"stub")
    assert local.ensure_model_file(model) == model


def test_download_failure_cleans_partial_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    model = tmp_path / "models" / "yunet.onnx"

    def boom(*args: object, **kwargs: object) -> None:
        raise URLError("network down")

    monkeypatch.setattr(local, "urlopen", boom)
    with pytest.raises(DetectorError, match="模型下载失败"):
        local.ensure_model_file(model)
    assert not (tmp_path / "models" / "yunet.onnx.part").exists()
