"""OpenAI LLM adapter. Pins model snapshot, seed, temperature; logs
system_fingerprint + token counts per call into AuditAnnotations.
"""

from __future__ import annotations

import os
import time
from typing import Optional

from openai import OpenAI

from agent.state import AuditAnnotations


FALLBACK_MODEL = "gpt-4o-mini"  # confirmed accessible in every OpenAI project tier
DEFAULT_TEMPERATURE = 0.1
DEFAULT_SEED = 42


def _resolve_model() -> str:
    """Prefer .env OPENAI_MODEL; fall back to a broadly-accessible default."""
    return os.environ.get("OPENAI_MODEL", FALLBACK_MODEL)


def _is_reasoning_family(model: str) -> bool:
    """gpt-5 / o1 / o3 / o4 series reject temperature + seed."""
    m = model.lower()
    return m.startswith(("gpt-5", "o1", "o3", "o4"))


_client: Optional[OpenAI] = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            # fall back to .env loading
            try:
                from dotenv import load_dotenv

                load_dotenv()
                api_key = os.environ.get("OPENAI_API_KEY")
            except ImportError:
                pass
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY missing. Set in environment or .env file."
            )
        _client = OpenAI(api_key=api_key)
    return _client


def invoke_json(
    system_prompt: str,
    user_prompt: str,
    annotations: AuditAnnotations,
    model: Optional[str] = None,
    temperature: float = DEFAULT_TEMPERATURE,
    seed: int = DEFAULT_SEED,
) -> str:
    """Call the LLM with JSON-response-format hint. Updates `annotations`
    in place: tokens_prompt, tokens_completion, llm_calls,
    system_fingerprint, wall_clock_seconds.

    Returns the raw string content of the response.
    """
    model = model or _resolve_model()
    client = get_client()

    kwargs = dict(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    if not _is_reasoning_family(model):
        kwargs["temperature"] = temperature
        kwargs["seed"] = seed

    t0 = time.time()
    # Retry transient network errors with exponential backoff.
    # Transient = APIConnectionError / APITimeoutError / RateLimitError /
    # InternalServerError / APIStatusError(5xx). Permanent errors (auth,
    # model_not_found, bad_request) still bubble up or trigger model fallback.
    max_retries = 5
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(**kwargs)
            break
        except Exception as exc:
            last_exc = exc
            msg = str(exc)
            exc_name = type(exc).__name__
            # Model access error → switch to fallback model and retry immediately
            if "model_not_found" in msg or "does not have access" in msg:
                kwargs["model"] = FALLBACK_MODEL
                if _is_reasoning_family(model) and not _is_reasoning_family(FALLBACK_MODEL):
                    kwargs["temperature"] = temperature
                    kwargs["seed"] = seed
                continue
            # Transient network/rate errors → exponential backoff
            transient_markers = (
                "APIConnectionError",
                "APITimeoutError",
                "RateLimitError",
                "InternalServerError",
                "ConnectionError",
                "ReadTimeout",
                "ServiceUnavailable",
            )
            is_transient = (
                any(m in exc_name for m in transient_markers)
                or "connection" in msg.lower()
                or "timeout" in msg.lower()
                or "rate limit" in msg.lower()
            )
            if is_transient and attempt < max_retries - 1:
                # 1s, 2s, 4s, 8s, 16s
                time.sleep(2 ** attempt)
                continue
            # Non-retriable or retries exhausted
            raise
    else:
        # Loop completed without break (all retries exhausted)
        if last_exc is not None:
            raise last_exc
    elapsed = time.time() - t0

    usage = response.usage
    fingerprint = response.system_fingerprint or response.model or ""
    content = (response.choices[0].message.content or "").strip()

    annotations["tokens_prompt"] = (
        annotations.get("tokens_prompt", 0) + (usage.prompt_tokens if usage else 0)
    )
    annotations["tokens_completion"] = (
        annotations.get("tokens_completion", 0)
        + (usage.completion_tokens if usage else 0)
    )
    annotations["llm_calls"] = annotations.get("llm_calls", 0) + 1
    annotations["system_fingerprint"] = fingerprint
    annotations["wall_clock_seconds"] = (
        annotations.get("wall_clock_seconds", 0.0) + elapsed
    )

    return content
