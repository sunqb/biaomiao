# -*- coding: utf-8 -*-
import argparse
import base64
import configparser
import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


CONFIG_FILE = Path(
    os.getenv("BAIMIAO_CONFIG_PATH", str(Path(__file__).with_name("config.ini")))
)
CONFIG_SECTION = "default"
BAIMIAO_URL = "https://web.baimiaoapp.com"
REQUEST_TIMEOUT = 15
OCR_TIMEOUT = 60
POLL_INTERVAL = 0.2
ENV_CONFIG_MAP = {
    "BAIMIAO_USERNAME": "username",
    "BAIMIAO_PASSWORD": "password",
    "BAIMIAO_UUID": "uuid",
    "BAIMIAO_LOGIN_TOKEN": "login_token",
    "BAIMIAO_REQUEST_TIMEOUT": "request_timeout",
    "BAIMIAO_OCR_TIMEOUT": "ocr_timeout",
    "BAIMIAO_POLL_INTERVAL": "poll_interval",
}


class BaimiaoOCR:
    def __init__(self, config_path: Path = CONFIG_FILE):
        self.config_path = config_path
        self.config = self._load_config(config_path)
        default_config = dict(self.config.items(CONFIG_SECTION))

        self.username = default_config.get("username", "")
        self.password = default_config.get("password", "")
        self.uuid = default_config.get("uuid", "")
        self.login_token = default_config.get("login_token", "")
        self.request_timeout = int(
            default_config.get("request_timeout", REQUEST_TIMEOUT)
        )
        self.ocr_timeout = int(default_config.get("ocr_timeout", OCR_TIMEOUT))
        self.poll_interval = float(default_config.get("poll_interval", POLL_INTERVAL))

        self.session = requests.Session()
        self.headers = {
            "Host": "web.baimiaoapp.com",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Content-Type": "application/json;charset=utf-8",
            "X-AUTH-TOKEN": self.login_token,
            "X-AUTH-UUID": self.uuid,
            "Origin": BAIMIAO_URL,
            "Referer": f"{BAIMIAO_URL}/",
        }

    @staticmethod
    def _load_config(config_path: Path) -> configparser.ConfigParser:
        config = configparser.ConfigParser()
        config.read(config_path, encoding="utf-8")

        if not config.has_section(CONFIG_SECTION):
            config.add_section(CONFIG_SECTION)

        # Backward compatibility for the old [defaults] section.
        if config.has_section("defaults"):
            for key, value in config.items("defaults"):
                if not config.has_option(CONFIG_SECTION, key):
                    config.set(CONFIG_SECTION, key, value)

        for env_name, config_key in ENV_CONFIG_MAP.items():
            env_value = os.getenv(env_name)
            if env_value is not None:
                config.set(CONFIG_SECTION, config_key, env_value)

        return config

    def _save_config(self) -> None:
        try:
            with self.config_path.open("w", encoding="utf-8") as file:
                self.config.write(file)
        except OSError:
            pass  # 容器只读文件系统时忽略，token 已保留在内存

    def _set_config(self, key: str, value: str) -> None:
        self.config.set(CONFIG_SECTION, key, value)

    def _request(self, method: str, path: str, **kwargs: Any) -> Dict[str, Any]:
        url = f"{BAIMIAO_URL}{path}"
        kwargs.setdefault("timeout", self.request_timeout)
        response = self.session.request(method, url, **kwargs)
        if not response.ok:
            raise RuntimeError(
                f"Http Request Error\nHttp Status: {response.status_code}\n{response.text}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError(f"Invalid JSON response: {response.text}") from exc

    def login(self) -> None:
        if not self.username or not self.password:
            raise RuntimeError("username/password is required in config.ini")

        self.uuid = str(uuid.uuid4())
        self._set_config("uuid", self.uuid)

        login_headers = self.headers.copy()
        login_headers["X-AUTH-TOKEN"] = ""
        login_headers["X-AUTH-UUID"] = self.uuid
        login_type = "mobile" if self.username.isdigit() else "email"
        data = {
            "username": self.username,
            "password": self.password,
            "type": login_type,
        }

        result = self._request(
            "POST", "/api/user/login", headers=login_headers, json=data
        )
        token = result.get("data", {}).get("token")
        if not token:
            raise RuntimeError(json.dumps(result, ensure_ascii=False))

        self.login_token = token
        self._set_config("login_token", self.login_token)
        self.headers["X-AUTH-UUID"] = self.uuid
        self.headers["X-AUTH-TOKEN"] = self.login_token
        self._save_config()

    def _ensure_token(self) -> None:
        """确保有有效的登录 token，没有则登录。有 token 直接复用，不做额外网络请求。"""
        if not self.uuid or not self.login_token:
            self.login()
            return
        self.headers["X-AUTH-UUID"] = self.uuid
        self.headers["X-AUTH-TOKEN"] = self.login_token

    def _get_single_permission(self) -> tuple[str, str]:
        result = self._request(
            "POST", "/api/perm/single", headers=self.headers, json={"mode": "single"}
        )
        data = result.get("data", {})
        engine = data.get("engine")
        token = data.get("token")
        if not engine or not token:
            raise RuntimeError(
                "已经达到今日识别上限，请前往白描手机端开通会员或明天再试"
            )
        return engine, token

    @staticmethod
    def _normalize_base64_image(image: str, mime_type: str) -> tuple[str, str]:
        if image.startswith("data:"):
            prefix, payload = image.split(",", 1)
            detected_mime = prefix.removeprefix("data:").split(";", 1)[0] or mime_type
            return payload, detected_mime
        return image, mime_type

    def _oss_upload(self, raw_bytes: bytes, mime_type: str) -> str:
        """上传原始图片字节到阿里云 OSS，返回 file_key。"""
        resp = self.session.get(
            f"{BAIMIAO_URL}/api/oss/sign",
            headers=self.headers,
            params={"mime_type": mime_type},
            timeout=self.request_timeout,
        )
        if not resp.ok:
            raise RuntimeError(f"OSS sign failed: {resp.status_code}")
        sign = resp.json().get("data", {}).get("result", {})

        form = {
            "success_action_status": "200",
            "policy": sign["policy"],
            "x-oss-signature": sign["signature"],
            "x-oss-signature-version": sign["x_oss_signature_version"],
            "x-oss-credential": sign["x_oss_credential"],
            "x-oss-date": sign["x_oss_date"],
            "key": sign["file_key"],
            "x-oss-security-token": sign["security_token"],
        }
        ext = mime_type.split("/")[-1]
        oss_timeout = max(self.request_timeout, 60)  # OSS 上传大图需要更长超时
        oss_resp = self.session.post(
            sign["host"],
            data=form,
            files={"file": (f"image.{ext}", raw_bytes, mime_type)},
            timeout=oss_timeout,
        )
        if oss_resp.status_code != 200:
            raise RuntimeError(f"OSS upload failed: {oss_resp.status_code}")
        return sign["file_key"]

    def recognize(
        self,
        base64_image: str,
        filename: str = "image.png",
        mime_type: str = "image/png",
        size: int = 0,
    ) -> str:
        self._ensure_token()
        engine, token = self._get_single_permission()
        image_payload, detected_mime = self._normalize_base64_image(
            base64_image, mime_type
        )
        raw_bytes = base64.b64decode(image_payload)
        hash_value = hashlib.md5(raw_bytes).hexdigest()
        actual_size = size if size > 0 else len(image_payload)

        # plus 引擎需要先上传到 OSS，获取 fileKey
        file_key = self._oss_upload(raw_bytes, detected_mime)

        image_data_url = f"data:{detected_mime};base64,{image_payload}"
        data = {
            "batchId": "",
            "total": 1,
            "token": token,
            "hash": hash_value,
            "name": filename,
            "size": actual_size,
            "dataUrl": image_data_url,
            "fileKey": file_key,
            "result": {},
            "status": "processing",
            "isSuccess": False,
        }
        result = self._request(
            "POST", f"/api/ocr/image/{engine}", headers=self.headers, json=data
        )
        job_status_id = result.get("data", {}).get("jobStatusId")
        if not job_status_id:
            raise RuntimeError(json.dumps(result, ensure_ascii=False))

        deadline = time.monotonic() + self.ocr_timeout
        while time.monotonic() < deadline:
            time.sleep(self.poll_interval)
            params = {"jobStatusId": job_status_id}
            result = self._request(
                "GET",
                f"/api/ocr/image/{engine}/status",
                headers=self.headers,
                params=params,
            )
            data = result.get("data", {})
            if not data.get("isEnded"):
                continue

            words_result = data.get("ydResp", {}).get("words_result", [])
            return "\n".join(
                item.get("words", "") for item in words_result if item.get("words")
            )

        raise TimeoutError(f"OCR timeout after {self.ocr_timeout}s")


class OcrRequest(BaseModel):
    image: str = Field(default="", description="Base64 image payload or data URL")
    url: str = Field(default="", description="Image URL (http/https)")
    filename: str = "image.png"
    mime_type: str = "image/png"

    def get_image_data(self) -> tuple[str, str, int]:
        """Returns (base64_payload, filename, base64_length)"""
        raw_url = (self.url or "").strip()
        raw_image = (self.image or "").strip()

        # Normalize: if image field contains a URL, treat it as url
        target_url = raw_url or (
            raw_image if raw_image.startswith(("http://", "https://")) else ""
        )
        if target_url:
            try:
                resp = requests.get(target_url, timeout=REQUEST_TIMEOUT)
                resp.raise_for_status()
                raw_bytes = resp.content
                payload = base64.b64encode(raw_bytes).decode("utf-8")
                fname = self.filename
                if fname == "image.png":
                    fname = Path(target_url.split("?")[0]).name or "image.png"
                # size should be base64 string length (same as original ocr.bak)
                return payload, fname, len(payload)
            except Exception as exc:
                raise RuntimeError(f"Failed to download image from URL: {exc}") from exc
        elif raw_image:
            if raw_image.startswith("data:"):
                prefix, payload = raw_image.split(",", 1)
                return payload, self.filename, len(payload)
            return raw_image, self.filename, len(raw_image)
        else:
            raise RuntimeError("Either 'image' (base64) or 'url' must be provided")


class OcrResponse(BaseModel):
    text: str


app = FastAPI(title="Baimiao OCR API", version="1.0.0")
_ocr_instance: BaimiaoOCR | None = None


def get_ocr_instance() -> BaimiaoOCR:
    global _ocr_instance
    if _ocr_instance is None:
        _ocr_instance = BaimiaoOCR()
    return _ocr_instance


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/ocr", response_model=OcrResponse)
def ocr(request: OcrRequest) -> OcrResponse:
    try:
        image_payload, filename, size = request.get_image_data()
        text = get_ocr_instance().recognize(
            image_payload, filename, request.mime_type, size=size
        )
        return OcrResponse(text=text)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def image_file_to_base64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Baimiao OCR client")
    parser.add_argument("image", type=Path, help="image file path")
    parser.add_argument("--mime-type", default="image/png")
    args = parser.parse_args()

    recognized_text = BaimiaoOCR().recognize(
        image_file_to_base64(args.image),
        filename=args.image.name,
        mime_type=args.mime_type,
    )
    print(recognized_text)


if __name__ == "__main__":
    main()
