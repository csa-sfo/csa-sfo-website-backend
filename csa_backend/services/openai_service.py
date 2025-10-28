import os, asyncio, backoff, logging
from config.logging import setup_logging
from config.settings import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_CONCURRENCY, OPENAI_MAX_BACKOFF_TIME
from openai import OpenAI, APIError, APIConnectionError, APITimeoutError, RateLimitError

setup_logging()

openai_client = OpenAI(api_key=OPENAI_API_KEY)
_semaphore = asyncio.Semaphore(OPENAI_CONCURRENCY)

    
def _log_backoff(details):
    logging.warning(
        "OpenAI retry %s for %s: %s",
        details["tries"],
        details["target"].__name__,
        details["exception"]
    )

@backoff.on_exception(
    backoff.expo,
    (APITimeoutError, APIError, APIConnectionError, RateLimitError),
    max_time=OPENAI_MAX_BACKOFF_TIME,
    jitter=backoff.full_jitter,
    on_backoff=logging.exception
)
def _sync_completion(model: str, messages: list, temperature: float, max_tokens: int):
    return openai_client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        n=1
    )

async def run_openai_prompt(
    prompt: str,
    model: str = OPENAI_MODEL,
    temperature: float = 0.7,
    max_tokens: int = 300,
    system_prompt: str = "You are a helpful AI assistant."
) -> str:
    async with _semaphore:
        resp = await asyncio.to_thread(
            _sync_completion,
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            max_tokens=max_tokens
        )
    return resp.choices[0].message.content.strip()