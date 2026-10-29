"""WhatsApp in the CRM (app/services/whatsapp/, ТЗ §3.5, П1-01, П1-03, И-05)
on the stub provider: the CRM's logic runs unchanged without Green API."""

from datetime import datetime, timezone

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.crm import Attribution, CrmDeal, CrmMessage, CrmParent, MessageStatus
from app.models.meta_ads import MetaAd
from app.models.user import UserRole
from app.services.crm import lead_source
from app.services.whatsapp import intake, provider
from app.services.whatsapp.fake import FakeWhatsApp
from app.services.whatsapp.green_api import GreenApi
from app.services.whatsapp.provider import StatusUpdate
from tests.integration.test_crm_deals import URL, _h, _user

PHONE = "+77050000001"
TOKEN = "hook-token"


@pytest_asyncio.fixture
async def wa(monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession) -> FakeWhatsApp:
    monkeypatch.setattr(settings, "GREEN_API_ID_INSTANCE", "1")
    monkeypatch.setattr(settings, "GREEN_API_TOKEN_INSTANCE", "t")
    monkeypatch.setattr(settings, "GREEN_API_WEBHOOK_TOKEN", TOKEN)
    # This database's clients with the test phones, if any (rolled back after).
    await db_session.execute(delete(CrmParent).where(CrmParent.phone.like("+7705000000%")))
    fake = FakeWhatsApp()
    provider.use(fake)
    return fake


async def _deals(db: AsyncSession, phone: str) -> list[CrmDeal]:
    parent = await db.scalar(select(CrmParent).where(CrmParent.phone == phone))
    if parent is None:
        return []
    return list((await db.execute(
        select(CrmDeal).where(CrmDeal.parent_id == parent.id).order_by(CrmDeal.created_at)
    )).scalars())


async def test_an_unknown_number_makes_a_lead_and_a_known_one_joins_it(db_session: AsyncSession, wa: FakeWhatsApp) -> None:
    await intake.handle(db_session, [wa.incoming(PHONE, "Здравствуйте! Хочу узнать подробнее", name="Асель")])
    [deal] = await _deals(db_session, PHONE)
    parent = await db_session.get(CrmParent, deal.parent_id)
    assert (parent.full_name, deal.stage.value, deal.first_message) == ("Асель", "unsorted", "Здравствуйте! Хочу узнать подробнее")
    assert deal.repeat is False and deal.meta_ad_id is None  # «Креатив не определён»
    # No ad data: SQL NULL, not a JSON null.
    assert await db_session.scalar(select(func.count()).select_from(CrmMessage).where(
        CrmMessage.deal_id == deal.id, CrmMessage.ad.is_not(None))) == 0

    # П1-03: the same number again goes to the open deal's feed.
    again = wa.incoming("8 705 000 00 01", "Сколько стоит?")
    await intake.handle(db_session, [again])
    assert len(await _deals(db_session, PHONE)) == 1
    rows = list((await db_session.execute(select(CrmMessage).where(CrmMessage.deal_id == deal.id))).scalars())
    assert [m.text for m in sorted(rows, key=lambda m: m.at)] == ["Здравствуйте! Хочу узнать подробнее", "Сколько стоит?"]

    # A repeated webhook is a no-op.
    assert await intake.handle(db_session, [again]) == 0

    # No open deal: a new lead, «повторное обращение».
    deal.result = deal.result.lost
    await db_session.flush()
    await intake.handle(db_session, [wa.incoming(PHONE, "Снова здравствуйте")])
    deals = await _deals(db_session, PHONE)
    assert len(deals) == 2 and deals[1].repeat is True


async def test_the_ad_in_the_message_sets_the_source(db_session: AsyncSession, wa: FakeWhatsApp) -> None:
    """П1-01: the ad's id in the message — «авто: реклама», even with the greeting erased."""
    db_session.add(MetaAd(id="ad-77", name="Статика 1.4", adset_name="Advantage+", campaign_name="Переписки"))
    await db_session.flush()
    await intake.handle(db_session, [wa.incoming("+77050000002", "?", ad_id="ad-77")])
    [deal] = await _deals(db_session, "+77050000002")
    assert deal.meta_ad_id == "ad-77" and deal.attribution.value == "ad"
    # An ad the CRM does not know yet: kept in the message, the lead stays undefined.
    await intake.handle(db_session, [wa.incoming("+77050000003", "?", ad_id="unknown")])
    [other] = await _deals(db_session, "+77050000003")
    assert other.meta_ad_id is None
    message = await db_session.scalar(select(CrmMessage).where(CrmMessage.deal_id == other.id))
    assert message.ad["sourceId"] == "unknown"

    # The next Meta sync brings the ad: the lead gets it, «авто: реклама».
    db_session.add(MetaAd(id="unknown", name="Видео 3", adset_name="Новая", campaign_name="Переписки"))
    await db_session.flush()
    assert await lead_source.attach_late_ads(db_session) >= 1
    await db_session.flush()
    await db_session.refresh(other)
    assert other.meta_ad_id == "unknown" and other.attribution.value == "ad"
    # A source picked by hand meanwhile stays.
    await intake.handle(db_session, [wa.incoming("+77050000009", "?", ad_id="later")])
    [picked] = await _deals(db_session, "+77050000009")
    picked.meta_ad_id, picked.attribution = "ad-77", Attribution.manual
    db_session.add(MetaAd(id="later", name="Видео 4"))
    await db_session.flush()
    await lead_source.attach_late_ads(db_session)
    await db_session.flush()
    await db_session.refresh(picked)
    assert picked.meta_ad_id == "ad-77"


