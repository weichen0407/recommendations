"""Profile Gate client used by graph nodes."""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from recommendation_contents.config import ProfileGateSettings


class ProfileGateClient:
    def __init__(self, settings: ProfileGateSettings) -> None:
        self.settings = settings

    def fetch_profile(
        self,
        user_id: str,
        query: str = "",
        context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.settings.endpoint:
            return {}

        last_error: Exception | None = None
        attempts = max(1, self.settings.retry_count + 1)

        for attempt in range(attempts):
            try:
                return self._post_profile_request(user_id=user_id, query=query, context=context or {})
            except Exception as exc:  # noqa: BLE001 - retry all transient client failures.
                last_error = exc
                if attempt + 1 < attempts:
                    time.sleep(self.settings.retry_delay_seconds)

        raise RuntimeError(f"Profile Gate request failed: {last_error}") from last_error

    def _post_profile_request(
        self,
        user_id: str,
        query: str,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("httpx is not installed. Run `python -m pip install -e .` first.") from exc

        payload = {
            "signatureId": self.settings.signature_id,
            "siteLang": self.settings.site_lang,
            "sourceType": self.settings.source_type,
            "moduleType": self.settings.module_type,
            "eventType": self.settings.event_type,
            "resultMode": self.settings.result_mode,
            "userId": user_id,
            "query": query,
            "context": dict(context),
        }
        payload = {key: value for key, value in payload.items() if value not in ("", None, {})}

        headers = dict(self.settings.extra_headers)
        token = self._get_token()
        if token and "Authorization" not in headers:
            headers["Authorization"] = f"Bearer {token}"

        with httpx.Client(timeout=self.settings.request_timeout_seconds) as client:
            response = client.post(self.settings.endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        extracted = _extract_path(data, self.settings.response_pass_path)
        return extracted if isinstance(extracted, dict) else {"value": extracted}

    def _get_token(self) -> str:
        cached = self._read_cached_token()
        if cached:
            return cached

        if self.settings.token_refresh_cmd:
            token = self._refresh_token_by_command()
            self._write_cached_token(token)
            return token

        if self.settings.token_refresh_url:
            token = self._refresh_token_by_http()
            self._write_cached_token(token)
            return token

        return ""

    def _read_cached_token(self) -> str:
        if not self.settings.token_cache:
            return ""

        cache_path = Path(self.settings.token_cache).expanduser()
        if not cache_path.exists():
            return ""

        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return cache_path.read_text(encoding="utf-8").strip()

        expires_at = data.get("expires_at")
        if expires_at and float(expires_at) <= time.time():
            return ""
        return str(data.get("access_token") or data.get("token") or "")

    def _write_cached_token(self, token: str) -> None:
        if not token or not self.settings.token_cache:
            return

        cache_path = Path(self.settings.token_cache).expanduser()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({"access_token": token}), encoding="utf-8")

    def _refresh_token_by_command(self) -> str:
        result = subprocess.run(
            self.settings.token_refresh_cmd,
            check=True,
            shell=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def _refresh_token_by_http(self) -> str:
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("httpx is not installed. Run `python -m pip install -e .` first.") from exc

        method = self.settings.token_refresh_method.upper()
        with httpx.Client(timeout=self.settings.request_timeout_seconds) as client:
            response = client.request(
                method,
                self.settings.token_refresh_url,
                headers=self.settings.token_refresh_headers,
                json=self.settings.token_refresh_body or None,
            )
            response.raise_for_status()
            data = response.json()

        token = _extract_path(data, "access_token") or _extract_path(data, "token")
        return str(token or "")


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
