import httpx
import asyncio
import logging
from typing import TypedDict
from django.conf import settings
from httpx import ConnectError, TimeoutException, HTTPStatusError

logger = logging.getLogger(__name__)


class AIResponse(TypedDict, total=False):
    result: str
    message: str
    explanation: str


_client: httpx.AsyncClient | None = None


async def get_shared_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=settings.AI_SERVICE_URL,
            timeout=settings.AI_TIMEOUT,
        )
    return _client


async def get_ai_decision(move: str, retry_attempts: int = 3) -> AIResponse:
    """Call the external AI decision service asynchronously and return structured result."""
    if not settings.AI_SERVICE_URL:
        logger.error("AI_SERVICE_URL not configured in settings.")
        return {"result": "error", "message": "AI service not configured"}

    client = await get_shared_client()
    for attempt in range(retry_attempts):
        try:
            response = await client.post("/decision", json={"move": move})
            response.raise_for_status()

            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Invalid JSON structure from AI")

            result = data.get("result")
            message = data.get("message")
            explanation = data.get("explanation")

            if result not in {"correct", "lost", "tie"}:
                raise ValueError(f"Unexpected result value: {result}")

            return {
                "result": result,
                "message": message or "",
                "explanation": explanation or "",
            }

        except (ConnectError, TimeoutException) as e:
            logger.warning(f"AI connection attempt {attempt + 1} failed: {e}")
            await asyncio.sleep(0.3 * (attempt + 1))
        except (HTTPStatusError, ValueError) as e:
            logger.error("Invalid response from AI service", exc_info=True)
            return {"result": "error", "message": str(e)}

    logger.error("All AI connection attempts failed after retries.")
    return {"result": "error", "message": "AI service unreachable"}
