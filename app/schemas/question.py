import uuid

from pydantic import BaseModel

from app.models.question import BigFiveDomain, HollandType, QuestionInstrument


class QuestionResponse(BaseModel):
    id: uuid.UUID
    instrument: QuestionInstrument
    riasec_type: HollandType | None
    bigfive_domain: BigFiveDomain | None
    text: str
    order: int
    # Which Likert scale the client should render for this item, decided by
    # the server and independent of `instrument` above (which protocol-
    # validity items lie about — see question_service._VALIDITY_WIRE_INSTRUMENT).
    # True selects the agree/disagree "Точно…Неточно" scale (real Big Five
    # items, and the MC-SDS/infrequency validity items, which are worded as
    # agree/disagree statements even while spliced into the RIASEC block);
    # False selects the liking "Нравится…Не нравится" scale (RIASEC, MI).
    bigfive_scale: bool

    model_config = {"from_attributes": True}
