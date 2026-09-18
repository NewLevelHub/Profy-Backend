import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BelbinRun(Base):
    """Одно завершённое прохождение Belbin BTRSPI (PRO-338 Ф2.3, epic
    Тикеты-новые-тесты/03-Фаза2-Белбин.md). Мирроит `PsychoEmotionalRun`
    (psychoemotional_runs, PRO-305): **append-only история** —
    `assessment_id` НЕ unique, повторное прохождение = новая строка,
    предыдущие не перезаписываются. Секция отчёта (`TeamRoleSection`, Ф2.7)
    читает последнюю строку по `assessment_id`.

    `allocations` — список из 7 блоков (разделы I–VII), каждый блок сырой
    `{item_id: баллы}` в формате `app/services/ipsative_battery.py::
    PointAllocation` (Ф0.6) — уже провалидированный тем же модулем
    (`validate_allocation`, сумма строго 10 на блок) на этапе сабмита
    (Ф2.4), эта модель ничего не проверяет сама.

    `role_totals` — агрегат `ipsative_battery.aggregate_by_key()` по всей
    батарее: `{role_key: итоговый_балл}` на все 8 ролей Belbin. Ключи ролей
    (латиницей, без кириллицы в коде — тот же принцип, что у
    `professional_types_bank.py`'s `practical`/`technical`/...) владеет
    контент-банк (`scripts/belbin_bank.py`, Ф2.2, ещё не реализован) — эта
    модель намеренно не перечисляет их жёстко: `role_totals` остаётся
    произвольным JSONB-словарём, а не колонкой с Postgres enum'ом. Раздел
    ролей ("И/П/Ф/М/Р/О/К/Д" в спецификации) не соответствует отдельному
    типизированному столбцу нигде в этой таблице — намеренное решение, а не
    недосмотр: единственное место, где перечисление ролей вообще имело бы
    смысл как enum, — тип колонки, а колонки для одной роли тут нет
    (`role_totals` хранит все 8 сразу, одним JSONB-блобом)."""

    __tablename__ = "belbin_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,  # NOT unique — append-only история прохождений
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    allocations: Mapped[list] = mapped_column(JSONB, nullable=False)
    role_totals: Mapped[dict] = mapped_column(JSONB, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
