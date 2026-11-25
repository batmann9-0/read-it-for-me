"""Environment settings for Read-It-For-Me (pydantic-settings).

Vision provider selection, in priority order:

1. ``VISION_BRIDGE_URL`` — a small Gemini bridge (see ``scripts/bridge_proxy.py``).
   Used for the hosted demo: the real Gemini API key never has to be stored
   in the hosting platform's env, the bridge holds it via the secure vault.
2. ``BASE_URL`` / ``API_KEY`` / ``MODEL`` — any OpenAI-compatible
   chat-completions endpoint: DashScope (Qwen2.5-VL / Qwen3-VL),
   a Hugging Face endpoint, a local vLLM/Ollama server, or Gemini's
   OpenAI-compatible endpoint. This is the path from the specification.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Vision / language model (OpenAI-compatible endpoint) ---
    base_url: str = ""  # e.g. https://dashscope.aliyuncs.com/compatible-mode/v1
    api_key: str = ""
    model: str = "qwen2.5-vl-72b-instruct"

    # --- Optional Gemini bridge (hosted demo path) ---
    vision_bridge_url: str = ""  # e.g. https://<tunnel>/webhook/readit-analyze
    vision_bridge_token: str = ""

    # --- App defaults ---
    default_lang: str = "ur"
    max_image_bytes: int = 8 * 1024 * 1024  # 8 MB upload cap
    max_image_edge: int = 1600  # longest edge after server-side resize
    model_timeout_seconds: float = 30.0
    tts_timeout_seconds: float = 15.0
    rate_limit_per_minute: int = 20

    @property
    def vision_configured(self) -> bool:
        """True when at least one vision route is configured."""
        return bool(self.vision_bridge_url or (self.base_url and self.api_key))


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()
