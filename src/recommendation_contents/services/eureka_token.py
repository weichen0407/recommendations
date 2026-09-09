"""Eureka access-token checking and refresh scaffolding."""

from __future__ import annotations

import base64
import binascii
import json
import re
import shlex
import subprocess
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from recommendation_contents.config import EurekaSettings

DEFAULT_REFRESH_HEADERS = {
    "accept": "application/json",
    "accept-language": "zh-CN,zh;q=0.9",
    "content-type": "application/json",
    "origin": "https://eureka.patsnap.com",
    "referer": "https://eureka.patsnap.com/",
    "x-requested-with": "XMLHttpRequest",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
    ),
}


@dataclass(frozen=True)
class TokenCheckResult:
    status: str
    reason: str
    authorization: str = ""
    refresh_available: bool = False
    source: str = ""
    signature_id: str = ""
    site_lang: str = ""
    cookie: str = ""


@dataclass(frozen=True)
class TokenRefreshResult:
    success: bool
    status: str
    reason: str
    authorization: str = ""


@dataclass(frozen=True)
class ImportedCurlAuth:
    authorization: str = ""
    signature_id: str = ""
    site_lang: str = ""
    cookie: str = ""
    source_url: str = ""
    expires_at: float | None = None


class EurekaTokenManager:
    def __init__(self, settings: EurekaSettings) -> None:
        self.settings = settings

    def check_token(self) -> TokenCheckResult:
        if self.settings.token_check_mode == "disabled":
            return TokenCheckResult(status="skipped", reason="token check is disabled")

        record = self._read_cached_record()
        cached_authorization = _authorization_from_record(record)
        cached_token_is_ready = bool(cached_authorization and not self._is_expired(record))

        if cached_token_is_ready:
            return TokenCheckResult(
                status="ready",
                reason="valid token loaded from cache",
                authorization=cached_authorization,
                refresh_available=self.refresh_available(),
                source="cache",
                **_cached_request_context(record),
            )

        if self.settings.authorization:
            if _authorization_is_expired(
                self.settings.authorization,
                self.settings.token_expiry_skew_seconds,
            ):
                return TokenCheckResult(
                    status="needs_refresh" if self.refresh_available() else "expired",
                    reason="authorization configured on settings is expired",
                    refresh_available=self.refresh_available(),
                    source="settings",
                    signature_id=self.settings.signature_id,
                    site_lang=self.settings.site_lang,
                )
            return TokenCheckResult(
                status="ready",
                reason="authorization configured on settings",
                authorization=self.settings.authorization,
                refresh_available=self.refresh_available(),
                source="settings",
                signature_id=self.settings.signature_id,
                site_lang=self.settings.site_lang,
            )

        authorization = cached_authorization
        if self.refresh_available():
            reason = "cached token expired" if authorization else "token missing"
            return TokenCheckResult(
                status="needs_refresh",
                reason=reason,
                refresh_available=True,
                source="cache" if authorization else "",
                **_cached_request_context(record),
            )

        return TokenCheckResult(
            status="missing",
            reason="no authorization token and refresh is not configured",
            refresh_available=False,
        )

    def refresh_available(self) -> bool:
        return self.settings.token_refresh_enabled and bool(
            self.settings.token_refresh_cmd or self.settings.token_refresh_url
        )

    def refresh_access_token(self) -> TokenRefreshResult:
        if not self.settings.token_refresh_enabled:
            return TokenRefreshResult(
                success=False,
                status="disabled",
                reason="EUREKA_TOKEN_REFRESH_ENABLED is false",
            )

        if not self.settings.token_refresh_cmd and not self.settings.token_refresh_url:
            return TokenRefreshResult(
                success=False,
                status="not_configured",
                reason="no Eureka token refresh command or URL configured",
            )

        current_record = self._read_cached_record()
        try:
            data = (
                self._refresh_by_command()
                if self.settings.token_refresh_cmd
                else self._refresh_by_http(current_record)
            )
        except Exception as exc:  # noqa: BLE001 - keep auth failures in graph state.
            return TokenRefreshResult(success=False, status="failed", reason=str(exc))

        record = self._token_record_from_response(data, current_record)
        authorization = _authorization_from_record(record)
        if not authorization:
            return TokenRefreshResult(
                success=False,
                status="invalid_response",
                reason="refresh response did not include an access token",
            )

        self._write_cached_record(record)
        return TokenRefreshResult(
            success=True,
            status="refreshed",
            reason="access token refreshed",
            authorization=authorization,
        )

    def save_refresh_credentials(
        self,
        refresh_token: str,
        cookie: str = "",
        client_id: str = "",
        from_value: str = "eureka",
        response_type: str = "TOKEN",
    ) -> Path:
        if not self.settings.token_cache:
            raise ValueError("EUREKA_TOKEN_CACHE is required to save refresh credentials")

        record = self._read_cached_record()
        record["refresh_token"] = refresh_token
        record["from"] = from_value
        record["response_type"] = response_type
        if cookie:
            record["cookie"] = cookie
        if client_id:
            record["client_id"] = client_id

        for transient_key in ("access_token", "authorization", "expires_at"):
            record.pop(transient_key, None)

        self._write_cached_record(record)
        return Path(self.settings.token_cache).expanduser()

    def save_cookie(self, cookie: str) -> Path:
        if not self.settings.token_cache:
            raise ValueError("EUREKA_TOKEN_CACHE is required to save cookie")

        record = self._read_cached_record()
        record["cookie"] = cookie
        self._write_cached_record(record)
        return Path(self.settings.token_cache).expanduser()

    def import_curl(self, curl_text: str) -> dict[str, Any]:
        if not self.settings.token_cache:
            raise ValueError("EUREKA_TOKEN_CACHE is required to import curl credentials")

        parsed = parse_imported_curl(curl_text)
        return self.import_auth(
            authorization=parsed.authorization,
            signature_id=parsed.signature_id,
            site_lang=parsed.site_lang,
            cookie=parsed.cookie,
            source_url=parsed.source_url,
            expires_at=parsed.expires_at,
        )

    def import_auth(
        self,
        authorization: str = "",
        signature_id: str = "",
        site_lang: str = "",
        cookie: str = "",
        source_url: str = "",
        expires_at: float | None = None,
    ) -> dict[str, Any]:
        if not self.settings.token_cache:
            raise ValueError("EUREKA_TOKEN_CACHE is required to import Eureka credentials")

        parsed = ImportedCurlAuth(
            authorization=_normalize_authorization(authorization) if authorization else "",
            signature_id=signature_id,
            site_lang=site_lang,
            cookie=cookie,
            source_url=source_url,
            expires_at=expires_at or jwt_expires_at(authorization),
        )
        if not any((parsed.authorization, parsed.signature_id, parsed.site_lang, parsed.cookie)):
            raise ValueError(
                "credentials did not include authorization, x-signature-id, x-site-lang, or cookie"
            )

        record = self._read_cached_record()
        if parsed.authorization:
            record["authorization"] = parsed.authorization
            record["access_token"] = _strip_bearer_prefix(parsed.authorization)
            if parsed.expires_at:
                record["expires_at"] = parsed.expires_at
        if parsed.signature_id:
            record["signature_id"] = parsed.signature_id
        if parsed.site_lang:
            record["site_lang"] = parsed.site_lang
        if parsed.cookie:
            record["cookie"] = parsed.cookie
        if parsed.source_url:
            record["imported_from_url"] = parsed.source_url
        record["imported_at"] = time.time()

        self._write_cached_record(record)
        return {
            "saved": True,
            "cache_path": str(Path(self.settings.token_cache).expanduser()),
            "has_authorization": bool(parsed.authorization),
            "has_signature_id": bool(parsed.signature_id),
            "has_site_lang": bool(parsed.site_lang),
            "has_cookie": bool(parsed.cookie),
            "expires_at": record.get("expires_at", ""),
            "imported_from_url": parsed.source_url,
        }

    def read_cached_auth_snapshot(self) -> dict[str, str]:
        record = self._read_cached_record()
        context = _cached_request_context(record)
        return {
            "authorization": _authorization_from_record(record),
            "signature_id": context["signature_id"],
            "site_lang": context["site_lang"],
            "cookie": context["cookie"],
        }

    def read_cached_record_redacted(self) -> dict[str, Any]:
        record = self._read_cached_record()
        return {
            "has_access_token": bool(record.get("access_token") or record.get("authorization")),
            "has_refresh_token": bool(record.get("refresh_token")),
            "has_cookie": bool(record.get("cookie")),
            "has_signature_id": bool(_signature_id_from_record(record)),
            "expires_at": record.get("expires_at", ""),
            "from": record.get("from", ""),
            "client_id": record.get("client_id", ""),
            "response_type": record.get("response_type", ""),
            "site_lang": _site_lang_from_record(record),
            "imported_from_url": record.get("imported_from_url", ""),
            "imported_at": record.get("imported_at", ""),
        }

    def cache_path(self) -> Path | None:
        return Path(self.settings.token_cache).expanduser() if self.settings.token_cache else None

    def _read_cached_record(self) -> dict[str, Any]:
        if not self.settings.token_cache:
            return {}

        cache_path = Path(self.settings.token_cache).expanduser()
        if not cache_path.exists():
            return {}

        raw = cache_path.read_text(encoding="utf-8").strip()
        if not raw:
            return {}

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {"access_token": raw}

        return data if isinstance(data, dict) else {}

    def _write_cached_record(self, record: Mapping[str, Any]) -> None:
        if not self.settings.token_cache:
            return

        cache_path = Path(self.settings.token_cache).expanduser()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(dict(record), ensure_ascii=False, indent=2)
        tmp_path = cache_path.with_name(f".{cache_path.name}.tmp")
        tmp_path.write_text(payload, encoding="utf-8")
        tmp_path.replace(cache_path)

    def _is_expired(self, record: Mapping[str, Any]) -> bool:
        expires_at = record.get("expires_at")
        if expires_at in ("", None):
            return False

        try:
            expires_at_seconds = float(expires_at)
        except (TypeError, ValueError):
            return False

        return expires_at_seconds <= time.time() + self.settings.token_expiry_skew_seconds

    def _refresh_by_command(self) -> Any:
        result = subprocess.run(
            self.settings.token_refresh_cmd,
            check=True,
            shell=True,
            capture_output=True,
            text=True,
        )
        return _parse_json_or_text(result.stdout.strip())

    def _refresh_by_http(self, current_record: Mapping[str, Any]) -> Any:
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("httpx is not installed. Run `uv sync` first.") from exc

        with httpx.Client(timeout=self.settings.timeout_seconds) as client:
            response = client.request(
                self.settings.token_refresh_method.upper(),
                self.settings.token_refresh_url,
                headers=self._refresh_headers(current_record),
                json=self._refresh_body(current_record) or None,
            )
            response.raise_for_status()
            return response.json()

    def _refresh_headers(self, current_record: Mapping[str, Any]) -> dict[str, str]:
        headers = dict(DEFAULT_REFRESH_HEADERS)
        headers.update(self.settings.token_refresh_headers)
        if current_record.get("cookie") and not _has_header(headers, "cookie"):
            headers["cookie"] = str(current_record["cookie"])
        return {key: value for key, value in headers.items() if value}

    def _refresh_body(self, current_record: Mapping[str, Any]) -> dict[str, Any]:
        body = dict(self.settings.token_refresh_body)
        cache_defaults = {
            "from": current_record.get("from"),
            "client_id": current_record.get("client_id"),
            "response_type": current_record.get("response_type"),
            "refresh_token": current_record.get("refresh_token"),
        }
        for key, value in cache_defaults.items():
            if value and not body.get(key):
                body[key] = value
        return body

    def _token_record_from_response(
        self,
        data: Any,
        current_record: Mapping[str, Any],
    ) -> dict[str, Any]:
        if isinstance(data, str):
            return {
                **dict(current_record),
                "access_token": _strip_bearer_prefix(data),
                "authorization": _normalize_authorization(data),
            }

        authorization = _extract_path(data, self.settings.token_refresh_authorization_path)
        access_token = _extract_path(data, self.settings.token_refresh_access_token_path)
        refresh_token = _extract_path(data, self.settings.token_refresh_refresh_token_path)
        expires_at = _extract_path(data, self.settings.token_refresh_expires_at_path)
        expires_in = _extract_path(data, self.settings.token_refresh_expires_in_path)

        authorization = authorization or _find_first_value(data, {"authorization"})
        access_token = access_token or _find_first_value(
            data,
            {"access_token", "accessToken", "token"},
        )
        refresh_token = refresh_token or _find_first_value(
            data,
            {"refresh_token", "refreshToken"},
        )
        expires_at = expires_at or _find_first_value(data, {"expires_at", "expiresAt"})
        expires_in = expires_in or _find_first_value(data, {"expires_in", "expiresIn"})

        record = dict(current_record)
        if isinstance(authorization, str) and authorization:
            record["authorization"] = _normalize_authorization(authorization)
        if isinstance(access_token, str) and access_token:
            record["access_token"] = _strip_bearer_prefix(access_token)
            if not authorization:
                record["authorization"] = _normalize_authorization(access_token)
        if isinstance(refresh_token, str) and refresh_token:
            record["refresh_token"] = refresh_token
        if expires_at not in ("", None):
            record["expires_at"] = expires_at
        elif expires_in not in ("", None):
            record["expires_at"] = time.time() + float(expires_in)
        elif isinstance(record.get("access_token"), str):
            expires_at_from_jwt = _jwt_exp(str(record["access_token"]))
            if expires_at_from_jwt:
                record["expires_at"] = expires_at_from_jwt
        return record


