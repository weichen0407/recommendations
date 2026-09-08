"""curl-based Eureka task client."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from recommendation_contents.config import EurekaSettings

DEFAULT_EUREKA_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "zh-CN,zh;q=0.9",
    "content-type": "application/json",
    "origin": "https://eureka.patsnap.com",
    "priority": "u=1, i",
    "referer": "https://eureka.patsnap.com/",
    "sec-ch-ua": '"Chromium";v="152", "Not?A_Brand";v="24", "Google Chrome";v="152"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
    ),
    "x-api-version": "1.0",
    "x-patsnap-from": "w-eureka",
    "x-requested-with": "XMLHttpRequest",
}


@dataclass(frozen=True)
class CurlResult:
    payload: dict[str, Any]
    body: str
    status_code: int
    return_code: int
    stderr: str = ""

    @property
    def success(self) -> bool:
        return self.return_code == 0 and 200 <= self.status_code < 400


class EurekaCurlClient:
    def __init__(self, settings: EurekaSettings) -> None:
        self.settings = settings

    def has_authorization_header(self) -> bool:
        return any(key.lower() == "authorization" and value for key, value in self.headers().items())

    def headers(self) -> dict[str, str]:
        headers = dict(DEFAULT_EUREKA_HEADERS)
        if self.settings.authorization:
            headers["authorization"] = self.settings.authorization
        if self.settings.signature_id:
            headers["x-signature-id"] = self.settings.signature_id
        if self.settings.site_lang:
            headers["x-site-lang"] = self.settings.site_lang
        headers.update(self.settings.extra_headers)
        return {key: value for key, value in headers.items() if value}

    def create_conversation(self, query: str) -> CurlResult:
        payload = {
            "work_project": "",
            "query": query,
            "parallel": True,
            "image_ids": [],
            "file_ids": [],
            "skill_list": [],
            "timezone": self.settings.timezone,
        }
        return run_curl_json(
            url=self.settings.query_endpoint,
            headers=self.headers(),
            payload=payload,
            timeout_seconds=self.settings.timeout_seconds,
        )

    def create_share(self, session_id: str) -> CurlResult:
        payload = {
            "data_id": session_id,
            "data_type": "AGENT_CONVERSATION",
        }
        return run_curl_json(
            url=self.settings.share_endpoint,
            headers=self.headers(),
            payload=payload,
            timeout_seconds=self.settings.timeout_seconds,
        )

    def build_session_link(self, session_id: str) -> str:
        return self.settings.session_link_template.format(session_id=quote(session_id, safe=""))

    def build_share_link(self, share_id: str) -> str:
        return self.settings.share_link_template.format(share_id=quote(share_id, safe=""))


def run_curl_json(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_seconds: float,
) -> CurlResult:
    command = build_curl_command(
        url=url,
        headers=headers,
        payload=payload,
        timeout_seconds=timeout_seconds,
    )
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError as exc:
        return CurlResult(
            payload=payload,
            body="",
            status_code=0,
            return_code=127,
            stderr=f"curl execution failed: {exc}",
        )

    body, status_code = split_curl_output(result.stdout)
    return CurlResult(
        payload=payload,
        body=body,
        status_code=status_code,
        return_code=result.returncode,
        stderr=result.stderr.strip(),
    )


def build_curl_command(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_seconds: float,
) -> list[str]:
    command = [
        "curl",
        "-sS",
        "--url",
        url,
        "--request",
        "POST",
        "--max-time",
        str(timeout_seconds),
    ]
    for key, value in headers.items():
        command.extend(["-H", f"{key}: {value}"])

    command.extend(
        [
            "--data-raw",
            json.dumps(payload, ensure_ascii=False),
            "-w",
            "\n%{http_code}",
        ]
    )
    return command


def split_curl_output(stdout: str) -> tuple[str, int]:
    if not stdout:
        return "", 0

    body, _, maybe_status = stdout.rpartition("\n")
    if maybe_status.isdigit():
        return body, int(maybe_status)
    return stdout, 0


def parse_json_body(body: str) -> Any:
    if not body:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def find_first_value(data: Any, keys: set[str]) -> str:
    if isinstance(data, dict):
        for key in keys:
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
        for value in data.values():
            found = find_first_value(value, keys)
            if found:
                return found
    elif isinstance(data, list):
        for item in data:
            found = find_first_value(item, keys)
            if found:
                return found
    return ""
