"""LLM abstraction layer for discovery.

Supports multiple backends:
- Ollama (local, default)
- OpenAI API
- Anthropic API
- Any OpenAI-compatible endpoint
"""

import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


class LLMBackend(ABC):
    """Abstract LLM backend."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend name for logging."""
        pass

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        """Generate text completion."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if backend is available."""
        pass

    def extract_json(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.3,
    ) -> dict | list | None:
        """Generate and parse JSON response."""
        response = self.generate(
            prompt=prompt,
            system=system,
            temperature=temperature,
            max_tokens=2048,
        )
        return _parse_json_response(response)


def _parse_json_response(response: str) -> dict | list | None:
    """Extract JSON from LLM response."""
    # Handle markdown code blocks
    if "```json" in response:
        start = response.find("```json") + 7
        end = response.find("```", start)
        if end > start:
            response = response[start:end].strip()
    elif "```" in response:
        start = response.find("```") + 3
        end = response.find("```", start)
        if end > start:
            response = response[start:end].strip()

    try:
        return json.loads(response)
    except json.JSONDecodeError:
        # Try to find JSON-like content
        for start_char, end_char in [("{", "}"), ("[", "]")]:
            start = response.find(start_char)
            end = response.rfind(end_char)
            if start != -1 and end > start:
                try:
                    return json.loads(response[start:end + 1])
                except json.JSONDecodeError:
                    continue
        logger.warning(f"Failed to parse JSON from: {response[:200]}")
        return None


# =============================================================================
# Ollama Backend
# =============================================================================


@dataclass
class OllamaConfig:
    base_url: str = "http://localhost:11434"
    model: str = "gpt-oss:20b"
    timeout: float = 120.0


class OllamaBackend(LLMBackend):
    """Ollama local LLM backend."""

    def __init__(self, config: OllamaConfig | None = None):
        self.config = config or OllamaConfig(
            base_url=os.environ.get("OLLAMA_URL", "http://localhost:11434"),
            model=os.environ.get("OLLAMA_MODEL", "gpt-oss:20b"),
        )
        self._client = httpx.Client(timeout=self.config.timeout)

    @property
    def name(self) -> str:
        return f"ollama:{self.config.model}"

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        url = f"{self.config.base_url}/api/generate"

        payload = {
            "model": self.config.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        if system:
            payload["system"] = system

        response = self._client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        return data.get("response", "").strip()

    def is_available(self) -> bool:
        try:
            response = self._client.get(f"{self.config.base_url}/api/tags")
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    def list_models(self) -> list[str]:
        try:
            response = self._client.get(f"{self.config.base_url}/api/tags")
            response.raise_for_status()
            data = response.json()
            return [m["name"] for m in data.get("models", [])]
        except httpx.HTTPError:
            return []


# =============================================================================
# OpenAI-Compatible Backend (works with OpenAI, Together, Groq, etc.)
# =============================================================================


@dataclass
class OpenAIConfig:
    api_key: str
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    timeout: float = 60.0


class OpenAIBackend(LLMBackend):
    """OpenAI-compatible API backend."""

    def __init__(self, config: OpenAIConfig | None = None):
        if config:
            self.config = config
        else:
            api_key = os.environ.get("OPENAI_API_KEY", "")
            self.config = OpenAIConfig(
                api_key=api_key,
                base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            )
        self._client = httpx.Client(timeout=self.config.timeout)

    @property
    def name(self) -> str:
        return f"openai:{self.config.model}"

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        url = f"{self.config.base_url}/chat/completions"

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        response = self._client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()

    def is_available(self) -> bool:
        return bool(self.config.api_key)


# =============================================================================
# Anthropic Backend
# =============================================================================


@dataclass
class AnthropicConfig:
    api_key: str
    model: str = "claude-3-haiku-20240307"
    timeout: float = 60.0


class AnthropicBackend(LLMBackend):
    """Anthropic Claude API backend."""

    def __init__(self, config: AnthropicConfig | None = None):
        if config:
            self.config = config
        else:
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            self.config = AnthropicConfig(
                api_key=api_key,
                model=os.environ.get("ANTHROPIC_MODEL", "claude-3-haiku-20240307"),
            )
        self._client = httpx.Client(timeout=self.config.timeout)

    @property
    def name(self) -> str:
        return f"anthropic:{self.config.model}"

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        url = "https://api.anthropic.com/v1/messages"

        payload = {
            "model": self.config.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }

        if system:
            payload["system"] = system

        headers = {
            "x-api-key": self.config.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        response = self._client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data["content"][0]["text"].strip()

    def is_available(self) -> bool:
        return bool(self.config.api_key)


# =============================================================================
# Backend Selection
# =============================================================================


_llm_backend: LLMBackend | None = None


def get_llm_backend() -> LLMBackend:
    """Get the configured LLM backend.

    Priority:
    1. ANTHROPIC_API_KEY -> Anthropic
    2. OPENAI_API_KEY -> OpenAI
    3. Ollama (if available)
    4. Raises error if nothing available
    """
    global _llm_backend

    if _llm_backend is not None:
        return _llm_backend

    # Check for API keys first
    if os.environ.get("ANTHROPIC_API_KEY"):
        _llm_backend = AnthropicBackend()
        logger.info(f"Using LLM backend: {_llm_backend.name}")
        return _llm_backend

    if os.environ.get("OPENAI_API_KEY"):
        _llm_backend = OpenAIBackend()
        logger.info(f"Using LLM backend: {_llm_backend.name}")
        return _llm_backend

    # Try Ollama
    ollama = OllamaBackend()
    if ollama.is_available():
        _llm_backend = ollama
        logger.info(f"Using LLM backend: {_llm_backend.name}")
        return _llm_backend

    raise RuntimeError(
        "No LLM backend available. Set ANTHROPIC_API_KEY, OPENAI_API_KEY, "
        "or ensure Ollama is running."
    )


def set_llm_backend(backend: LLMBackend) -> None:
    """Manually set the LLM backend."""
    global _llm_backend
    _llm_backend = backend
    logger.info(f"LLM backend set to: {backend.name}")


def get_llm_status() -> dict:
    """Get status of all LLM backends."""
    ollama = OllamaBackend()

    return {
        "current": _llm_backend.name if _llm_backend else None,
        "backends": {
            "ollama": {
                "available": ollama.is_available(),
                "models": ollama.list_models() if ollama.is_available() else [],
            },
            "openai": {
                "available": bool(os.environ.get("OPENAI_API_KEY")),
                "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            },
            "anthropic": {
                "available": bool(os.environ.get("ANTHROPIC_API_KEY")),
                "model": os.environ.get("ANTHROPIC_MODEL", "claude-3-haiku-20240307"),
            },
        },
    }
