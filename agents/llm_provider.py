"""Provider-agnostic LLM factory.

Imports are intentionally lazy so an API provider does not load the Ollama
native dependency on Windows.
"""


def get_llm(provider="local", api_key=None, model=None, base_url=None):
    provider = (provider or "local").lower().strip()

    if provider == "local":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=model or "qwen3:8b",
            temperature=0.1,
        )

    if provider == "xai":
        if not api_key:
            raise ValueError("xAI API key is required when provider='xai'.")
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model or "grok-4.1-fast",
            temperature=0.1,
            api_key=api_key,
            base_url="https://api.x.ai/v1",
        )

    if provider == "openai":
        if not api_key:
            raise ValueError("OpenAI API key is required when provider='openai'.")
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model or "gpt-5",
            temperature=0.1,
            api_key=api_key,
        )

    if provider == "gemini":
        if not api_key:
            raise ValueError("Gemini API key is required when provider='gemini'.")
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=model or "gemini-3.6-flash",
            temperature=0.1,
            google_api_key=api_key,
        )

    if provider == "groq":
        if not api_key:
            raise ValueError("Groq API key is required when provider='groq'.")
        from langchain_groq import ChatGroq
        return ChatGroq(
            model=model or "openai/gpt-oss-120b",
            temperature=0.2,
            api_key=api_key,
        )

    if provider == "custom":
        if not api_key:
            raise ValueError("API key is required when provider='custom'.")
        if not base_url:
            raise ValueError("Base URL is required when provider='custom'.")
        if not model:
            raise ValueError("Model is required when provider='custom'.")
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model,
            temperature=0.1,
            api_key=api_key,
            base_url=base_url,
        )

    raise ValueError(
        f"Unsupported LLM provider: {provider}. "
        "Use: local, openai, xai, gemini, groq, custom."
    )
