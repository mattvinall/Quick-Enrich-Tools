from app.config import settings
from app.services.llm.base import BaseLLMProvider


def get_llm_provider() -> BaseLLMProvider:
    if settings.llm_provider == "openai":
        from app.services.llm.openai_provider import OpenAIProvider
        return OpenAIProvider()
    else:
        from app.services.llm.gemini import GeminiProvider
        return GeminiProvider()