async def test_test_numbers_only(db_session: AsyncSession, wa: FakeWhatsApp, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "WHATSAPP_TEST_NUMBERS", "+7 (705) 000-00-04")
    await intake.handle(db_session, [wa.incoming("+77050000005", "личный чат"), wa.incoming("87050000004", "тест")])
    assert await _deals(db_session, "+77050000005") == []
    assert len(await _deals(db_session, "+77050000004")) == 1


async def test_the_chat_in_the_card(client: httpx.AsyncClient, db_session: AsyncSession, wa: FakeWhatsApp) -> None:
    await intake.handle(db_session, [wa.incoming("+77050000006", "Добрый день", name="Мадина")])
    [deal] = await _deals(db_session, "+77050000006")
    manager = await _user(db_session, UserRole.sales_manager)
    accepted = await client.post(f"{URL}/deals/{deal.id}/accept", headers=_h(manager))
    assert accepted.status_code == 200 and accepted.json()["messages"][0]["direction"] == "in"

    sent = await client.post(f"{URL}/deals/{deal.id}/messages", json={"text": "Здравствуйте, Мадина!"}, headers=_h(manager))
    assert sent.status_code == 200, sent.text
    assert wa.sent == [("+77050000006", "Здравствуйте, Мадина!")]
    newest = sent.json()["messages"][0]
    assert (newest["direction"], newest["status"], newest["author"]["id"]) == ("out", "pending", str(manager.id))

    # Statuses go forward only; the provider echoing the CRM's own message adds nothing.
    out = await db_session.scalar(select(CrmMessage).where(CrmMessage.text == "Здравствуйте, Мадина!"))
    await intake.handle(db_session, [StatusUpdate(out.provider_id, MessageStatus.read), StatusUpdate(out.provider_id, MessageStatus.sent)])
    await db_session.refresh(out)
    assert out.status == MessageStatus.read

    # A message from the sales phone itself joins the chat.
    from_phone = wa.incoming("+77050000006", "Отправлю прайс")
    await intake.handle(db_session, [from_phone.__class__(**{**from_phone.__dict__, "outgoing": True})])
    detail = (await client.get(f"{URL}/deals/{deal.id}", headers=_h(manager))).json()
    assert [m["direction"] for m in detail["messages"]][:2] == ["out", "out"]

    # Someone else's deal: no.
    other = await _user(db_session, UserRole.sales_manager)
    assert (await client.post(f"{URL}/deals/{deal.id}/messages", json={"text": "x"}, headers=_h(other))).status_code == 404


async def test_the_webhook_needs_the_token(client: httpx.AsyncClient, db_session: AsyncSession, wa: FakeWhatsApp) -> None:
    provider.use(GreenApi())  # the real parser; nothing is sent
    payload = {
        "typeWebhook": "incomingMessageReceived", "idMessage": "BAE5F4886F6F2D05", "timestamp": 1793254000,
        "senderData": {"chatId": "77050000007@c.us", "senderName": "Айгуль"},
        "messageData": {"typeMessage": "extendedTextMessage", "extendedTextMessageData": {
            "text": "Здравствуйте! Вы обратились в Profile", "sourceType": "ad", "sourceId": "120000",
            "sourceUrl": "https://fb.me/x", "ctwaClid": "abc",
        }},
    }
    hook = "/api/v1/whatsapp/webhook"
    assert (await client.post(hook, json=payload)).status_code == 403
    assert (await client.post(hook, json=payload, headers={"Authorization": "Bearer wrong"})).status_code == 403
    assert (await client.post(hook, json=payload, headers={"Authorization": f"Bearer {TOKEN}"})).status_code == 200
    [deal] = await _deals(db_session, "+77050000007")
    message = await db_session.scalar(select(CrmMessage).where(CrmMessage.deal_id == deal.id))
    assert message.ad["sourceId"] == "120000" and message.at == datetime.fromtimestamp(1793254000, tz=timezone.utc)
    # A group chat is ignored.
    group = {**payload, "idMessage": "G1", "senderData": {"chatId": "120363@g.us"}}
    await client.post(hook, json=group, headers={"Authorization": f"Bearer {TOKEN}"})
    assert await db_session.scalar(select(CrmMessage).where(CrmMessage.provider_id == "G1")) is None


def test_green_api_formats() -> None:
    green = GreenApi()
    [photo] = green.parse({
        "typeWebhook": "incomingMessageReceived", "idMessage": "P1", "timestamp": 1,
        "senderData": {"chatId": "77051234567@c.us"},
        "messageData": {"typeMessage": "imageMessage", "fileMessageData": {"caption": "вот"}},
    })
    assert (photo.phone, photo.text, photo.kind) == ("+77051234567", "[фото] вот", "image")
    [status] = green.parse({"typeWebhook": "outgoingMessageStatus", "idMessage": "X", "status": "delivered"})
    assert status == StatusUpdate("X", MessageStatus.delivered)
    assert green.parse({"typeWebhook": "stateInstanceChanged"}) == []


async def test_off_without_the_instance(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    assert (await client.post("/api/v1/whatsapp/webhook", json={})).status_code == 404
    manager = await _user(db_session, UserRole.sales_manager)
    deal = (await client.post(f"{URL}/deals", json={"parent": {"full_name": "А", "phone": "+77050000008"}}, headers=_h(manager))).json()
    answer = await client.post(f"{URL}/deals/{deal['id']}/messages", json={"text": "x"}, headers=_h(manager))
    assert answer.status_code == 404 and answer.json()["error_code"] == "whatsapp_disabled"
