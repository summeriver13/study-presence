"""人脸检测后端工厂。"""

from __future__ import annotations

from app.config.settings import Settings
from app.detectors.baidu import BaiduDetector
from app.detectors.base import Detector, DetectorError
from app.detectors.local import LocalDetector


def build_detector(settings: Settings) -> Detector:
    """按配置选择检测后端；baidu 缺密钥时抛 ConfigError。"""
    if settings.backend == "baidu":
        api_key, secret_key = settings.baidu_credentials()
        return BaiduDetector(api_key, secret_key)
    return LocalDetector(settings.model_path)


__all__ = ["BaiduDetector", "Detector", "DetectorError", "LocalDetector", "build_detector"]
