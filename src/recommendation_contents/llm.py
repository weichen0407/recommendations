"""OpenAI model factory."""

from __future__ import annotations

from .config import OpenAISettings


def format_llm_error(exc: Exception) -> str:
    """Return actionable provider diagnostics without exposing response bodies or secrets."""
    error_type = type(exc).__name__
    status_code = getattr(exc, "status_code", None)
    if status_code is None:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)

    detail = error_type
    if isinstance(status_code, int):
        detail += f", HTTP {status_code}"

    if status_code == 400:
        guidance = "The endpoint rejected the request; check model compatibility and request size."
    elif status_code == 401:
        guidance = "Check OPENAI_API_KEY."
    elif status_code == 402:
        guidance = (
            "The provider requires available account or project quota/billing authorization."
        )
    elif status_code == 403:
        guidance = "Check whether the API key can use OPENAI_MODEL."
    elif status_code == 404:
        guidance = "Check OPENAI_BASE_URL and OPENAI_MODEL."
    elif status_code == 408:
        guidance = "The provider timed out; retry later."
    elif status_code == 429:
        guidance = "The provider rate or quota limit was reached; retry later with fewer workers."
    elif isinstance(status_code, int) and status_code >= 500:
        guidance = "The provider service failed; retry later."
    elif error_type in {"APIConnectionError", "OpenAIConnectionError"}:
        guidance = "The model endpoint could not be reached."
    else:
        guidance = "Check the model endpoint and configuration."
    return f"LLM request failed ({detail}). {guidance}"


def create_chat_model(settings: OpenAISettings):
    if not settings.api_key:
        raise RuntimeError("OPENAI_API_KEY is required. Put it in .env or process env.")

    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise RuntimeError(
            "langchain-openai is not installed. Run `python -m pip install -e .` first."
        ) from exc

    kwargs = {
        "api_key": settings.api_key,
        "model": settings.model,
    }
    if settings.base_url:
        kwargs["base_url"] = settings.base_url
    if settings.temperature is not None:
        kwargs["temperature"] = settings.temperature

    return ChatOpenAI(**kwargs)
