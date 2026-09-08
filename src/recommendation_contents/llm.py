"""OpenAI model factory."""

from __future__ import annotations

from .config import OpenAISettings


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
