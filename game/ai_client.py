import httpx
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


async def get_ai_decision(move: str) -> dict:
    """
    Sends a move to external AI service and returns a dict like:
    {
        "result": "correct" | "lost",
        "message": "paper beats rock",
        "explanation": "paper covers rock"
    }
    """
    url = getattr(settings, "AI_SERVICE_URL", None)
    timeout = float(getattr(settings, "AI_TIMEOUT", 3.0))

    if not url:
        raise ValueError("AI_SERVICE_URL is not set in settings or .env")

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json={"move": move})
            response.raise_for_status()
            data = response.json()

            if not all(k in data for k in ("result", "message", "explanation")):
                raise ValueError(f"Invalid AI response schema: {data}")
            return data

    except httpx.TimeoutException:
        logger.warning("AI service timeout")
        return {"result": "error", "message": "AI timeout", "explanation": ""}
    except Exception as e:
        logger.error(f"AI service error: {e}")
        return {"result": "error", "message": "AI unavailable", "explanation": ""}
