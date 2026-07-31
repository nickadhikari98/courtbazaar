import os
import httpx
import logging

logger = logging.getLogger(__name__)

N8N_WEBHOOK_URL = os.getenv(
    "N8N_WEBHOOK_URL",
    "http://localhost:5678/webhook/courtbazaar-events"
)


async def publish_event(event: str, payload: dict) -> bool:
    """
    Send an event to n8n. Best-effort: never raises — callers should treat
    n8n as a non-critical side channel and continue their own workflow
    regardless of the return value.

    Example:
        await publish_event(
            event="hearing_broadcast",
            payload={
                "hearing_id": "...",
                "court": "...",
                "user_id": "..."
            }
        )

    Returns True if n8n accepted the event, False otherwise.
    """

    body = {
        "event": event,
        "payload": payload,
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=3.0)) as client:
            response = await client.post(
                N8N_WEBHOOK_URL,
                json=body,
            )
            response.raise_for_status()

        logger.info(f"n8n event sent successfully: {event}")
        return True

    except httpx.TimeoutException as e:
        logger.error(f"Timed out sending n8n event '{event}': {e}")
        return False
    except httpx.HTTPStatusError as e:
        logger.error(
            f"n8n rejected event '{event}': {e.response.status_code} {e.response.text}"
        )
        return False
    except httpx.HTTPError as e:
        logger.error(f"Failed to send n8n event '{event}': {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending n8n event '{event}': {e}")
        return False