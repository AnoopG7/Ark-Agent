"""Chat model construction (Groq) and resilient invocation."""

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.core.config import Settings


class LLMNotConfiguredError(RuntimeError):
    pass


def build_chat_model(settings: Settings) -> BaseChatModel:
    if settings.groq_api_key is None or not settings.groq_api_key.get_secret_value():
        raise LLMNotConfiguredError("GROQ_API_KEY is not set. Add it to the .env file.")
    from langchain_groq import ChatGroq

    return ChatGroq(
        model=settings.groq_model,
        api_key=settings.groq_api_key,
        temperature=settings.llm_temperature,
        timeout=settings.llm_timeout_s,
        max_retries=settings.llm_max_retries,
    )


def _is_retryable(exc: BaseException) -> bool:
    """Groq returns 400 ``tool_use_failed`` when the model emits a malformed tool call, and 429
    on rate limits. Both are worth retrying; other errors are not."""
    text = str(exc)
    return "tool_use_failed" in text or "rate_limit" in text or "429" in text


@retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    reraise=True,
)
def invoke_with_retry(model, messages: list[BaseMessage]) -> AIMessage:
    return model.invoke(messages)
