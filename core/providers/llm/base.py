"""
core/providers/llm/base.py

Every LLM backend (Groq, OpenAI, local Ollama, etc.) implements this
interface. The Story Engine only ever talks to LLMProvider -- it never
imports a vendor SDK directly. Swapping providers is a config change
(which provider class to instantiate), not a code change.
"""
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str,
                 temperature: float = 0.9, max_tokens: int = 900) -> str:
        """Return raw text completion from the model. Callers are
        responsible for parsing the response into structured data --
        this interface stays generic across providers."""
        raise NotImplementedError
