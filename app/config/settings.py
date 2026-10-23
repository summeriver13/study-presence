"""运行期配置：环境变量 + .env，唯一入口 Settings.from_env()。"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from dotenv import load_dotenv

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
ENV_FILE: Final[Path] = PROJECT_ROOT / ".env"
DEFAULT_DB_PATH: Final[Path] = PROJECT_ROOT / "data" / "presence.db"
DEFAULT_MODEL_PATH: Final[Path] = PROJECT_ROOT / "models" / "face_detection_yunet_2023mar.onnx"

BackendName = Literal["local", "baidu"]
BACKENDS: Final[tuple[BackendName, ...]] = ("local", "baidu")

DEFAULT_CAMERA_INDEX: Final[int] = 0
DEFAULT_DETECT_INTERVAL_S: Final[float] = 2.0
DEFAULT_PRESENT_AFTER_S: Final[float] = 4.0
DEFAULT_ABSENT_AFTER_S: Final[float] = 6.0
DEFAULT_MIN_FACE_AREA_RATIO: Final[float] = 0.02
DEFAULT_ACTIVITY_IDLE_S: Final[float] = 60.0
DEFAULT_TRACK_INPUT: Final[bool] = True
TRUE_WORDS: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on"})
FALSE_WORDS: Final[frozenset[str]] = frozenset({"0", "false", "no", "off"})


class ConfigError(ValueError):
    """配置缺失或取值非法。"""


@dataclass(frozen=True, slots=True)
class Settings:
    backend: BackendName = "local"
    camera_index: int = DEFAULT_CAMERA_INDEX
    source_path: Path | None = None
    detect_interval_s: float = DEFAULT_DETECT_INTERVAL_S
    present_after_s: float = DEFAULT_PRESENT_AFTER_S
    absent_after_s: float = DEFAULT_ABSENT_AFTER_S
    min_face_area_ratio: float = DEFAULT_MIN_FACE_AREA_RATIO
    track_input: bool = DEFAULT_TRACK_INPUT
    activity_idle_s: float = DEFAULT_ACTIVITY_IDLE_S
    db_path: Path = DEFAULT_DB_PATH
    model_path: Path = DEFAULT_MODEL_PATH
    baidu_api_key: str | None = None
    baidu_secret_key: str | None = None

    def __post_init__(self) -> None:
        if self.camera_index < 0:
            raise ConfigError("camera_index 不能为负")
        if not self.detect_interval_s > 0:
            raise ConfigError("detect_interval_s 必须为正数")
        if not self.present_after_s > 0 or not self.absent_after_s > 0:
            raise ConfigError("present_after_s 与 absent_after_s 必须为正数")
        if not 0 <= self.min_face_area_ratio < 1:
            raise ConfigError("min_face_area_ratio 必须落在 [0, 1) 内")
        if not self.activity_idle_s > 0:
            raise ConfigError("activity_idle_s 必须为正数")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        """读取 SP_* 变量；传 env 时跳过 .env，便于测试。"""
        if env is None:
            load_dotenv(ENV_FILE, override=False)
            env = os.environ
        return cls(
            backend=_read_backend(env),
            camera_index=_read_int(env, "SP_CAMERA_INDEX", DEFAULT_CAMERA_INDEX),
            source_path=_read_optional_path(env, "SP_SOURCE"),
            detect_interval_s=_read_float(env, "SP_DETECT_INTERVAL_S", DEFAULT_DETECT_INTERVAL_S),
            present_after_s=_read_float(env, "SP_PRESENT_AFTER_S", DEFAULT_PRESENT_AFTER_S),
            absent_after_s=_read_float(env, "SP_ABSENT_AFTER_S", DEFAULT_ABSENT_AFTER_S),
            min_face_area_ratio=_read_float(env, "SP_MIN_FACE_AREA", DEFAULT_MIN_FACE_AREA_RATIO),
            track_input=_read_bool(env, "SP_TRACK_INPUT", DEFAULT_TRACK_INPUT),
            activity_idle_s=_read_float(env, "SP_ACTIVITY_IDLE_S", DEFAULT_ACTIVITY_IDLE_S),
            db_path=_read_path(env, "SP_DB_PATH", DEFAULT_DB_PATH),
            baidu_api_key=_read_optional(env, "SP_BAIDU_API_KEY"),
            baidu_secret_key=_read_optional(env, "SP_BAIDU_SECRET_KEY"),
        )

    def baidu_credentials(self) -> tuple[str, str]:
        """云端后端所需的密钥对，缺失时立即失败而不是静默降级。"""
        if not self.baidu_api_key or not self.baidu_secret_key:
            raise ConfigError("backend=baidu 需要 SP_BAIDU_API_KEY 与 SP_BAIDU_SECRET_KEY（见 .env.example）")
        return self.baidu_api_key, self.baidu_secret_key


def _read_backend(env: Mapping[str, str]) -> BackendName:
    raw = env.get("SP_BACKEND", "local").strip().lower()
    if raw == "local":
        return "local"
    if raw == "baidu":
        return "baidu"
    raise ConfigError(f"SP_BACKEND 只能是 {BACKENDS}，当前为 {raw!r}")


def _read_int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} 需要整数，当前为 {raw!r}") from exc


def _read_float(env: Mapping[str, str], name: str, default: float) -> float:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} 需要数字，当前为 {raw!r}") from exc


def _read_bool(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(name, "").strip().lower()
    if not raw:
        return default
    if raw in TRUE_WORDS:
        return True
    if raw in FALSE_WORDS:
        return False
    raise ConfigError(f"{name} 需要布尔值（1/0、true/false），当前为 {raw!r}")


def _read_path(env: Mapping[str, str], name: str, default: Path) -> Path:
    raw = env.get(name, "").strip()
    return Path(raw).expanduser() if raw else default


def _read_optional_path(env: Mapping[str, str], name: str) -> Path | None:
    raw = env.get(name, "").strip()
    return Path(raw).expanduser() if raw else None


def _read_optional(env: Mapping[str, str], name: str) -> str | None:
    raw = env.get(name, "").strip()
    return raw or None
