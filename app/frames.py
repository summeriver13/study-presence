"""帧的几何与编码工具，所有后端共用。"""

from __future__ import annotations

import base64
from typing import Final

import cv2
import numpy as np

Frame = np.ndarray

DEFAULT_JPEG_QUALITY: Final[int] = 90


class FrameError(RuntimeError):
    """帧为空或编码失败。"""


def fit_width(frame: Frame, max_width: int) -> Frame:
    """保持宽高比把宽缩到 max_width 以内；已足够小则原样返回。"""
    height, width = frame.shape[:2]
    if width <= max_width:
        return frame
    scale = max_width / width
    return cv2.resize(frame, (max_width, max(1, round(height * scale))), interpolation=cv2.INTER_AREA)


def fit_box(frame: Frame, max_width: int, max_height: int) -> Frame:
    """等比缩放到 max_width × max_height 的框内。"""
    height, width = frame.shape[:2]
    scale = min(max_width / width, max_height / height, 1.0)
    if scale == 1.0:
        return frame
    size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return cv2.resize(frame, size, interpolation=cv2.INTER_AREA)


def to_rgb(frame: Frame) -> Frame:
    """BGR（OpenCV 原生）转 RGB（Tk / PIL 需要）。"""
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)


def encode_jpeg_base64(frame: Frame, quality: int = DEFAULT_JPEG_QUALITY) -> str:
    """编码为 base64 JPEG 字符串，供云端 API 使用。"""
    ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise FrameError("JPEG 编码失败")
    return base64.b64encode(buffer.tobytes()).decode("ascii")
