"""Configuration helpers for environment-backed settings."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def load_env_file(path: str = ".env") -> dict[str, str]:
    """Load a simple dotenv file without overriding process environment."""
    env_path = Path(path)
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value

    return values


def merged_env(env_file: str = ".env") -> dict[str, str]:
    """Merge dotenv values with process env, letting process env win."""
    values = load_env_file(env_file)
    values.update(os.environ)
    return values


def _json_env(env: Mapping[str, str], key: str, default: Any | None = None) -> Any:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{key} must be valid JSON") from exc


def _float_env(env: Mapping[str, str], key: str, default: float) -> float:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    return float(raw)


def _optional_float_env(env: Mapping[str, str], key: str) -> float | None:
    raw = env.get(key)
    if raw is None or raw == "":
        return None
    return float(raw)


def _int_env(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    return int(raw)


@dataclass(frozen=True)
class OpenAISettings:
    api_key: str = ""
    base_url: str = ""
    model: str = "gpt-4o-mini"
    temperature: float | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> OpenAISettings:
        return cls(
            api_key=env.get("OPENAI_API_KEY", ""),
            base_url=env.get("OPENAI_BASE_URL", ""),
            model=env.get("OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini",
            temperature=_optional_float_env(env, "OPENAI_TEMPERATURE"),
        )


@dataclass(frozen=True)
class ProfileGateSettings:
    endpoint: str = ""
    signature_id: str = ""
    site_lang: str = ""
    source_type: str = ""
    module_type: str = ""
    event_type: str = ""
    result_mode: str = ""
    response_pass_path: str = ""
    extra_headers: dict[str, str] = field(default_factory=dict)
    token_refresh_cmd: str = ""
    token_cache: str = ""
    token_refresh_url: str = ""
    token_refresh_method: str = "POST"
    token_refresh_headers: dict[str, str] = field(default_factory=dict)
    token_refresh_body: dict[str, Any] = field(default_factory=dict)
    request_timeout_seconds: float = 20.0
    concurrency: int = 4
    retry_count: int = 2
    retry_delay_seconds: float = 0.5

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> ProfileGateSettings:
        return cls(
            endpoint=env.get("PROFILE_GATE_ENDPOINT", ""),
            signature_id=env.get("PROFILE_GATE_SIGNATURE_ID", ""),
            site_lang=env.get("PROFILE_GATE_SITE_LANG", ""),
            source_type=env.get("PROFILE_GATE_SOURCE_TYPE", ""),
            module_type=env.get("PROFILE_GATE_MODULE_TYPE", ""),
            event_type=env.get("PROFILE_GATE_EVENT_TYPE", ""),
            result_mode=env.get("PROFILE_GATE_RESULT_MODE", ""),
            response_pass_path=env.get("PROFILE_GATE_RESPONSE_PASS_PATH", ""),
            extra_headers=_json_env(env, "PROFILE_GATE_EXTRA_HEADERS_JSON", {}) or {},
            token_refresh_cmd=env.get("PROFILE_GATE_TOKEN_REFRESH_CMD", ""),
            token_cache=env.get("PROFILE_GATE_TOKEN_CACHE", ""),
            token_refresh_url=env.get("PROFILE_GATE_TOKEN_REFRESH_URL", ""),
            token_refresh_method=env.get("PROFILE_GATE_TOKEN_REFRESH_METHOD", "POST") or "POST",
            token_refresh_headers=_json_env(env, "PROFILE_GATE_TOKEN_REFRESH_HEADERS_JSON", {})
            or {},
            token_refresh_body=_json_env(env, "PROFILE_GATE_TOKEN_REFRESH_BODY_JSON", {}) or {},
            request_timeout_seconds=_float_env(
                env,
                "PROFILE_GATE_REQUEST_TIMEOUT_SECONDS",
                20.0,
            ),
            concurrency=_int_env(env, "PROFILE_GATE_CONCURRENCY", 4),
            retry_count=_int_env(env, "PROFILE_GATE_RETRY_COUNT", 2),
            retry_delay_seconds=_float_env(env, "PROFILE_GATE_RETRY_DELAY_SECONDS", 0.5),
        )


@dataclass(frozen=True)
class EurekaSettings:
    query_endpoint: str = "https://eureka-service.patsnap.com/api/eureka/query/conversational"
    share_endpoint: str = "https://eureka-service.patsnap.com/eureka/secure-share/create"
    authorization: str = ""
    bearer_token: str = ""
    signature_id: str = ""
    site_lang: str = "CN"
    extra_headers: dict[str, str] = field(default_factory=dict)
    timeout_seconds: float = 60.0
    timezone: str = "Asia/Shanghai"
    session_link_template: str = (
        "https://eureka.patsnap.com/ai-search/{session_id}"
        "?from=rd-home&start_from=eureka_landingpage"
    )
    share_link_template: str = (
        "https://eureka.patsnap.com/share/"
        "?id={share_id}&from=invite-eureakplg-result&content="
    )

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> EurekaSettings:
        extra_headers = _json_env(env, "PROFILE_GATE_EXTRA_HEADERS_JSON", {}) or {}
        extra_headers.update(_json_env(env, "EUREKA_EXTRA_HEADERS_JSON", {}) or {})

        bearer_token = env.get("EUREKA_BEARER_TOKEN", "")
        authorization = env.get("EUREKA_AUTHORIZATION", "")
        if not authorization and bearer_token:
            authorization = (
                bearer_token if bearer_token.lower().startswith("bearer ") else f"Bearer {bearer_token}"
            )

        return cls(
            query_endpoint=env.get(
                "EUREKA_QUERY_ENDPOINT",
                "https://eureka-service.patsnap.com/api/eureka/query/conversational",
            ),
            share_endpoint=env.get(
                "EUREKA_SHARE_ENDPOINT",
                "https://eureka-service.patsnap.com/eureka/secure-share/create",
            ),
            authorization=authorization,
            bearer_token=bearer_token,
            signature_id=env.get("EUREKA_SIGNATURE_ID") or env.get("PROFILE_GATE_SIGNATURE_ID", ""),
            site_lang=env.get("EUREKA_SITE_LANG") or env.get("PROFILE_GATE_SITE_LANG", "CN") or "CN",
            extra_headers=extra_headers,
            timeout_seconds=_float_env(env, "EUREKA_TIMEOUT_SECONDS", 60.0),
            timezone=env.get("EUREKA_TIMEZONE", "Asia/Shanghai") or "Asia/Shanghai",
            session_link_template=env.get(
                "EUREKA_SESSION_LINK_TEMPLATE",
                "https://eureka.patsnap.com/ai-search/{session_id}"
                "?from=rd-home&start_from=eureka_landingpage",
            ),
            share_link_template=env.get(
                "EUREKA_SHARE_LINK_TEMPLATE",
                "https://eureka.patsnap.com/share/"
                "?id={share_id}&from=invite-eureakplg-result&content=",
            ),
        )


@dataclass(frozen=True)
class AppSettings:
    openai: OpenAISettings
    profile_gate: ProfileGateSettings
    eureka: EurekaSettings

    @classmethod
    def from_env_file(cls, env_file: str = ".env") -> AppSettings:
        env = merged_env(env_file)
        return cls(
            openai=OpenAISettings.from_env(env),
            profile_gate=ProfileGateSettings.from_env(env),
            eureka=EurekaSettings.from_env(env),
        )
