"""Green API webhook (app/services/whatsapp/). Mounted at `/api/v1/whatsapp`.

Green API sends the instance's webhookUrlToken as `Authorization: Bearer`
(set by scripts/whatsapp_set_webhook.py). Without the instance or the token
configured the route does not exist (404).
"""

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.services.whatsapp import intake, provider

router = APIRouter(tags=["whatsapp"])


@router.post("/webhook", include_in_schema=False)
async def webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(default=None),
) -> dict:
    if not (settings.whatsapp_enabled and settings.GREEN_API_WEBHOOK_TOKEN):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    expected = f"Bearer {settings.GREEN_API_WEBHOOK_TOKEN}"
    if authorization is None or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    try:
        payload = await request.json()
    except ValueError:
        return {}
    if isinstance(payload, dict):
        await intake.handle(db, provider.get().parse(payload))
    # Always 200 once authorized: anything else makes Green API resend.
    return {}
