from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import os
from dotenv import load_dotenv

from model_provider import ProviderConfig, normalize_provider


@dataclass
class LabConfig:
    """Shared configuration for the lab."""

    base_dir: Path
    data_dir: Path
    state_dir: Path
    compact_threshold_tokens: int
    compact_keep_messages: int
    model: ProviderConfig
    judge_model: ProviderConfig


def _resolve_provider_credentials(
    provider: str,
    prefix: str = "LLM",
) -> tuple[str | None, str | None]:
    """Helper to resolve api_key and base_url for a given provider and prefix."""
    provider_key_map = {
        "openai": ["OPENAI_API_KEY"],
        "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
        "anthropic": ["ANTHROPIC_API_KEY"],
        "openrouter": ["OPENROUTER_API_KEY"],
        "custom": ["CUSTOM_API_KEY", "OPENAI_API_KEY"],
        "ollama": [],
    }

    api_key = os.getenv(f"{prefix}_API_KEY")
    if not api_key:
        for env_var in provider_key_map.get(provider, []):
            val = os.getenv(env_var)
            if val:
                api_key = val
                break

    base_url = os.getenv(f"{prefix}_BASE_URL")
    if not base_url:
        if provider == "custom":
            base_url = os.getenv("CUSTOM_BASE_URL", "http://localhost:8000/v1")
        elif provider == "ollama":
            base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        elif provider == "openrouter":
            base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

    return api_key, base_url


def load_config(base_dir: Path | None = None) -> LabConfig:
    """Load environment variables and return a populated LabConfig."""
    root = (base_dir or Path(__file__).resolve().parent.parent).resolve()

    # Load environment variables
    env_file = root / ".env"
    if env_file.exists():
        load_dotenv(env_file)
    else:
        load_dotenv()

    data_dir = root / "data"
    state_dir = root / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "profiles").mkdir(parents=True, exist_ok=True)

    compact_threshold_tokens = int(os.getenv("COMPACT_THRESHOLD_TOKENS", "1200"))
    compact_keep_messages = int(os.getenv("COMPACT_KEEP_MESSAGES", "4"))

    # Main model configuration
    provider = normalize_provider(os.getenv("LLM_PROVIDER", "openai"))
    model_name = os.getenv("LLM_MODEL", "gpt-4o-mini")
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.0"))
    api_key, base_url = _resolve_provider_credentials(provider, prefix="LLM")

    model_config = ProviderConfig(
        provider=provider,
        model_name=model_name,
        temperature=temperature,
        api_key=api_key,
        base_url=base_url,
    )

    # Judge model configuration
    judge_provider = normalize_provider(os.getenv("JUDGE_PROVIDER", provider))
    judge_model_name = os.getenv("JUDGE_MODEL", model_name)
    judge_temperature = float(os.getenv("JUDGE_TEMPERATURE", "0.0"))
    judge_api_key, judge_base_url = _resolve_provider_credentials(judge_provider, prefix="JUDGE")
    if not judge_api_key:
        judge_api_key = api_key

    judge_config = ProviderConfig(
        provider=judge_provider,
        model_name=judge_model_name,
        temperature=judge_temperature,
        api_key=judge_api_key,
        base_url=judge_base_url,
    )

    return LabConfig(
        base_dir=root,
        data_dir=data_dir,
        state_dir=state_dir,
        compact_threshold_tokens=compact_threshold_tokens,
        compact_keep_messages=compact_keep_messages,
        model=model_config,
        judge_model=judge_config,
    )
