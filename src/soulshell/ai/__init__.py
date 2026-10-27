"""AI integration and personality package for SoulShell Terminal."""
from soulshell.ai.ollama_provider import (
    AIProvider,
    AIProviderError,
    ConversationService,
    GenerationResponse,
    ModelInfo,
    OllamaProvider,
    ProviderStatus,
)
from soulshell.ai.personality import (
    SOUL_MODES,
    PersonalityEngine,
    SoulModeMetadata,
    build_system_prompt,
)

__all__ = [
    "AIProvider",
    "AIProviderError",
    "ModelInfo",
    "ProviderStatus",
    "GenerationResponse",
    "OllamaProvider",
    "ConversationService",
    "SOUL_MODES",
    "SoulModeMetadata",
    "PersonalityEngine",
    "build_system_prompt",
]
