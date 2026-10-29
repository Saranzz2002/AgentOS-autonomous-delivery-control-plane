import os


class LLMNotConfigured(RuntimeError):
    pass


class LLMClient:
    """Provider boundary for model calls; agents depend on this interface only."""

    def __init__(self) -> None:
        self.api_key = os.getenv("GROQ_API_KEY", "").strip()
        self.model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        json_mode: bool = False,
    ) -> str:
        if not self.api_key:
            raise LLMNotConfigured("GROQ_API_KEY is not configured.")
        from groq import Groq

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        options = {"response_format": {"type": "json_object"}} if json_mode else {}
        response = Groq(api_key=self.api_key).chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.2,
            **options,
        )
        return response.choices[0].message.content or ""
