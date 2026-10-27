"""«Сотрудники» in the CRM: the owner's list of the business staff."""

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import UserRole
from tests.integration.test_crm_deals import URL, _h, _user, head, manager  # noqa: F401 — fixtures


async def test_owner_sees_the_staff(
    client: httpx.AsyncClient, db_session: AsyncSession, manager, head, test_user, admin_user
) -> None:
    owner = await _user(db_session, UserRole.owner, "Санжар")
    specialist = await _user(db_session, UserRole.psychologist, "Лолита")
    response = await client.get(f"{URL}/staff", headers=_h(owner))
    assert response.status_code == 200
    ids = {m["id"]: m for m in response.json()}
    for user in (owner, specialist, manager, head):
        assert ids[str(user.id)]["role"] == user.role.value
    # Students and platform admins are not the owner's staff.
    assert str(test_user.id) not in ids and str(admin_user.id) not in ids

    for user in (manager, head):
        assert (await client.get(f"{URL}/staff", headers=_h(user))).status_code == 403
