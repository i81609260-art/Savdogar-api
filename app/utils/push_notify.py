"""Web Push notification sender using VAPID keys."""

import json
import logging
from typing import Optional

from pywebpush import webpush, WebPushException

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def send_web_push(
    subscription_json: str,
    title: str,
    body: str,
    url: Optional[str] = None,
) -> bool:
    """Send a browser push notification to a subscribed user."""
    if not settings.vapid_private_key or not settings.vapid_public_key:
        logger.debug("VAPID keys not configured, skipping web push")
        return False

    try:
        subscription = json.loads(subscription_json)
        payload = json.dumps({"title": title, "body": body, "url": url or "/"})
        webpush(
            subscription_info=subscription,
            data=payload,
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": settings.vapid_claims_email},
        )
        return True
    except WebPushException as exc:
        logger.warning("Web push failed: %s", exc)
        return False
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("Invalid push subscription: %s", exc)
        return False
