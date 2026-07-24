"""
core/providers/llm/groq_provider.py

Groq implementation of LLMProvider. This is a direct port of the
request-building logic from the original post.py's generate_story(),
generalized to accept any system/user prompt rather than a
horror-specific hardcoded one.
"""
import requests
from .base import LLMProvider


class GroqProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        self.api_key = api_key
        self.model = model

    def generate(self, system_prompt: str, user_prompt: str,
                 temperature: float = 0.9, max_tokens: int = 900) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        res = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers, json=payload, timeout=30,
        )
        res.raise_for_status()
        return res.json()["choices"][0]["message"]["content"].strip()
