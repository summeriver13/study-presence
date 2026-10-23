"""百度云人脸检测后端：token 缓存 + 失效重取，密钥只从配置读。"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Final

import requests

from app.detectors.base import DetectorError
from app.frames import Frame, encode_jpeg_base64, fit_width

TOKEN_URL: Final[str] = "https://aip.baidubce.com/oauth/2.0/token"
DETECT_URL: Final[str] = "https://aip.baidubce.com/rest/2.0/face/v3/detect"
TOKEN_INVALID_CODES: Final[frozenset[int]] = frozenset({110, 111})
TOKEN_EXPIRY_MARGIN_S: Final[float] = 60.0
DEFAULT_TIMEOUT_S: Final[float] = 8.0
CLOUD_MAX_WIDTH: Final[int] = 1024
MAX_FACE_NUM: Final[int] = 5
SUCCESS_CODE: Final[int] = 0


class BaiduDetector:
    name = "baidu:detect"

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        session: requests.Session | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._api_key = api_key
        self._secret_key = secret_key
        self._timeout_s = timeout_s
        self._session = session or requests.Session()
        self._clock = clock
        self._token: str | None = None
        self._token_expires_at = 0.0

    def detect(self, frame: Frame) -> int:
        image = encode_jpeg_base64(fit_width(frame, CLOUD_MAX_WIDTH))
        return self._request_face_count(image, allow_refresh=True)

    def _request_face_count(self, image: str, *, allow_refresh: bool) -> int:
        token = self._access_token()
        payload = {"image": image, "image_type": "BASE64", "max_face_num": MAX_FACE_NUM}
        try:
            response = self._session.post(
                DETECT_URL, params={"access_token": token}, json=payload, timeout=self._timeout_s
            )
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise DetectorError(f"百度云请求失败：{exc}") from exc

        code = int(data.get("error_code", SUCCESS_CODE))
        if code in TOKEN_INVALID_CODES and allow_refresh:
            self._token = None
            return self._request_face_count(image, allow_refresh=False)
        if code != SUCCESS_CODE:
            raise DetectorError(f"百度云返回错误 {code}：{data.get('error_msg', '未知错误')}")
        return int(data["result"]["face_num"])

    def _access_token(self) -> str:
        if self._token is not None and self._clock() < self._token_expires_at:
            return self._token
        payload = {
            "grant_type": "client_credentials",
            "client_id": self._api_key,
            "client_secret": self._secret_key,
        }
        try:
            response = self._session.post(TOKEN_URL, data=payload, timeout=self._timeout_s)
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise DetectorError(f"百度云鉴权请求失败：{exc}") from exc
        token = data.get("access_token")
        if not token:
            raise DetectorError(
                f"百度云鉴权失败：{data.get('error_description', data.get('error', '未知错误'))}"
            )
        expires_in = float(data.get("expires_in", 0))
        self._token = str(token)
        self._token_expires_at = self._clock() + max(0.0, expires_in - TOKEN_EXPIRY_MARGIN_S)
        return self._token
