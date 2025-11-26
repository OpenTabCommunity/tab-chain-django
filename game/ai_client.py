# ai_client.py
import asyncio
import json
import logging
import random
import re
import time
from typing import Any, Dict, List, Optional, TypedDict, Tuple

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

# --- types ---
class AIResponse(TypedDict, total=False):
    result: bool
    message: str

# --- module-level shared client + init lock ---
_client: Optional[httpx.AsyncClient] = None
_client_lock = asyncio.Lock()

# --- circuit breaker state (use monotonic time) ---
_failure_count = 0
_last_failure_monotonic = 0.0
_CIRCUIT_THRESHOLD = getattr(settings, "AI_CIRCUIT_THRESHOLD", 6)
_CIRCUIT_COOLDOWN = getattr(settings, "AI_CIRCUIT_COOLDOWN", 30.0)

# --- defaults (configurable from Django settings) ---
_AI_MODEL = getattr(settings, "AI_MODEL", "gemma3")
_AI_MAX_TOKENS = getattr(settings, "AI_MAX_TOKENS", 120)
_AI_RETRY_ATTEMPTS = getattr(settings, "AI_RETRY_ATTEMPTS", 3)
_AI_TIMEOUT = getattr(settings, "AI_TIMEOUT", 10.0)
_AI_MAX_KEEPALIVE = getattr(settings, "AI_MAX_KEEPALIVE", 10)
_AI_MAX_CONNECTIONS = getattr(settings, "AI_MAX_CONNECTIONS", 50)
_AI_STOP = getattr(settings, "AI_STOP", ["\n\n"])

# --- helpers for circuit breaker ---
def _is_circuit_open() -> bool:
    global _failure_count, _last_failure_monotonic
    if _failure_count < _CIRCUIT_THRESHOLD:
        return False
    # cooldown after last failure
    if time.monotonic() - _last_failure_monotonic > _CIRCUIT_COOLDOWN:
        _failure_count = 0
        return False
    return True


def _record_failure() -> None:
    global _failure_count, _last_failure_monotonic
    _failure_count += 1
    _last_failure_monotonic = time.monotonic()


def _record_success() -> None:
    global _failure_count
    _failure_count = 0


# --- shared httpx client init ---
async def get_shared_client() -> httpx.AsyncClient:
    global _client
    if _client is not None:
        return _client

    async with _client_lock:
        if _client is None:
            # adapt timeout
            timeout_value = _AI_TIMEOUT
            if isinstance(timeout_value, (int, float)):
                timeout = httpx.Timeout(timeout_value)
            else:
                timeout = httpx.Timeout(**timeout_value)  # type: ignore[arg-type]

            limits = httpx.Limits(max_keepalive_connections=_AI_MAX_KEEPALIVE, max_connections=_AI_MAX_CONNECTIONS)

            base_url = getattr(settings, "AI_SERVICE_URL", "")
            if not base_url:
                # create client without base_url but log error later when used
                logger.warning("AI_SERVICE_URL not set; client created without base_url")

            _client = httpx.AsyncClient(base_url=base_url, timeout=timeout, limits=limits, headers={"Content-Type": "application/json"})
            logger.info("AI AsyncClient initialized (base_url=%r).", base_url)
    return _client


# --- parsing helpers ---
# Pattern to parse "boolean - explanation" or "boolean: explanation" etc.
_RESULT_EXPLANATION_RE = re.compile(r"^\s*(?P<boolean>true|false|yes|no|1|0)\b\s*[-:]\s*(?P<explanation>.+)$", re.I)


def _parse_result_and_explanation_from_field(value: str) -> Tuple[bool, str]:
    """
    Parse a string like "true - because X" or "false: explanation" and return (bool, explanation).
    Accepts true/false/yes/no/1/0 as boolean tokens (case-insensitive).
    Raises ValueError if parsing fails.
    """
    if not isinstance(value, str):
        raise ValueError("results field is not a string")

    value = value.strip()
    # try "true - explanation"
    m = _RESULT_EXPLANATION_RE.match(value)
    if m:
        b = m.group("boolean").lower()
        explanation = m.group("explanation").strip()
        truth = b in ("true", "yes", "1")
        return truth, explanation

    # If the whole string is a single boolean token (no explanation)
    lower = value.lower()
    if lower in ("true", "yes", "1"):
        return True, ""
    if lower in ("false", "no", "0"):
        return False, ""

    # not parseable
    raise ValueError("cannot parse boolean/explanation from results field")


