"""
AutoJob AI — LLM Provider Abstraction
Single file to configure AI provider. Switch between Gemini/OpenAI by changing .env.

Google Gemini supports OpenAI-compatible API, so we use the same openai
Python client for both providers — just different base_url, key, and model.
"""

import logging

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger("autojob.llm")

# ── Provider URLs ────────────────────────────────────
_PROVIDER_BASE_URLS = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "openai": "https://api.openai.com/v1",
    "groq": "https://api.groq.com/openai/v1",
}

# ── Default Models Per Provider ──────────────────────
_DEFAULT_MODELS = {
    "gemini": "gemini-2.0-flash",
    "openai": "gpt-4o-mini",
    "groq": "llama-3.1-70b-versatile",
}

# ── Fallback Models (used when primary hits rate limits) ──
_FALLBACK_MODELS = {
    "groq": "llama-3.1-8b-instant",  # Smaller but separate rate limit
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.0-flash",
}


def get_llm_client() -> AsyncOpenAI:
    """Get the configured LLM client. Uses OpenAI-compatible API for all providers."""
    provider = settings.llm_provider.lower()
    base_url = settings.llm_base_url or _PROVIDER_BASE_URLS.get(provider)

    if not base_url:
        raise ValueError(f"Unknown LLM provider: {provider}")

    if not settings.llm_api_key:
        raise ValueError(f"LLM_API_KEY not set for provider: {provider}")

    logger.info(f"LLM provider: {provider} | model: {get_model()}")

    return AsyncOpenAI(
        api_key=settings.llm_api_key,
        base_url=base_url,
    )


def get_model() -> str:
    """Get the configured model name."""
    provider = settings.llm_provider.lower()
    return settings.llm_model or _DEFAULT_MODELS.get(provider, "gpt-4o-mini")


def get_fallback_model() -> str:
    """Get the fallback model for when primary hits rate limits."""
    provider = settings.llm_provider.lower()
    return _FALLBACK_MODELS.get(provider, get_model())


async def llm_chat(messages: list, temperature: float = 0.1, response_format=None, **kwargs) -> str:
    """Make LLM call with automatic fallback on rate limit errors.
    
    Returns the response content string. Automatically retries with
    fallback model if primary model hits rate limits (429).
    """
    # Try primary model first
    try:
        create_kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            **kwargs,
        }
        if response_format:
            create_kwargs["response_format"] = response_format

        response = await client.chat.completions.create(**create_kwargs)
        return response.choices[0].message.content
    except Exception as e:
        if "429" in str(e) or "rate_limit" in str(e).lower():
            # Rate limited — try fallback model
            fb_model = get_fallback_model()
            if fb_model != model:
                logger.warning(f"  Rate limited on {model} — falling back to {fb_model}")
                try:
                    create_kwargs["model"] = fb_model
                    response = await client.chat.completions.create(**create_kwargs)
                    return response.choices[0].message.content
                except Exception as e2:
                    logger.error(f"  Fallback model also failed: {e2}")
                    raise e2
        raise e


# ── Singleton Client (reuse across agents) ───────────
client = get_llm_client()
model = get_model()

