"""
Ollama Local HTTP API Provider and Conversation Service for SoulShell Terminal (Section 5).
Requirements satisfied:
- Configurable Ollama base URL (`config.ollama_url`)
- Automatic detection of whether the local Ollama server is available
- Fetch locally installed models from `/api/tags`
- Allow user to select a model
- Provide helpful setup instructions when Ollama is unavailable
- Streaming and synchronous responses via `/api/chat`
- Support conversation context and local SQLite persistence
- Handle network errors, timeouts, missing models, and malformed JSON gracefully
- Never claim AI is working when disconnected, and never send data to external cloud APIs
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterator, List, Optional
from urllib.parse import urlparse

import httpx

from soulshell.ai.personality import PersonalityEngine
from soulshell.core.config import SoulConfig
from soulshell.database.db import ConversationRecord, DatabaseManager, MessageRecord

OLLAMA_SETUP_GUIDE = (
    "Local Ollama AI service is currently unreachable.\n"
    "To enable local AI in SoulShell Terminal:\n"
    "  1. Install Ollama:  curl -fsSL https://ollama.com/install.sh | sh  (or visit https://ollama.com/download)\n"
    "  2. Start server:    ollama serve\n"
    "  3. Pull a model:    ollama pull llama3.2   (or `ollama pull mistral` / `ollama pull qwen2.5-coder:7b`)\n"
    "  4. Select model:    config set model llama3.2"
)


class AIProviderError(Exception):
    """Raised when the local AI provider is unreachable, times out, or returns an error."""

    def __init__(self, message: str, recoverable: bool = True, details: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.recoverable = recoverable
        self.details = details


@dataclass
class ModelInfo:
    """Metadata for a locally installed Ollama model."""

    name: str
    size_bytes: int = 0
    family: str = ""
    parameter_size: str = ""
    quantization_level: str = ""
    modified_at: str = ""

    @property
    def size_human(self) -> str:
        if self.size_bytes <= 0:
            return "Unknown"
        gb = self.size_bytes / (1024**3)
        if gb >= 1.0:
            return f"{gb:.2f} GB"
        mb = self.size_bytes / (1024**2)
        return f"{mb:.1f} MB"


@dataclass
class ProviderStatus:
    """Real-time availability status of the local Ollama server and configured model."""

    provider_name: str
    endpoint: str
    is_local: bool
    runtime_available: bool
    models_installed: List[ModelInfo] = field(default_factory=list)
    selected_model: str = ""
    selected_model_available: bool = False
    error_message: str = ""
    setup_instructions: str = ""


@dataclass
class GenerationResponse:
    """Result from a local AI chat completion request."""

    content: str
    model: str
    provider: str
    done: bool = True
    total_duration_ms: Optional[float] = None


class AIProvider(ABC):
    """Abstract interface for local AI providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return display name of provider."""

    @property
    @abstractmethod
    def is_local(self) -> bool:
        """Return True if endpoint is local."""

    @abstractmethod
    def check_status(self, selected_model: str = "") -> ProviderStatus:
        """Check server reachability and model installation status."""

    @abstractmethod
    def list_models(self) -> List[ModelInfo]:
        """Return list of installed models."""

    @abstractmethod
    def generate_chat(
        self,
        messages: List[Dict[str, str]],
        model: str,
        system_prompt: str = "",
        temperature: float = 0.7,
    ) -> GenerationResponse:
        """Generate synchronous chat response."""

    @abstractmethod
    def stream_chat(
        self,
        messages: List[Dict[str, str]],
        model: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> Iterator[str]:
        """Yield streaming response chunks."""


class OllamaProvider(AIProvider):
    """Local Ollama HTTP API client."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        timeout: int = 60,
        max_retries: int = 1,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        self.base_url = (base_url or "http://127.0.0.1:11434").strip().rstrip("/")
        self.timeout = max(5, int(timeout))
        self.max_retries = max(0, int(max_retries))
        self._client = http_client

    @property
    def provider_name(self) -> str:
        return "Ollama (Local HTTP API)"

    @property
    def is_local(self) -> bool:
        parsed = urlparse(self.base_url)
        host = (parsed.hostname or "").lower()
        return host in ("127.0.0.1", "localhost", "::1", "0.0.0.0")

    def list_models(self) -> List[ModelInfo]:
        """Fetch locally installed models from GET /api/tags."""
        url = f"{self.base_url}/api/tags"
        last_exc: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                if self._client is not None:
                    resp = self._client.get(url)
                else:
                    with httpx.Client(timeout=4.0) as client:
                        resp = client.get(url)

                if resp.status_code != 200:
                    raise AIProviderError(
                        f"Ollama server at {self.base_url} returned HTTP {resp.status_code}.",
                        recoverable=True,
                        details=resp.text[:250],
                    )
                data = resp.json()
                if not isinstance(data, dict):
                    raise AIProviderError("Malformed JSON response from Ollama /api/tags.")
                raw_models = data.get("models", [])
                if not isinstance(raw_models, list):
                    raise AIProviderError("Malformed 'models' list in Ollama /api/tags.")

                models: List[ModelInfo] = []
                for m in raw_models:
                    if not isinstance(m, dict):
                        continue
                    details = m.get("details") if isinstance(m.get("details"), dict) else {}
                    models.append(
                        ModelInfo(
                            name=str(m.get("name", "")),
                            size_bytes=int(m.get("size", 0) or 0),
                            family=str(details.get("family", "")),
                            parameter_size=str(details.get("parameter_size", "")),
                            quantization_level=str(details.get("quantization_level", "")),
                            modified_at=str(m.get("modified_at", "")),
                        )
                    )
                return models
            except AIProviderError:
                raise
            except (httpx.RequestError, ValueError, KeyError) as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    time.sleep(0.1)

        raise AIProviderError(
            f"Ollama is not reachable at {self.base_url}.",
            recoverable=True,
            details=str(last_exc) if last_exc else "",
        )

    def check_status(self, selected_model: str = "") -> ProviderStatus:
        """Check whether Ollama is running and whether the configured model is installed."""
        target = (selected_model or "").strip()
        try:
            models = self.list_models()
            installed_names = [m.name for m in models]
            if not target and installed_names:
                target = installed_names[0]

            model_ok = bool(
                target
                and any(
                    name == target or name.split(":")[0] == target.split(":")[0]
                    for name in installed_names
                )
            )
            err = ""
            setup = ""
            if not models:
                err = "Ollama is running, but no local models are installed."
                setup = "Run `ollama pull llama3.2` in your terminal to download a model."
            elif target and not model_ok:
                err = f"Selected model '{target}' is not installed locally."
                setup = (
                    f"Run `ollama pull {target}` or switch to an installed model: "
                    f"{', '.join(installed_names)}"
                )

            return ProviderStatus(
                provider_name=self.provider_name,
                endpoint=self.base_url,
                is_local=self.is_local,
                runtime_available=True,
                models_installed=models,
                selected_model=target,
                selected_model_available=model_ok,
                error_message=err,
                setup_instructions=setup,
            )
        except AIProviderError as exc:
            return ProviderStatus(
                provider_name=self.provider_name,
                endpoint=self.base_url,
                is_local=self.is_local,
                runtime_available=False,
                models_installed=[],
                selected_model=target,
                selected_model_available=False,
                error_message=exc.message,
                setup_instructions=OLLAMA_SETUP_GUIDE,
            )

    @staticmethod
    def _build_payload(
        messages: List[Dict[str, str]],
        model: str,
        system_prompt: str,
        temperature: float,
        stream: bool,
    ) -> Dict[str, Any]:
        clean_model = (model or "").strip()
        if not clean_model:
            raise AIProviderError(
                "No AI model is configured. Use `config set model <name>` after pulling a model in Ollama.",
                recoverable=True,
            )
        formatted: List[Dict[str, str]] = []
        if system_prompt and system_prompt.strip():
            formatted.append({"role": "system", "content": system_prompt.strip()})
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if content and content.strip():
                formatted.append({"role": role, "content": content})
        if not any(m["role"] == "user" for m in formatted):
            raise AIProviderError("Prompt cannot be empty.", recoverable=True)

        return {
            "model": clean_model,
            "messages": formatted,
            "stream": stream,
            "options": {"temperature": float(temperature)},
        }

    def generate_chat(
        self,
        messages: List[Dict[str, str]],
        model: str,
        system_prompt: str = "",
        temperature: float = 0.7,
    ) -> GenerationResponse:
        payload = self._build_payload(
            messages=messages,
            model=model,
            system_prompt=system_prompt,
            temperature=temperature,
            stream=False,
        )
        url = f"{self.base_url}/api/chat"
        last_exc: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                if self._client is not None:
                    resp = self._client.post(url, json=payload)
                else:
                    with httpx.Client(timeout=float(self.timeout)) as client:
                        resp = client.post(url, json=payload)

                if resp.status_code == 404:
                    raise AIProviderError(
                        f"Model '{model}' is not installed in Ollama. Run `ollama pull {model}` first.",
                        recoverable=False,
                    )
                if resp.status_code != 200:
                    raise AIProviderError(
                        f"Ollama returned HTTP {resp.status_code}.",
                        recoverable=True,
                        details=resp.text[:250],
                    )
                data = resp.json()
                if not isinstance(data, dict) or "message" not in data:
                    raise AIProviderError(
                        "Received malformed response payload from Ollama /api/chat.",
                        recoverable=False,
                    )
                msg_obj = data.get("message") or {}
                content = str(msg_obj.get("content", ""))
                dur_ns = data.get("total_duration")
                dur_ms = float(dur_ns) / 1_000_000.0 if dur_ns else None
                return GenerationResponse(
                    content=content,
                    model=str(data.get("model", model)),
                    provider=self.provider_name,
                    done=bool(data.get("done", True)),
                    total_duration_ms=dur_ms,
                )
            except AIProviderError as exc:
                if not exc.recoverable:
                    raise
                last_exc = exc
            except (httpx.TimeoutException,) as exc:
                raise AIProviderError(
                    f"Ollama request timed out after {self.timeout}s. "
                    "Increase `request_timeout` via `config set request_timeout 120` or try a smaller model.",
                    recoverable=True,
                ) from exc
            except (httpx.RequestError, ValueError) as exc:
                last_exc = exc

        raise AIProviderError(
            f"Could not connect to Ollama at {self.base_url}.\n{OLLAMA_SETUP_GUIDE}",
            recoverable=True,
            details=str(last_exc) if last_exc else "",
        )

    def stream_chat(
        self,
        messages: List[Dict[str, str]],
        model: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> Iterator[str]:
        payload = self._build_payload(
            messages=messages,
            model=model,
            system_prompt=system_prompt,
            temperature=temperature,
            stream=True,
        )
        url = f"{self.base_url}/api/chat"
        try:
            if self._client is not None:
                resp = self._client.post(url, json=payload)
                if resp.status_code == 404:
                    raise AIProviderError(
                        f"Model '{model}' is not installed in Ollama. Run `ollama pull {model}`.",
                        recoverable=False,
                    )
                if resp.status_code != 200:
                    raise AIProviderError(
                        f"Ollama streaming failed with HTTP {resp.status_code}.",
                        recoverable=True,
                    )
                for line in resp.text.splitlines():
                    if should_cancel and should_cancel():
                        break
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if "error" in chunk:
                        raise AIProviderError(str(chunk["error"]), recoverable=False)
                    token = chunk.get("message", {}).get("content", "")
                    if token:
                        yield str(token)
                    if chunk.get("done"):
                        break
                return

            with httpx.Client(timeout=float(self.timeout)) as client:
                with client.stream("POST", url, json=payload) as response:
                    if response.status_code == 404:
                        raise AIProviderError(
                            f"Model '{model}' is not installed in Ollama. Run `ollama pull {model}`.",
                            recoverable=False,
                        )
                    if response.status_code != 200:
                        raise AIProviderError(
                            f"Ollama streaming failed with HTTP {response.status_code}.",
                            recoverable=True,
                        )
                    for line in response.iter_lines():
                        if should_cancel and should_cancel():
                            break
                        if not line:
                            continue
                        chunk = json.loads(line)
                        if "error" in chunk:
                            raise AIProviderError(str(chunk["error"]), recoverable=False)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            yield str(token)
                        if chunk.get("done"):
                            break
        except AIProviderError:
            raise
        except httpx.TimeoutException as exc:
            raise AIProviderError(
                f"Ollama streaming timed out after {self.timeout}s.",
                recoverable=True,
            ) from exc
        except (httpx.RequestError, ValueError) as exc:
            raise AIProviderError(
                f"Ollama connection failed at {self.base_url}.\n{OLLAMA_SETUP_GUIDE}",
                recoverable=True,
                details=str(exc),
            ) from exc


class ConversationService:
    """Coordinates multi-turn conversation context, personality prompts, and SQLite storage."""

    def __init__(
        self,
        db: DatabaseManager,
        provider: AIProvider,
        config: SoulConfig,
    ) -> None:
        self.db = db
        self.provider = provider
        self.config = config.validate()
        self.personality = PersonalityEngine(self.config)
        self.current_conversation: Optional[ConversationRecord] = None

    def update_config(self, config: SoulConfig) -> None:
        self.config = config.validate()
        self.personality.config = self.config
        if isinstance(self.provider, OllamaProvider):
            self.provider.base_url = self.config.ollama_url
            self.provider.timeout = self.config.request_timeout

    def start_new_conversation(self, title: str = "New Haunted Session") -> ConversationRecord:
        self.current_conversation = self.db.create_conversation(
            title=title,
            soul_mode=self.config.personality_mode,
            model=self.config.model,
            save_history=self.config.save_history,
        )
        return self.current_conversation

    def get_context_messages(self) -> List[Dict[str, str]]:
        if not self.current_conversation:
            return []
        return [
            {"role": m.role, "content": m.content}
            for m in self.current_conversation.messages[-16:]
        ]

    def chat(
        self,
        user_prompt: str,
        stream_callback: Optional[Callable[[str], None]] = None,
        task_instructions: str = "",
    ) -> MessageRecord:
        clean_prompt = (user_prompt or "").strip()
        if not clean_prompt:
            raise ValueError("Prompt cannot be empty.")

        if self.current_conversation is None:
            self.start_new_conversation(title=clean_prompt.splitlines()[0][:60])

        assert self.current_conversation is not None

        user_msg = self.db.add_message(
            conversation_id=self.current_conversation.id,
            role="user",
            content=clean_prompt,
            model=self.config.model,
            soul_mode=self.config.personality_mode,
            save_history=self.config.save_history,
        )
        self.current_conversation.messages.append(user_msg)

        sys_prompt = self.personality.get_system_prompt(
            task_instructions=task_instructions
        )
        context_msgs = self.get_context_messages()

        if stream_callback is not None:
            chunks: List[str] = []
            for token in self.provider.stream_chat(
                messages=context_msgs,
                model=self.config.model,
                system_prompt=sys_prompt,
                temperature=self.config.temperature,
            ):
                chunks.append(token)
                stream_callback(token)
            reply_text = "".join(chunks).strip()
        else:
            resp = self.provider.generate_chat(
                messages=context_msgs,
                model=self.config.model,
                system_prompt=sys_prompt,
                temperature=self.config.temperature,
            )
            reply_text = resp.content.strip()

        assistant_msg = self.db.add_message(
            conversation_id=self.current_conversation.id,
            role="assistant",
            content=reply_text,
            model=self.config.model,
            soul_mode=self.config.personality_mode,
            save_history=self.config.save_history,
        )
        self.current_conversation.messages.append(assistant_msg)
        return assistant_msg
