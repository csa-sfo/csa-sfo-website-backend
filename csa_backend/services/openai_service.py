import asyncio
import backoff
import logging
from typing import Any, Iterable
from config.logging import setup_logging
from config.settings import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_CONCURRENCY, OPENAI_MAX_BACKOFF_TIME
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from openai import APIError, APIConnectionError, APITimeoutError, RateLimitError

setup_logging()

_semaphore = asyncio.Semaphore(OPENAI_CONCURRENCY)


def _log_backoff(details):
    logging.warning(
        "OpenAI retry %s for %s: %s",
        details["tries"],
        details["target"].__name__,
        details["exception"]
    )


def _normalize_history(history: Any) -> list[BaseMessage]:
    """Convert mixed history formats into LangChain messages."""
    if not history:
        return []

    messages: list[BaseMessage] = []

    def add_message(content: str, is_ai: bool):
        content = (content or "").strip()
        if not content:
            return
        messages.append(AIMessage(content=content) if is_ai else HumanMessage(content=content))

    # History may be a string, list of strings, or list of dicts with user/bot keys.
    items: Iterable[Any]
    if isinstance(history, str):
        items = [history]
    elif isinstance(history, Iterable):
        items = history
    else:
        return messages

    for item in items:
        if isinstance(item, dict):
            if "user" in item:
                add_message(str(item.get("user", "")), is_ai=False)
            if "bot" in item:
                add_message(str(item.get("bot", "")), is_ai=True)
            continue

        if not isinstance(item, str):
            continue

        lowered = item.lower()
        if lowered.startswith("bot:"):
            add_message(item.split(":", 1)[1] if ":" in item else item, is_ai=True)
        elif lowered.startswith("user:"):
            add_message(item.split(":", 1)[1] if ":" in item else item, is_ai=False)
        else:
            # Default to treating as user message
            add_message(item, is_ai=False)

    return messages


@backoff.on_exception(
    backoff.expo,
    (APITimeoutError, APIError, APIConnectionError, RateLimitError),
    max_time=OPENAI_MAX_BACKOFF_TIME,
    jitter=backoff.full_jitter,
    on_backoff=logging.exception
)
def _sync_completion(model: str, messages: list[BaseMessage], temperature: float, max_tokens: int):
    llm = ChatOpenAI(
        api_key=OPENAI_API_KEY,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return llm.invoke(messages)


async def run_openai_prompt(
    prompt: str,
    model: str = OPENAI_MODEL,
    temperature: float = 0.7,
    max_tokens: int = 300,
    system_prompt: str = "You are a helpful AI assistant.",
    history: Any = None,
) -> str:
    """Run an LLM call using LangChain ChatOpenAI with optional chat history."""
    base_messages: list[BaseMessage] = [SystemMessage(content=system_prompt)]
    base_messages.extend(_normalize_history(history))
    base_messages.append(HumanMessage(content=prompt))

    async with _semaphore:
        resp = await asyncio.to_thread(
            _sync_completion,
            model=model,
            messages=base_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    return (resp.content or "").strip()