def _extract_model_text(outer: Dict[str, Any]) -> Optional[str]:
    """
    Best-effort extraction: many local LLM wrappers vary in shape.
    Prefer keys: "response", "text", "results", "output".
    If the outer value already is a string (not dict) return it directly.
    """
    # if outer itself is string-ish, handle earlier. But we expect dict here.
    for key in ("response", "text", "output"):
        v = outer.get(key)
        if isinstance(v, str) and v.strip():
            return v
        # some wrappers return list/choices; try first item
        if isinstance(v, list) and v:
            first = v[0]
            if isinstance(first, str):
                return first
            if isinstance(first, dict) and "text" in first:
                return first.get("text")
    # fallback: if outer has a top-level 'results' string, return it
    v = outer.get("results")
    if isinstance(v, str):
        return v
    # nothing useful
    return None


def _parse_model_text_response(text: str) -> Dict[str, Any]:
    """
    Attempt to parse the model's textual output to a JSON-like dict.
    Accepts:
      - direct JSON text: '{"results":"true - explanation", ...}'
      - a plain "true - explanation" string (return {'results': <that string>})
      - embedded JSON inside other text (first { ... } found)
    If nothing parseable, raise ValueError.
    """
    if not isinstance(text, str):
        raise ValueError("model text is not a string")

    s = text.strip()

    # 1) direct JSON
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    # 2) extract first {...}
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            obj = json.loads(s[start : end + 1])
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

    # 3) treat entire text as plain results string
    # put it into a dict under 'results' so callers can parse uniformly
    return {"results": s}