def parse_imported_curl(curl_text: str) -> ImportedCurlAuth:
    text = _normalize_curl_text(curl_text)
    headers, cookie, source_url = _parse_curl_parts(text)
    authorization = headers.get("authorization", "")
    signature_id = headers.get("x-signature-id", "")
    site_lang = headers.get("x-site-lang", "")
    cookie = headers.get("cookie", "") or cookie
    expires_at = _jwt_exp(_strip_bearer_prefix(authorization)) if authorization else None

    return ImportedCurlAuth(
        authorization=_normalize_authorization(authorization) if authorization else "",
        signature_id=signature_id,
        site_lang=site_lang,
        cookie=cookie,
        source_url=source_url,
        expires_at=expires_at,
    )


def _normalize_curl_text(curl_text: str) -> str:
    text = curl_text.strip().replace("\u00a0", " ")
    text = re.sub(
        r"\[(https?://[^\]]+)\]\((https?://[^)]+)\)",
        lambda match: match.group(2),
        text,
    )
    replacements = {
        "\\\n": " ",
        "\\_": "_",
        "\\.": ".",
        "\\&": "&",
        "\\--": "--",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def _parse_curl_parts(curl_text: str) -> tuple[dict[str, str], str, str]:
    headers: dict[str, str] = {}
    cookie = ""
    source_url = ""

    for args in (_safe_shlex_split(curl_text),):
        index = 0
        while index < len(args):
            part = args[index]
            next_part = args[index + 1] if index + 1 < len(args) else ""
            if part in {"-H", "--header"} and next_part:
                key, value = _split_header(next_part)
                if key:
                    headers[key] = value
                index += 2
                continue
            if part in {"-b", "--cookie"} and next_part:
                cookie = _clean_curl_value(next_part)
                index += 2
                continue
            if part == "--url" and next_part:
                source_url = _clean_curl_value(next_part)
                index += 2
                continue
            if not source_url and part.startswith("http"):
                source_url = _clean_curl_value(part)
            index += 1

    if not headers:
        headers.update(_regex_headers(curl_text))
    if not cookie:
        cookie = _regex_cookie(curl_text)
    if not source_url:
        source_url = _regex_url(curl_text)

    return headers, cookie, source_url


def _safe_shlex_split(curl_text: str) -> list[str]:
    try:
        return shlex.split(curl_text)
    except ValueError:
        return []


def _regex_headers(curl_text: str) -> dict[str, str]:
    headers = {}
    for raw_header in re.findall(r"(?:-H|--header)\s+(['\"])(.*?)\1", curl_text, re.DOTALL):
        key, value = _split_header(raw_header[1])
        if key:
            headers[key] = value
    return headers


def _regex_cookie(curl_text: str) -> str:
    match = re.search(r"(?:-b|--cookie)\s+(['\"])(.*?)\1", curl_text, re.DOTALL)
    return _clean_curl_value(match.group(2)) if match else ""


def _regex_url(curl_text: str) -> str:
    match = re.search(r"--url\s+(['\"]?)(https?://[^\s'\"]+)\1", curl_text)
    if match:
        return _clean_curl_value(match.group(2))
    match = re.search(r"\bhttps?://[^\s'\"]+", curl_text)
    return _clean_curl_value(match.group(0)) if match else ""


def _split_header(raw_header: str) -> tuple[str, str]:
    key, separator, value = raw_header.partition(":")
    if not separator:
        return "", ""
    return key.strip().lower(), _clean_curl_value(value)


def _clean_curl_value(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        text = text[1:-1]
    return _normalize_curl_text(text)


def _cached_request_context(record: Mapping[str, Any]) -> dict[str, str]:
    return {
        "signature_id": _signature_id_from_record(record),
        "site_lang": _site_lang_from_record(record),
        "cookie": _string_from_record(record, "cookie"),
    }


def _signature_id_from_record(record: Mapping[str, Any]) -> str:
    return (
        _string_from_record(record, "signature_id")
        or _string_from_record(record, "x_signature_id")
        or _string_from_record(record, "x-signature-id")
    )


def _site_lang_from_record(record: Mapping[str, Any]) -> str:
    return _string_from_record(record, "site_lang") or _string_from_record(record, "x-site-lang")


def _string_from_record(record: Mapping[str, Any], key: str) -> str:
    value = record.get(key)
    return value.strip() if isinstance(value, str) else ""


def _has_header(headers: Mapping[str, str], header_name: str) -> bool:
    return any(key.lower() == header_name.lower() for key in headers)


def _authorization_from_record(record: Mapping[str, Any]) -> str:
    authorization = record.get("authorization")
    if isinstance(authorization, str) and authorization:
        return _normalize_authorization(authorization)

    access_token = record.get("access_token") or record.get("token")
    if isinstance(access_token, str) and access_token:
        return _normalize_authorization(access_token)
    return ""


def _normalize_authorization(token_or_header: str) -> str:
    value = token_or_header.strip()
    return value if value.lower().startswith("bearer ") else f"Bearer {value}"


def _strip_bearer_prefix(token_or_header: str) -> str:
    value = token_or_header.strip()
    return value[7:].strip() if value.lower().startswith("bearer ") else value


def _authorization_is_expired(authorization: str, skew_seconds: float) -> bool:
    expires_at = jwt_expires_at(authorization)
    return bool(expires_at and expires_at <= time.time() + skew_seconds)


def jwt_expires_at(token_or_authorization: str) -> float | None:
    return _jwt_exp(_strip_bearer_prefix(token_or_authorization))


def _jwt_exp(token: str) -> float | None:
    parts = token.split(".")
    if len(parts) < 2:
        return None

    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload + padding)
        data = json.loads(decoded)
    except (binascii.Error, ValueError, json.JSONDecodeError):
        return None

    exp = data.get("exp") if isinstance(data, Mapping) else None
    try:
        return float(exp)
    except (TypeError, ValueError):
        return None


def _parse_json_or_text(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _extract_path(data: Any, path: str) -> Any:
    if not path:
        return data

    current = data
    for part in path.split("."):
        if isinstance(current, Mapping):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            current = current[int(part)]
        else:
            return None
    return current


def _find_first_value(data: Any, keys: set[str]) -> Any:
    if isinstance(data, Mapping):
        for key in keys:
            value = data.get(key)
            if value not in ("", None):
                return value
        for value in data.values():
            found = _find_first_value(value, keys)
            if found not in ("", None):
                return found
    elif isinstance(data, list):
        for item in data:
            found = _find_first_value(item, keys)
            if found not in ("", None):
                return found
    return None
