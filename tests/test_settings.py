from __future__ import annotations

import pytest

from app.config.settings import ConfigError, Settings


def test_defaults_without_env() -> None:
    settings = Settings.from_env({})
    assert settings.backend == "local"
    assert settings.camera_index == 0
    assert settings.detect_interval_s == pytest.approx(2.0)
    assert settings.present_after_s == pytest.approx(4.0)
    assert settings.absent_after_s == pytest.approx(6.0)
    assert settings.min_face_area_ratio == pytest.approx(0.02)
    assert settings.track_input is True
    assert settings.activity_idle_s == pytest.approx(60.0)
    assert settings.baidu_api_key is None


def test_env_overrides_are_parsed() -> None:
    settings = Settings.from_env(
        {
            "SP_CAMERA_INDEX": "2",
            "SP_DETECT_INTERVAL_S": "0.5",
            "SP_PRESENT_AFTER_S": "2.5",
            "SP_ABSENT_AFTER_S": "7",
            "SP_MIN_FACE_AREA": "0.05",
            "SP_TRACK_INPUT": "off",
            "SP_ACTIVITY_IDLE_S": "30",
        }
    )
    assert settings.camera_index == 2
    assert settings.detect_interval_s == pytest.approx(0.5)
    assert settings.present_after_s == pytest.approx(2.5)
    assert settings.absent_after_s == pytest.approx(7.0)
    assert settings.min_face_area_ratio == pytest.approx(0.05)
    assert settings.track_input is False
    assert settings.activity_idle_s == pytest.approx(30.0)


def test_db_path_is_configurable() -> None:
    settings = Settings.from_env({"SP_DB_PATH": "./tmp/custom.db"})
    assert settings.db_path.name == "custom.db"
    assert settings.db_path.parent.name == "tmp"


def test_db_path_falls_back_to_default() -> None:
    assert Settings.from_env({}).db_path.name == "presence.db"


def test_baidu_backend_requires_credentials() -> None:
    settings = Settings.from_env({"SP_BACKEND": "baidu"})
    with pytest.raises(ConfigError, match="SP_BAIDU_API_KEY"):
        settings.baidu_credentials()


def test_baidu_credentials_returned_when_present() -> None:
    settings = Settings.from_env(
        {"SP_BACKEND": "baidu", "SP_BAIDU_API_KEY": "ak", "SP_BAIDU_SECRET_KEY": "sk"}
    )
    assert settings.baidu_credentials() == ("ak", "sk")


@pytest.mark.parametrize("raw", ["cuda", "", "Local "])
def test_invalid_backend_rejected(raw: str) -> None:
    if raw.strip().lower() == "local":
        assert Settings.from_env({"SP_BACKEND": raw}).backend == "local"
        return
    with pytest.raises(ConfigError, match="SP_BACKEND"):
        Settings.from_env({"SP_BACKEND": raw})


@pytest.mark.parametrize(
    ("name", "value"),
    [("SP_CAMERA_INDEX", "abc"), ("SP_DETECT_INTERVAL_S", "fast"), ("SP_PRESENT_AFTER_S", "soon")],
)
def test_invalid_numbers_rejected(name: str, value: str) -> None:
    with pytest.raises(ConfigError, match=name):
        Settings.from_env({name: value})


def test_invalid_boolean_rejected() -> None:
    with pytest.raises(ConfigError, match="SP_TRACK_INPUT"):
        Settings.from_env({"SP_TRACK_INPUT": "maybe"})


@pytest.mark.parametrize(
    "kwargs",
    [
        {"camera_index": -1},
        {"detect_interval_s": 0.0},
        {"present_after_s": 0.0},
        {"absent_after_s": 0.0},
        {"min_face_area_ratio": 1.0},
        {"activity_idle_s": 0.0},
    ],
)
def test_post_init_validates(kwargs: dict[str, object]) -> None:
    with pytest.raises(ConfigError):
        Settings(**kwargs)  # type: ignore[arg-type]