async def get_ai_decision(
    move: str,
    chain: List[str],
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    retry_attempts: Optional[int] = None,
) -> AIResponse:
    """
    Query the local LLM judging service. Returns {"result": bool, "message": "<explanation>"} on success,
    or {"result": False, "message": "<error...>"} with result False for error cases (consistent).
    """
    if _is_circuit_open():
        logger.warning("AI circuit open: fast-failing request.")
        return {"result": False, "message": "AI service temporarily unavailable"}

    base_url = getattr(settings, "AI_SERVICE_URL", None)
    if not base_url:
        logger.error("AI_SERVICE_RL missing in settings.")
        return {"result": False, "message": "AI service not configured"}

    model = model or _AI_MODEL
    max_tokens = max_tokens or _AI_MAX_TOKENS
    retry_attempts = retry_attempts or _AI_RETRY_ATTEMPTS

    client = await get_shared_client()

    # send structured input (no prompt). Many local LLM endpoints accept a JSON 'input' field.
    payload = {
        "model": model,
        "prompt": f'{{"move": {move}, "chain": {chain}}}',
        "stream": False,
        "max_tokens": max_tokens,
        "stop": _AI_STOP,
    }

    # Exponential backoff with jitter
    for attempt in range(1, retry_attempts + 1):
        try:
            logger.info(payload)
            resp = await client.post("/api/generate", json=payload)
            # Raise for 4xx/5xx
            resp.raise_for_status()
            _record_success()

            # Outer response is expected to be JSON (wrapper)
            try:
                outer = resp.json()
                logger.info(outer)
            except Exception as e:
                # fallback: use raw text
                text = resp.text if hasattr(resp, "text") else (await resp.aread()).decode(errors="ignore")
                logger.warning("AI returned non-JSON wrapper; falling back to raw text. err=%s", e)
                outer = {"response": text}

            # best-effort extraction of model text
            model_text = _extract_model_text(outer)
            logger.info("Model text extracted: %.200s", model_text or "<empty>")
            if model_text is None:
                raise ValueError("no model text found in response wrapper")

            parsed = _parse_model_text_response(model_text)
            logger.info(parsed)

            # Prefer a 'results' field in the model output (per your spec)
            if "results" in parsed:
                try:
                    boolean, explanation = _parse_result_and_explanation_from_field(parsed["results"])
                    logger.info(boolean)
                    logger.info(explanation)
                    return {"result": boolean, "message": explanation}
                except ValueError:
                    # parsed['results'] might be free-form text — fall through to other heuristics
                    logger.debug("Failed to parse parsed['results']: %r", parsed.get("results"))

            # If parsed contains explicit fields like 'result' (boolean/text) and 'explanation' or 'message'
            if "result" in parsed:
                raw_result = parsed["result"]
                # Accept boolean or textual true/false
                if isinstance(raw_result, bool):
                    msg = parsed.get("message") or parsed.get("explanation") or ""
                    return {"result": raw_result, "message": str(msg)}
                if isinstance(raw_result, str):
                    try:
                        # accept "true"/"false" strings
                        b, _ = _parse_result_and_explanation_from_field(raw_result + " - ")
                        msg = parsed.get("message") or parsed.get("explanation") or ""
                        return {"result": b, "message": str(msg)}
                    except ValueError:
                        logger.debug("Could not parse string 'result' field: %r", raw_result)

            # fallback: if parsed has a single string that looks like "true - explanation"
            if len(parsed) == 1:
                only_val = next(iter(parsed.values()))
                if isinstance(only_val, str):
                    try:
                        b, explanation = _parse_result_and_explanation_from_field(only_val)
                        return {"result": b, "message": explanation}
                    except ValueError:
                        logger.debug("Single-value parsed object not boolean/explanation: %r", only_val)

            # NEW FALLBACK: the model produced a free-form textual response (like your example).
            # Return the raw model text as the message so callers can use it.
            logger.info("Model output did not contain a parseable boolean result; returning raw text as message.")
            return {"result": True, "message": model_text}

        except httpx.HTTPStatusError as e:
            status = e.response.status_code if e.response is not None else None
            body = e.response.text[:1000] if (e.response is not None and hasattr(e.response, "text")) else ""
            logger.warning("AI HTTP error %s (attempt %d/%d). Body: %s", status, attempt, retry_attempts, body)

            if status == 429:
                # honor Retry-After header if present
                retry_after = e.response.headers.get("Retry-After") if e.response is not None else None
                wait = None
                if retry_after:
                    try:
                        wait = int(retry_after)
                    except Exception:
                        try:
                            wait = float(retry_after)
                        except Exception:
                            wait = None
                if wait is None:
                    wait = min(2 ** attempt, 30)
                _record_failure()
                await asyncio.sleep(wait + random.uniform(0, 0.5))
                continue

            if status and 500 <= status < 600:
                _record_failure()
                jitter = random.uniform(0, 0.3)
                await asyncio.sleep(min(0.5 * (2 ** (attempt - 1)) + jitter, 10.0))
                continue

            logger.error("Non-retriable HTTP error from AI: %s", status, exc_info=True)
            _record_failure()
            return {"result": False, "message": f"AI HTTP error: {status}"}

        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.warning("Network error to AI (attempt %d/%d): %s", attempt, retry_attempts, e)
            _record_failure()
            await asyncio.sleep(min(0.25 * (2 ** (attempt - 1)) + random.uniform(0, 0.3), 10.0))
            continue

        except ValueError as e:
            # parsing / validation failure -> don't retry (model gave bad shape)
            logger.error("Invalid AI/model response: %s", e, exc_info=True)
            _record_failure()
            return {"result": False, "message": f"Invalid model response: {e}"}

        except Exception:
            # unexpected; attempt again up to retry_attempts
            logger.exception("Unexpected error while calling AI (attempt %d/%d)", attempt, retry_attempts)
            _record_failure()
            await asyncio.sleep(min(0.5 * attempt + random.uniform(0, 0.5), 10.0))
            continue

    logger.error("AI unreachable after %d attempts", retry_attempts)
    return {"result": False, "message": "AI service unreachable"}

# optional shutdown helper
async def close_shared_client() -> None:
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        except Exception:
            logger.exception("Error closing AI httpx client")
        _client = None

