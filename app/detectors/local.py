"""本地离线检测：OpenCV YuNet（ONNX），模型首次使用时下载。"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Final
from urllib.error import URLError
from urllib.request import urlopen

import cv2

from app.detectors.base import DetectorError
from app.frames import Frame, fit_width

MODEL_URL: Final[str] = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
)
SCORE_THRESHOLD: Final[float] = 0.6
NMS_THRESHOLD: Final[float] = 0.3
TOP_K: Final[int] = 5000
DETECT_MAX_WIDTH: Final[int] = 640
DOWNLOAD_TIMEOUT_S: Final[float] = 60.0

logger = logging.getLogger(__name__)


class LocalDetector:
    """YuNet 只做前向推理，无需联网、不上传画面。"""

    name = "local:yunet"

    def __init__(self, model_path: Path) -> None:
        self._model_path = model_path
        self._detector: cv2.FaceDetectorYN | None = None
        self._input_size: tuple[int, int] | None = None

    def detect(self, frame: Frame) -> int:
        detector = self._ensure_detector()
        prepared = fit_width(frame, DETECT_MAX_WIDTH)
        height, width = prepared.shape[:2]
        if self._input_size != (width, height):
            detector.setInputSize((width, height))
            self._input_size = (width, height)
        _, faces = detector.detect(prepared)
        return 0 if faces is None else len(faces)

    def _ensure_detector(self) -> cv2.FaceDetectorYN:
        if self._detector is not None:
            return self._detector
        ensure_model_file(self._model_path)
        logger.info("加载 YuNet 模型：%s", self._model_path)
        self._detector = cv2.FaceDetectorYN.create(
            str(self._model_path),
            "",
            (DETECT_MAX_WIDTH, DETECT_MAX_WIDTH),
            SCORE_THRESHOLD,
            NMS_THRESHOLD,
            TOP_K,
        )
        return self._detector


def ensure_model_file(path: Path) -> Path:
    """模型缺失时下载到 path；下载失败给出可执行的补救提示。"""
    if path.is_file():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("模型缺失，开始下载：%s", MODEL_URL)
    partial = path.with_name(f"{path.name}.part")
    try:
        with urlopen(MODEL_URL, timeout=DOWNLOAD_TIMEOUT_S) as response, partial.open("wb") as handle:
            shutil.copyfileobj(response, handle)
    except (URLError, OSError) as exc:
        partial.unlink(missing_ok=True)
        raise DetectorError(f"YuNet 模型下载失败，请手动下载 {MODEL_URL} 到 {path}") from exc
    partial.replace(path)
    logger.info("模型下载完成：%s（%d 字节）", path, path.stat().st_size)
    return path
